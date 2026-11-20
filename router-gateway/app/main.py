from __future__ import annotations

import json
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from .cascade import run_cascade
from .config import Settings, load_settings
from .providers import PASSTHROUGH_PARAMS, Provider, ProviderError, build_providers
from .router import Decider, RuleRouter, cost_usd
from .tracing import TraceBuilder, TraceStore
from .verifiers import Verifier, default_verifier

MODEL_ALIASES = {"auto": "auto", "single": "single", "strong": "single", "cheap": "cheap"}
RUNTIME_FIELDS = {
    "threshold": float,
    "escalation_hint": bool,
    "max_escalations": int,
    "verify": bool,
    "session_budget_usd": float,
}


def error_response(status: int, message: str, kind: str = "invalid_request_error") -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"message": message, "type": kind}})


def create_app(
    settings: Settings | None = None,
    providers: list[Provider] | None = None,
    decider: Decider | None = None,
    verifier: Verifier | None = None,
) -> FastAPI:
    settings = settings or load_settings()
    tiers = settings.tiers
    providers = providers or build_providers(tiers)
    decider = decider or RuleRouter()
    verifier = verifier or default_verifier()
    store = TraceStore(settings.db_path)
    spent: dict[str, float] = {}

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        for p in providers:
            close = getattr(p, "aclose", None)
            if close:
                await close()

    app = FastAPI(title="Router + Cascade Gateway", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"],
        expose_headers=["X-Router-Trace-Id", "X-Router-Tier"],
    )
    app.state.store = store
    app.state.settings = settings

    @app.get("/health")
    async def health():
        return {"status": "ok", "tiers": [t.name for t in tiers]}

    @app.get("/v1/models")
    async def list_models():
        now = int(time.time())
        return {"object": "list", "data": [
            {"id": m, "object": "model", "created": now, "owned_by": "router-gateway"}
            for m in ("auto", "single", "cheap")
        ]}

    @app.post("/v1/chat/completions")
    async def chat(request: Request, x_session_id: str | None = Header(default=None),
                   x_client: str | None = Header(default=None), user_agent: str | None = Header(default=None)):
        try:
            body = await request.json()
        except Exception:
            return error_response(400, "Request body must be valid JSON")
        messages = body.get("messages")
        if not isinstance(messages, list) or not messages:
            return error_response(400, "'messages' must be a non-empty list")
        if body.get("tools") or body.get("functions"):
            return error_response(400, "Tool/function calling is not supported by this gateway version")

        requested = str(body.get("model") or "auto")
        mode = MODEL_ALIASES.get(requested.split("/")[-1].lower(), "auto")
        forced = mode in ("single", "cheap")
        session = x_session_id or "default"
        rt = settings.runtime

        if rt.session_budget_usd > 0 and spent.get(session, 0.0) >= rt.session_budget_usd:
            return error_response(429, "Session budget exceeded", "budget_exceeded")

        trace = TraceBuilder(session, x_client or (user_agent or "unknown")[:60], mode, requested)
        n = len(tiers)
        with trace.span("route") as rs:
            if mode == "auto":
                d = decider.decide(messages, n, rt.threshold)
                start = d.tier_index
                rs.set(hardness=d.hardness, threshold=d.threshold, confidence=d.confidence,
                       reason=d.reason, features=d.features, chosen_tier=tiers[start].name)
            else:
                start = n - 1 if mode == "single" else 0
                rs.set(reason=f"forced by model name '{requested}'", chosen_tier=tiers[start].name)

        params = {k: v for k, v in body.items() if k in PASSTHROUGH_PARAMS}
        try:
            result = await run_cascade(
                messages=messages, request=body, params=params, tiers=tiers, providers=providers,
                start=start, verifier=verifier, runtime=rt, trace=trace, forced=forced,
            )
        except ProviderError as exc:
            row, spans = trace.finish({
                "start_tier": tiers[start].name, "final_tier": None, "escalations": 0, "attempts": 0,
                "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0, "counterfactual_usd": 0.0,
                "passed": None, "verifier": None, "verdict": None, "error": str(exc),
            })
            store.emit(row, spans)
            return error_response(502, str(exc), "provider_error")

        final = result.final
        comp = final.completion
        assert comp is not None
        first_ok = next(a for a in result.attempts if a.completion is not None)
        strong = tiers[-1]
        counterfactual = cost_usd(strong, first_ok.completion.tokens_in, comp.tokens_out)  # type: ignore[union-attr]
        total_cost = result.total_cost
        spent[session] = spent.get(session, 0.0) + total_cost
        verdict = final.verdict
        row, spans = trace.finish({
            "start_tier": tiers[start].name,
            "final_tier": tiers[final.tier_index].name,
            "escalations": result.escalations,
            "attempts": len(result.attempts),
            "tokens_in": sum(a.completion.tokens_in for a in result.attempts if a.completion),
            "tokens_out": sum(a.completion.tokens_out for a in result.attempts if a.completion),
            "cost_usd": round(total_cost, 8),
            "counterfactual_usd": round(counterfactual, 8),
            "passed": None if verdict is None else int(verdict.passed),
            "verifier": None if verdict is None else verdict.name,
            "verdict": None if verdict is None else verdict.evidence,
            "error": None,
        })
        store.emit(row, spans)

        completion_id = "chatcmpl-" + uuid.uuid4().hex[:24]
        created = int(time.time())
        usage = {
            "prompt_tokens": comp.tokens_in,
            "completion_tokens": comp.tokens_out,
            "total_tokens": comp.tokens_in + comp.tokens_out,
        }
        meta = {
            "trace_id": trace.trace_id,
            "mode": mode,
            "start_tier": tiers[start].name,
            "final_tier": tiers[final.tier_index].name,
            "escalations": result.escalations,
            "cost_usd": round(total_cost, 8),
            "counterfactual_single_usd": round(counterfactual, 8),
            "latency_ms": row["total_ms"],
            "verified": None if verdict is None else verdict.passed,
            "verifier_evidence": None if verdict is None else verdict.evidence,
        }
        headers = {"X-Router-Trace-Id": trace.trace_id, "X-Router-Tier": tiers[final.tier_index].name}
        model_name = comp.model

        if body.get("stream"):
            include_usage = bool((body.get("stream_options") or {}).get("include_usage"))
            return StreamingResponse(
                _sse(completion_id, created, model_name, comp.text, comp.finish_reason, usage, include_usage),
                media_type="text/event-stream", headers=headers,
            )
        return JSONResponse(
            headers=headers,
            content={
                "id": completion_id, "object": "chat.completion", "created": created, "model": model_name,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": comp.text},
                             "finish_reason": comp.finish_reason}],
                "usage": usage,
                "x_router": meta,
            },
        )

    # ---------- observability and config APIs (contract for the dashboard) ----------

    @app.get("/api/traces")
    async def api_traces(limit: int = 50, mode: str | None = None, session_id: str | None = None):
        store.flush()
        return store.list_traces(min(limit, 500), mode, session_id)

    @app.get("/api/traces/{trace_id}")
    async def api_trace(trace_id: str):
        store.flush()
        t = store.get_trace(trace_id)
        if t is None:
            raise HTTPException(404, "trace not found")
        return t

    @app.get("/api/metrics/summary")
    async def api_summary(window_s: float | None = None, session_id: str | None = None):
        store.flush()
        return store.summary(window_s, session_id)

    @app.get("/api/config")
    async def api_get_config():
        return {
            "runtime": asdict(settings.runtime),
            "tiers": [{"name": t.name, "provider": t.provider, "model": t.model,
                       "price_in_per_m": t.price_in_per_m, "price_out_per_m": t.price_out_per_m} for t in tiers],
        }

    @app.put("/api/config")
    async def api_put_config(update: dict[str, Any], x_admin_key: str | None = Header(default=None)):
        if settings.admin_key and x_admin_key != settings.admin_key:
            raise HTTPException(401, "admin key required")
        for k, v in update.items():
            if k not in RUNTIME_FIELDS:
                raise HTTPException(400, f"unknown setting: {k}")
            try:
                setattr(settings.runtime, k, RUNTIME_FIELDS[k](v))
            except (TypeError, ValueError):
                raise HTTPException(400, f"bad value for {k}")
        return asdict(settings.runtime)

    return app


def _chunk(cid: str, created: int, model: str, delta: dict, finish: str | None) -> bytes:
    payload = {"id": cid, "object": "chat.completion.chunk", "created": created, "model": model,
               "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
    return f"data: {json.dumps(payload)}\n\n".encode()


async def _sse(cid: str, created: int, model: str, text: str, finish: str, usage: dict, include_usage: bool):
    """The cascade needs the whole reply before it can verify it, so the reply is buffered
    and then replayed to streaming clients (such as coding agents) in small pieces."""
    yield _chunk(cid, created, model, {"role": "assistant", "content": ""}, None)
    for i in range(0, len(text), 60):
        yield _chunk(cid, created, model, {"content": text[i:i + 60]}, None)
    yield _chunk(cid, created, model, {}, finish)
    if include_usage:
        payload = {"id": cid, "object": "chat.completion.chunk", "created": created, "model": model,
                   "choices": [], "usage": usage}
        yield f"data: {json.dumps(payload)}\n\n".encode()
    yield b"data: [DONE]\n\n"


def app_factory() -> FastAPI:
    return create_app()
