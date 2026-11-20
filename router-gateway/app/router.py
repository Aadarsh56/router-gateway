from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from .config import TierConfig

HARD_WORDS = (
    "refactor", "architecture", "race condition", "concurrency", "deadlock", "optimi",
    "migrate", "redesign", "security", "performance", "algorithm", "rewrite",
)
EASY_WORDS = (
    "typo", "rename", "comment", "docstring", "format", "summar", "explain",
    "spelling", "print", "readme", "log ",
)
FAIL_WORDS = ("traceback", "error:", "failed", "exception", "assertionerror")


def cost_usd(tier: TierConfig, tokens_in: int, tokens_out: int) -> float:
    return (tokens_in * tier.price_in_per_m + tokens_out * tier.price_out_per_m) / 1_000_000


def message_text(message: dict) -> str:
    content = message.get("content", "")
    if isinstance(content, list):
        return " ".join(p.get("text", "") for p in content if isinstance(p, dict))
    return str(content)


def extract_features(messages: list[dict]) -> dict[str, Any]:
    """Features come from the LAST user message, because coding agents prepend very long
    system prompts and file contents that would drown out the actual request."""
    last_user = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last_user = message_text(m)
            break
    low = last_user.lower()
    return {
        "n_messages": len(messages),
        "last_user_chars": len(last_user),
        "n_code_fences": last_user.count("```") // 2,
        "hard_hits": [w for w in HARD_WORDS if w in low],
        "easy_hits": [w for w in EASY_WORDS if w in low],
        "fail_hits": [w for w in FAIL_WORDS if w in low],
    }


@dataclass
class Decision:
    tier_index: int
    hardness: float
    threshold: float
    confidence: float
    reason: str
    features: dict[str, Any] = field(default_factory=dict)


class Decider(Protocol):
    def decide(self, messages: list[dict], n_tiers: int, threshold: float) -> Decision: ...


class RuleRouter:
    """Version 1 decision layer: transparent, rule-based hardness score.

    Swap this for a learned decider (embedding classifier) later by implementing the same
    `decide` method; nothing else in the gateway needs to change.
    """

    def decide(self, messages: list[dict], n_tiers: int, threshold: float) -> Decision:
        f = extract_features(messages)
        score = 0.30
        reasons: list[str] = []
        if f["hard_hits"]:
            score += 0.25
            reasons.append(f"hard words {f['hard_hits']}")
        if f["easy_hits"]:
            score -= 0.20
            reasons.append(f"easy words {f['easy_hits']}")
        if f["fail_hits"]:
            score += 0.15
            reasons.append("error or failure text in request")
        length_bonus = min(f["last_user_chars"] / 4000.0, 0.20)
        if length_bonus > 0.02:
            score += length_bonus
            reasons.append(f"long request ({f['last_user_chars']} chars)")
        if f["n_code_fences"] >= 2:
            score += 0.10
            reasons.append("multiple code blocks")
        score = max(0.0, min(1.0, score))
        threshold = max(0.05, threshold)
        idx = min(n_tiers - 1, int(score / threshold))
        confidence = min(1.0, 0.5 + abs(score - threshold * max(idx, 1)))
        return Decision(
            tier_index=idx,
            hardness=round(score, 3),
            threshold=threshold,
            confidence=round(confidence, 3),
            reason="; ".join(reasons) or "no strong signals, default hardness",
            features=f,
        )
