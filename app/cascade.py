from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .config import RuntimeConfig, TierConfig
from .providers import Completion, Provider, ProviderError
from .router import cost_usd
from .tracing import TraceBuilder
from .verifiers import Verdict, Verifier


@dataclass
class Attempt:
    tier_index: int
    completion: Completion | None
    verdict: Verdict | None
    cost_usd: float
    error: str | None = None


@dataclass
class CascadeResult:
    attempts: list[Attempt] = field(default_factory=list)

    @property
    def final(self) -> Attempt:
        return self.attempts[-1]

    @property
    def escalations(self) -> int:
        return len(self.attempts) - 1

    @property
    def total_cost(self) -> float:
        return sum(a.cost_usd for a in self.attempts)


def build_escalation_messages(messages: list[dict], failed_text: str, evidence: str) -> list[dict]:
    return list(messages) + [
        {"role": "assistant", "content": failed_text},
        {
            "role": "user",
            "content": (
                f"Your previous reply was rejected by an automatic check: {evidence}. "
                "Please answer again and follow the required output format exactly."
            ),
        },
    ]


async def run_cascade(
    *,
    messages: list[dict],
    request: dict[str, Any],
    params: dict[str, Any],
    tiers: list[TierConfig],
    providers: list[Provider],
    start: int,
    verifier: Verifier,
    runtime: RuntimeConfig,
    trace: TraceBuilder,
    forced: bool,
) -> CascadeResult:
    """Call `start` tier, verify, and escalate upward while the check fails.

    `forced` modes (single/cheap baselines) never escalate and never fall back, so they
    measure exactly what one fixed model does. The verifier still runs in every mode so
    pass rates are comparable across modes.
    """
    result = CascadeResult()
    last = len(tiers) - 1
    idx = start
    current = messages
    while True:
        tier = tiers[idx]
        comp: Completion | None = None
        error: str | None = None
        cost = 0.0
        with trace.span("model_call", tier=tier.name, model=tier.model, provider=tier.provider) as sp:
            try:
                comp = await providers[idx].complete(current, params)
                cost = cost_usd(tier, comp.tokens_in, comp.tokens_out)
                sp.set(tokens_in=comp.tokens_in, tokens_out=comp.tokens_out, cost_usd=round(cost, 8),
                       finish_reason=comp.finish_reason, provider_request_id=comp.raw_id)
            except ProviderError as exc:
                error = str(exc)
                sp.set(status="error", error=error)

        verdict: Verdict | None = None
        if comp is not None and runtime.verify:
            with trace.span("verify", tier=tier.name) as vs:
                verdict = verifier.check(comp, request)
                vs.set(status="ok" if verdict.passed else "rejected", verifier=verdict.name,
                       passed=verdict.passed, evidence=verdict.evidence)

        result.attempts.append(Attempt(idx, comp, verdict, cost, error))
        escalations_used = len(result.attempts) - 1
        can_escalate = (not forced) and idx < last and escalations_used < runtime.max_escalations

        if comp is None:
            if can_escalate:
                idx += 1  # provider failure: fall back to the next tier
                continue
            raise ProviderError(error or "provider failed")
        if verdict is None or verdict.passed or not can_escalate:
            return result
        if runtime.escalation_hint:
            current = build_escalation_messages(messages, comp.text, verdict.evidence)
        idx += 1
