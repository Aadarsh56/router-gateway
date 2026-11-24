import json

import pytest
from fastapi.testclient import TestClient

from app.config import RuntimeConfig, Settings, TierConfig
from app.main import create_app
from app.providers import Completion, ProviderError

GOOD = "Here is the change:\n\n```python\ndef f():\n    return 1\n```\n"
BAD = "<<<<<<< SEARCH\nold\n=======\nnew\n"  # unterminated block, verifier must reject


class FakeProvider:
    def __init__(self, name, replies=None, fail=False):
        self.name = name
        self.replies = list(replies or [GOOD])
        self.fail = fail
        self.calls = []

    async def complete(self, messages, params):
        self.calls.append(messages)
        if self.fail:
            raise ProviderError(f"{self.name}: simulated outage")
        text = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        return Completion(text=text, finish_reason="stop", tokens_in=1000, tokens_out=200,
                          model=f"fake-{self.name}", raw_id="x")


def make(tmp_path, cheap=None, strong=None, **runtime):
    tiers = [
        TierConfig("cheap", "mock", "fake-cheap", price_in_per_m=0.1, price_out_per_m=0.4),
        TierConfig("strong", "mock", "fake-strong", price_in_per_m=1.25, price_out_per_m=10.0),
    ]
    cheap = cheap or FakeProvider("cheap")
    strong = strong or FakeProvider("strong")
    settings = Settings(tiers=tiers, runtime=RuntimeConfig(**runtime), db_path=str(tmp_path / "t.db"))
    return TestClient(create_app(settings, providers=[cheap, strong])), cheap, strong


def ask(client, text, model="auto", **extra):
    body = {"model": model, "messages": [{"role": "system", "content": "You edit code."},
                                         {"role": "user", "content": text}], **extra}
    return client.post("/v1/chat/completions", json=body)


EASY = "Please fix the typo in the docstring and rename the variable."
HARD = "Refactor the architecture to remove the race condition. It failed with an exception: traceback below."


def test_openai_response_shape(tmp_path):
    client, _, _ = make(tmp_path)
    r = ask(client, EASY)
    assert r.status_code == 200
    d = r.json()
    assert d["object"] == "chat.completion"
    assert d["choices"][0]["message"]["role"] == "assistant"
    assert d["usage"]["total_tokens"] == 1200
    assert r.headers["X-Router-Trace-Id"] == d["x_router"]["trace_id"]


def test_easy_request_stays_on_cheap_tier(tmp_path):
    client, cheap, strong = make(tmp_path)
    d = ask(client, EASY).json()
    assert d["x_router"]["final_tier"] == "cheap"
    assert d["x_router"]["escalations"] == 0
    assert len(cheap.calls) == 1 and len(strong.calls) == 0


def test_hard_request_starts_on_strong_tier(tmp_path):
    client, cheap, strong = make(tmp_path)
    d = ask(client, HARD).json()
    assert d["x_router"]["start_tier"] == "strong"
    assert len(cheap.calls) == 0 and len(strong.calls) == 1


def test_router_decisions_depend_on_input(tmp_path):
    client, _, _ = make(tmp_path)
    prompts = {
        "Fix the typo in the README": "cheap",
        "Explain what this function does": "cheap",
        "Refactor this module and fix the race condition": "strong",
        "Optimize the algorithm, security and performance matter": "strong",
    }
    got = {p: ask(client, p).json()["x_router"]["start_tier"] for p in prompts}
    assert got == prompts


def test_failed_check_escalates_and_sends_failed_attempt(tmp_path):
    cheap = FakeProvider("cheap", [BAD])
    client, cheap, strong = make(tmp_path, cheap=cheap)
    d = ask(client, EASY).json()
    assert d["x_router"]["start_tier"] == "cheap"
    assert d["x_router"]["final_tier"] == "strong"
    assert d["x_router"]["escalations"] == 1
    assert d["x_router"]["verified"] is True
    sent = strong.calls[0]
    assert sent[-2] == {"role": "assistant", "content": BAD}
    assert "rejected by an automatic check" in sent[-1]["content"]


def test_escalation_hint_can_be_disabled(tmp_path):
    cheap = FakeProvider("cheap", [BAD])
    client, _, strong = make(tmp_path, cheap=cheap, escalation_hint=False)
    ask(client, EASY)
    assert len(strong.calls[0]) == 2  # original messages only


def test_single_mode_never_uses_cheap(tmp_path):
    client, cheap, strong = make(tmp_path)
    d = ask(client, EASY, model="openai/single").json()
    assert d["x_router"]["final_tier"] == "strong"
    assert len(cheap.calls) == 0


def test_forced_modes_do_not_escalate(tmp_path):
    cheap = FakeProvider("cheap", [BAD])
    client, cheap, strong = make(tmp_path, cheap=cheap)
    d = ask(client, EASY, model="cheap").json()
    assert d["x_router"]["final_tier"] == "cheap"
    assert d["x_router"]["verified"] is False
    assert len(strong.calls) == 0


def test_provider_outage_falls_back_to_next_tier(tmp_path):
    client, _, strong = make(tmp_path, cheap=FakeProvider("cheap", fail=True))
    d = ask(client, EASY).json()
    assert d["x_router"]["final_tier"] == "strong"
    assert len(strong.calls) == 1


def test_all_tiers_failing_returns_502_and_is_traced(tmp_path):
    client, _, _ = make(tmp_path, cheap=FakeProvider("c", fail=True), strong=FakeProvider("s", fail=True))
    r = ask(client, EASY)
    assert r.status_code == 502
    assert client.get("/api/metrics/summary").json()["error_count"] == 1


def test_tools_are_rejected_clearly(tmp_path):
    client, _, _ = make(tmp_path)
    r = ask(client, EASY, tools=[{"type": "function"}])
    assert r.status_code == 400


def test_streaming_replays_the_verified_reply(tmp_path):
    client, _, _ = make(tmp_path)
    r = ask(client, EASY, stream=True, stream_options={"include_usage": True})
    lines = [l for l in r.text.split("\n\n") if l.startswith("data: ")]
    assert lines[-1] == "data: [DONE]"
    pieces = []
    saw_usage = False
    for l in lines[:-1]:
        c = json.loads(l[6:])
        if c["choices"]:
            pieces.append(c["choices"][0]["delta"].get("content", ""))
        else:
            saw_usage = c["usage"]["total_tokens"] == 1200
    assert "".join(pieces) == GOOD
    assert saw_usage


def test_trace_has_waterfall_spans(tmp_path):
    cheap = FakeProvider("cheap", [BAD])
    client, _, _ = make(tmp_path, cheap=cheap)
    tid = ask(client, EASY).json()["x_router"]["trace_id"]
    t = client.get(f"/api/traces/{tid}").json()
    names = [s["name"] for s in t["spans"]]
    assert names[0] == "request"
    assert names.count("model_call") == 2 and names.count("verify") == 2 and "route" in names
    route = next(s for s in t["spans"] if s["name"] == "route")
    assert "hardness" in route["attrs"] and "reason" in route["attrs"]
    assert t["trace"]["escalations"] == 1


def test_metrics_compare_single_vs_auto(tmp_path):
    client, _, _ = make(tmp_path)
    for _ in range(5):
        ask(client, EASY, model="auto")
        ask(client, EASY, model="single")
    m = client.get("/api/metrics/summary").json()["modes"]
    assert m["auto"]["requests"] == 5 and m["single"]["requests"] == 5
    assert m["auto"]["total_cost_usd"] < m["single"]["total_cost_usd"]
    assert m["auto"]["savings_vs_single_pct"] > 50
    assert m["single"]["savings_vs_single_pct"] == 0
    assert m["auto"]["pass_rate"] == 1.0


def test_runtime_config_changes_routing_live(tmp_path):
    client, _, _ = make(tmp_path)
    prompt = "Refactor this module"  # hardness 0.55
    assert ask(client, prompt).json()["x_router"]["start_tier"] == "strong"
    assert client.put("/api/config", json={"threshold": 0.9}).status_code == 200
    assert ask(client, prompt).json()["x_router"]["start_tier"] == "cheap"
    assert client.put("/api/config", json={"nonsense": 1}).status_code == 400


def test_session_budget_blocks_further_requests(tmp_path):
    client, _, _ = make(tmp_path, session_budget_usd=0.0001)
    assert ask(client, EASY).status_code == 200
    assert ask(client, EASY).status_code == 429


def test_openai_sdk_compatibility(tmp_path):
    openai = pytest.importorskip("openai")
    client, _, _ = make(tmp_path)
    sdk = openai.OpenAI(base_url="http://testserver/v1", api_key="dummy", http_client=client)
    msgs = [{"role": "user", "content": EASY}]
    r = sdk.chat.completions.create(model="auto", messages=msgs)
    assert r.choices[0].message.content == GOOD
    s = sdk.chat.completions.create(model="auto", messages=msgs, stream=True)
    assert "".join(c.choices[0].delta.content or "" for c in s if c.choices) == GOOD
