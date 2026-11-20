from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class TierConfig:
    name: str
    provider: str  # "openai_compat" or "mock"
    model: str
    base_url: str = ""
    api_key_env: str = ""
    price_in_per_m: float = 0.0  # USD per million input tokens (list price, "shadow price" if free tier)
    price_out_per_m: float = 0.0  # USD per million output tokens
    timeout_s: float = 60.0
    mock_latency_s: float = 0.0  # only used by the mock provider


@dataclass
class RuntimeConfig:
    """Values that can be changed at run time through PUT /api/config."""

    threshold: float = 0.45  # router hardness threshold: below -> cheapest tier, above -> stronger tier
    escalation_hint: bool = True  # send the failed attempt plus the reason when escalating
    max_escalations: int = 1
    verify: bool = True
    session_budget_usd: float = 0.0  # 0 means unlimited


@dataclass
class Settings:
    tiers: list[TierConfig]
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    db_path: str = "traces.db"
    admin_key: str = ""
    cors_origins: list[str] = field(default_factory=lambda: ["*"])


def load_settings(path: str | None = None) -> Settings:
    path = path or os.environ.get("ROUTER_CONFIG", "configs/tiers.yaml")
    data = yaml.safe_load(Path(path).read_text())
    tiers = [TierConfig(**t) for t in data["tiers"]]
    if len(tiers) < 2:
        raise ValueError("Configure at least two tiers, cheapest first.")
    runtime = RuntimeConfig(**data.get("runtime", {}))
    return Settings(
        tiers=tiers,
        runtime=runtime,
        db_path=os.environ.get("ROUTER_DB", data.get("db_path", "traces.db")),
        admin_key=os.environ.get("ADMIN_KEY", ""),
        cors_origins=data.get("cors_origins", ["*"]),
    )
