# Contracts (change only by agreement between AI and web owners)

## Chat endpoint (OpenAI-compatible)
`POST /v1/chat/completions`
- `model`: `auto` (router + cascade), `single` or `strong` (strong tier only), `cheap` (cheap tier only). A provider prefix such as `openai/auto` is ignored.
- Optional headers: `X-Session-Id` (groups traces per visitor), `X-Client` (label such as `aider`).
- Response: standard chat completion plus `x_router`:
  `trace_id, mode, start_tier, final_tier, escalations, cost_usd, counterfactual_single_usd, latency_ms, verified, verifier_evidence`.
- Response headers: `X-Router-Trace-Id`, `X-Router-Tier`.
- `stream: true` is supported (buffered, verified, then replayed). `tools`/`functions` return 400.

## Observability
- `GET /api/traces?limit=50&mode=&session_id=` : list of trace rows (newest first).
- `GET /api/traces/{trace_id}` : `{trace, spans[]}`; spans are ordered by `start_ms` (waterfall view).
- `GET /api/metrics/summary?window_s=&session_id=` : `{modes: {auto: {...}, single: {...}}, overall, error_count}`.
  Per mode: requests, total_cost_usd, avg_cost_usd, counterfactual_single_usd, savings_vs_single_pct,
  pass_rate, escalation_rate, latency_ms_avg/p50/p95, tokens_in/out, final_tier_counts.
- `GET /api/config`, `PUT /api/config` (header `X-Admin-Key` when ADMIN_KEY is set).
  Settable: threshold, escalation_hint, max_escalations, verify, session_budget_usd.

## Trace tables (SQLite)
traces(trace_id, ts, session_id, client, mode, requested_model, start_tier, final_tier, escalations,
       attempts, tokens_in, tokens_out, cost_usd, counterfactual_usd, total_ms, passed, verifier, verdict, error)
spans(span_id, trace_id, parent_id, name, start_ms, duration_ms, tier, tokens_in, tokens_out,
      cost_usd, status, attrs JSON)

Span names: request (root), route, model_call, verify.
`route.attrs`: hardness, threshold, confidence, reason, features, chosen_tier.
`model_call.attrs`: model, provider (`mock` for offline data), finish_reason, provider_request_id.
`verify.attrs`: verifier, passed, evidence.

## Interfaces (Python)
Decider.decide(messages, n_tiers, threshold) -> Decision(tier_index, hardness, threshold, confidence, reason, features)
Verifier.check(completion, request) -> Verdict(passed, evidence, name, ms)
Provider.complete(messages, params) -> Completion(text, finish_reason, tokens_in, tokens_out, model, raw_id)
