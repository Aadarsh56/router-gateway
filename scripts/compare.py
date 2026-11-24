"""Send the same prompts through the single strong model and through router+cascade,
then print the difference. Works against any running gateway.

    python scripts/compare.py --base-url http://localhost:8000 --prompts data/sample_prompts.mock.jsonl
"""
import argparse
import json
import time
import uuid

import httpx


def send(client, base, model, prompt, session):
    t0 = time.perf_counter()
    r = client.post(f"{base}/v1/chat/completions", headers={"X-Session-Id": session, "X-Client": "compare.py"},
                    json={"model": model, "messages": [{"role": "system", "content": "You edit code."},
                                                       {"role": "user", "content": prompt}]}, timeout=120)
    ms = (time.perf_counter() - t0) * 1000
    if r.status_code != 200:
        return {"error": r.text[:120], "ms": ms}
    d = r.json()["x_router"]
    return {**d, "ms": ms}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--prompts", required=True)
    args = ap.parse_args()
    prompts = [json.loads(l)["prompt"] for l in open(args.prompts) if l.strip()]
    session = "compare-" + uuid.uuid4().hex[:6]
    with httpx.Client() as client:
        print(f"{'mode':7} {'path':16} {'esc':>3} {'cost USD':>10} {'ms':>7}  verified  prompt")
        for p in prompts:
            for model in ("single", "auto"):
                r = send(client, args.base_url, model, p, session)
                if "error" in r:
                    print(f"{model:7} ERROR {r['error']}")
                    continue
                path = f"{r['start_tier']}->{r['final_tier']}" if r["escalations"] else r["final_tier"]
                print(f"{model:7} {path:16} {r['escalations']:>3} {r['cost_usd']:>10.6f} {r['ms']:>7.0f}  {str(r['verified']):8}  {p[:48]}")
        s = client.get(f"{args.base_url}/api/metrics/summary", params={"session_id": session}).json()["modes"]
    print("\nSUMMARY (same prompts, same session)")
    print(f"{'':28}{'single':>12}{'auto':>12}")
    rows = [("requests", "requests"), ("total cost USD", "total_cost_usd"), ("pass rate", "pass_rate"),
            ("escalation rate", "escalation_rate"), ("latency avg ms", "latency_ms_avg"), ("latency p95 ms", "latency_ms_p95")]
    for label, key in rows:
        print(f"{label:28}{str(s['single'].get(key)):>12}{str(s['auto'].get(key)):>12}")
    a, b = s["single"]["total_cost_usd"], s["auto"]["total_cost_usd"]
    if a:
        print(f"\nrouter+cascade cost vs single strong model: {(1 - b / a) * 100:.1f}% lower")


if __name__ == "__main__":
    main()
