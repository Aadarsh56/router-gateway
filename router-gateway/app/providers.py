from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from .config import TierConfig

PASSTHROUGH_PARAMS = {
    "temperature",
    "top_p",
    "max_tokens",
    "max_completion_tokens",
    "stop",
    "seed",
    "presence_penalty",
    "frequency_penalty",
}


@dataclass
class Completion:
    text: str
    finish_reason: str
    tokens_in: int
    tokens_out: int
    model: str
    raw_id: str = ""


class ProviderError(Exception):
    pass


class Provider(Protocol):
    async def complete(self, messages: list[dict], params: dict[str, Any]) -> Completion: ...


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def messages_chars(messages: list[dict]) -> int:
    total = 0
    for m in messages:
        content = m.get("content", "")
        if isinstance(content, list):
            for p in content:
                if isinstance(p, dict):
                    total += len(p.get("text", ""))
        elif isinstance(content, str):
            total += len(content)
        elif content:
            total += len(str(content))
    return total


class OpenAICompatProvider:
    """Calls any provider that exposes an OpenAI-compatible /chat/completions endpoint."""

    def __init__(self, tier: TierConfig, client: httpx.AsyncClient | None = None, retry_sleep: float = 1.0):
        self.tier = tier
        if client is None:
            limits = httpx.Limits(max_keepalive_connections=20, max_connections=50, keepalive_expiry=30.0)
            self._client = httpx.AsyncClient(limits=limits)
        else:
            self._client = client
        self._retry_sleep = retry_sleep

    async def aclose(self) -> None:
        await self._client.aclose()

    async def complete(self, messages: list[dict], params: dict[str, Any]) -> Completion:
        key = os.environ.get(self.tier.api_key_env, "") if self.tier.api_key_env else ""
        if self.tier.api_key_env and not key:
            raise ProviderError(f"{self.tier.name}: environment variable {self.tier.api_key_env} is not set")
        payload: dict[str, Any] = {"model": self.tier.model, "messages": messages}
        payload.update({k: v for k, v in params.items() if k in PASSTHROUGH_PARAMS})
        if "max_tokens" not in payload and "max_completion_tokens" not in payload:
            payload["max_tokens"] = 8192
        url = self.tier.base_url.rstrip("/") + "/chat/completions"
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        resp = None
        try:
            for attempt in range(2):
                resp = await self._client.post(url, json=payload, headers=headers, timeout=self.tier.timeout_s)
                if resp.status_code in (429, 500, 502, 503, 504) and attempt == 0:
                    await asyncio.sleep(self._retry_sleep)
                    continue
                break
        except httpx.HTTPError as exc:
            raise ProviderError(f"{self.tier.name}: network error: {exc.__class__.__name__}") from exc
        assert resp is not None
        if resp.status_code >= 400:
            raise ProviderError(f"{self.tier.name}: HTTP {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        choice = data["choices"][0]
        text = (choice.get("message") or {}).get("content") or ""
        usage = data.get("usage") or {}
        return Completion(
            text=text,
            finish_reason=choice.get("finish_reason") or "stop",
            tokens_in=int(usage.get("prompt_tokens") or estimate_tokens(" " * messages_chars(messages))),
            tokens_out=int(usage.get("completion_tokens") or estimate_tokens(text)),
            model=data.get("model") or self.tier.model,
            raw_id=data.get("id", ""),
        )


GOOD_REPLY = "Here is the change:\n\n```python\ndef add(a, b):\n    return a + b\n```\n"
BAD_REPLY = "<<<<<<< SEARCH\ndef add(a, b):\n    return a - b\n=======\ndef add(a, b):\n    return a + b\n"


class MockProvider:
    """Offline stand-in used for tests and for dashboard development without API keys.

    Every trace produced through it is tagged provider=mock in the span attributes by the
    caller, so mock data can never be confused with real model calls. Never use it for the
    evaluation or the teacher demo.
    """

    HARD_WORDS = ("refactor", "race condition", "concurrency", "deadlock", "rewrite")

    def __init__(self, tier: TierConfig):
        self.tier = tier

    async def complete(self, messages: list[dict], params: dict[str, Any]) -> Completion:
        if self.tier.mock_latency_s:
            await asyncio.sleep(self.tier.mock_latency_s)
        last = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                c = m.get("content", "")
                last = c if isinstance(c, str) else " ".join(p.get("text", "") for p in c if isinstance(p, dict))
                break
        low = last.lower()
        is_hard = "[mock-hard]" in low or any(w in low for w in self.HARD_WORDS)
        is_weak = self.tier.name != "strong"
        text = BAD_REPLY if (is_hard and is_weak) else GOOD_REPLY
        return Completion(
            text=text,
            finish_reason="stop",
            tokens_in=estimate_tokens(" " * messages_chars(messages)),
            tokens_out=estimate_tokens(text),
            model=self.tier.model,
            raw_id="mock",
        )


def build_providers(tiers: list[TierConfig]) -> list[Provider]:
    out: list[Provider] = []
    for t in tiers:
        if t.provider == "mock":
            out.append(MockProvider(t))
        elif t.provider == "openai_compat":
            out.append(OpenAICompatProvider(t))
        else:
            raise ValueError(f"Unknown provider type: {t.provider}")
    return out
