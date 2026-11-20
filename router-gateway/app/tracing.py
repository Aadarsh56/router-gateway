from __future__ import annotations

import json
import math
import queue
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS traces (
    trace_id TEXT PRIMARY KEY,
    ts REAL NOT NULL,
    session_id TEXT,
    client TEXT,
    mode TEXT,
    requested_model TEXT,
    start_tier TEXT,
    final_tier TEXT,
    escalations INTEGER,
    attempts INTEGER,
    tokens_in INTEGER,
    tokens_out INTEGER,
    cost_usd REAL,
    counterfactual_usd REAL,
    total_ms REAL,
    passed INTEGER,
    verifier TEXT,
    verdict TEXT,
    error TEXT
);
CREATE TABLE IF NOT EXISTS spans (
    span_id TEXT PRIMARY KEY,
    trace_id TEXT NOT NULL,
    parent_id TEXT,
    name TEXT NOT NULL,
    start_ms REAL,
    duration_ms REAL,
    tier TEXT,
    tokens_in INTEGER,
    tokens_out INTEGER,
    cost_usd REAL,
    status TEXT,
    attrs TEXT
);
CREATE INDEX IF NOT EXISTS idx_traces_ts ON traces(ts);
CREATE INDEX IF NOT EXISTS idx_spans_trace ON spans(trace_id);
"""

SPAN_COLUMNS = {"tier", "tokens_in", "tokens_out", "cost_usd", "status"}


class Span:
    def __init__(self, record: dict[str, Any]):
        self.record = record

    def set(self, **kw: Any) -> None:
        for k, v in kw.items():
            if k in SPAN_COLUMNS:
                self.record[k] = v
            else:
                self.record["attrs"][k] = v


class TraceBuilder:
    """Collects the spans of one request, then hands everything to the store."""

    def __init__(self, session_id: str, client: str, mode: str, requested_model: str):
        self.trace_id = uuid.uuid4().hex[:16]
        self.session_id = session_id
        self.client = client
        self.mode = mode
        self.requested_model = requested_model
        self._t0 = time.perf_counter()
        self.started_at = time.time()
        self.spans: list[dict[str, Any]] = []
        self.root_id = uuid.uuid4().hex[:12]

    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self._t0) * 1000

    @contextmanager
    def span(self, name: str, **attrs: Any) -> Iterator[Span]:
        record: dict[str, Any] = {
            "span_id": uuid.uuid4().hex[:12],
            "trace_id": self.trace_id,
            "parent_id": self.root_id,
            "name": name,
            "start_ms": round(self.elapsed_ms(), 3),
            "duration_ms": 0.0,
            "tier": None,
            "tokens_in": None,
            "tokens_out": None,
            "cost_usd": None,
            "status": "ok",
            "attrs": {},
        }
        sp = Span(record)
        sp.set(**attrs)
        start = time.perf_counter()
        try:
            yield sp
        except Exception as exc:
            record["status"] = "error"
            record["attrs"]["error"] = f"{exc.__class__.__name__}: {exc}"
            raise
        finally:
            record["duration_ms"] = round((time.perf_counter() - start) * 1000, 3)
            self.spans.append(record)

    def finish(self, row: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        root = {
            "span_id": self.root_id,
            "trace_id": self.trace_id,
            "parent_id": None,
            "name": "request",
            "start_ms": 0.0,
            "duration_ms": round(self.elapsed_ms(), 3),
            "tier": None,
            "tokens_in": None,
            "tokens_out": None,
            "cost_usd": None,
            "status": "error" if row.get("error") else "ok",
            "attrs": {},
        }
        trace_row = {
            "trace_id": self.trace_id,
            "ts": self.started_at,
            "session_id": self.session_id,
            "client": self.client,
            "mode": self.mode,
            "requested_model": self.requested_model,
            "total_ms": round(self.elapsed_ms(), 3),
            **row,
        }
        return trace_row, [root, *self.spans]


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = max(0, math.ceil(p * len(s)) - 1)
    return s[k]


class TraceStore:
    """SQLite store. Writes happen on a background thread so they never block a response."""

    def __init__(self, path: str):
        self.path = path
        self._q: queue.Queue = queue.Queue()
        with self._conn() as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.executescript(SCHEMA)
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def emit(self, trace_row: dict[str, Any], spans: list[dict[str, Any]]) -> None:
        self._q.put((trace_row, spans))

    def flush(self) -> None:
        self._q.join()

    def _worker(self) -> None:
        conn = self._conn()
        while True:
            trace_row, spans = self._q.get()
            try:
                cols = ",".join(trace_row)
                marks = ",".join("?" for _ in trace_row)
                conn.execute(f"INSERT OR REPLACE INTO traces ({cols}) VALUES ({marks})", list(trace_row.values()))
                for s in spans:
                    row = dict(s)
                    row["attrs"] = json.dumps(row["attrs"])
                    cols = ",".join(row)
                    marks = ",".join("?" for _ in row)
                    conn.execute(f"INSERT OR REPLACE INTO spans ({cols}) VALUES ({marks})", list(row.values()))
                conn.commit()
            except Exception as exc:  # never let a logging failure kill the worker
                print(f"[trace-store] write failed: {exc}")
            finally:
                self._q.task_done()

    def list_traces(self, limit: int = 50, mode: str | None = None, session_id: str | None = None) -> list[dict]:
        q = "SELECT * FROM traces WHERE 1=1"
        args: list[Any] = []
        if mode:
            q += " AND mode = ?"
            args.append(mode)
        if session_id:
            q += " AND session_id = ?"
            args.append(session_id)
        q += " ORDER BY ts DESC LIMIT ?"
        args.append(limit)
        with self._conn() as c:
            return [dict(r) for r in c.execute(q, args)]

    def get_trace(self, trace_id: str) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM traces WHERE trace_id = ?", (trace_id,)).fetchone()
            if row is None:
                return None
            spans = []
            for s in c.execute("SELECT * FROM spans WHERE trace_id = ? ORDER BY start_ms", (trace_id,)):
                d = dict(s)
                d["attrs"] = json.loads(d["attrs"] or "{}")
                spans.append(d)
        return {"trace": dict(row), "spans": spans}

    def summary(self, window_s: float | None = None, session_id: str | None = None) -> dict[str, Any]:
        q = "SELECT * FROM traces WHERE error IS NULL"
        args: list[Any] = []
        if window_s:
            q += " AND ts >= ?"
            args.append(time.time() - window_s)
        if session_id:
            q += " AND session_id = ?"
            args.append(session_id)
        with self._conn() as c:
            rows = [dict(r) for r in c.execute(q, args)]
            n_errors = c.execute(
                "SELECT COUNT(*) FROM traces WHERE error IS NOT NULL" + (" AND ts >= ?" if window_s else ""),
                [time.time() - window_s] if window_s else [],
            ).fetchone()[0]
        modes: dict[str, dict[str, Any]] = {}
        for mode in sorted({r["mode"] for r in rows}):
            modes[mode] = _aggregate([r for r in rows if r["mode"] == mode])
        return {"window_s": window_s, "modes": modes, "overall": _aggregate(rows), "error_count": n_errors}


def _aggregate(rows: list[dict]) -> dict[str, Any]:
    n = len(rows)
    if n == 0:
        return {"requests": 0}
    cost = sum(r["cost_usd"] or 0 for r in rows)
    cf = sum(r["counterfactual_usd"] or 0 for r in rows)
    lat = [r["total_ms"] for r in rows]
    judged = [r for r in rows if r["passed"] is not None]
    tiers: dict[str, int] = {}
    for r in rows:
        tiers[r["final_tier"]] = tiers.get(r["final_tier"], 0) + 1
    return {
        "requests": n,
        "total_cost_usd": round(cost, 6),
        "avg_cost_usd": round(cost / n, 6),
        "counterfactual_single_usd": round(cf, 6),
        "savings_vs_single_pct": round((1 - cost / cf) * 100, 1) if cf > 0 else None,
        "pass_rate": round(sum(1 for r in judged if r["passed"]) / len(judged), 3) if judged else None,
        "escalation_rate": round(sum(1 for r in rows if (r["escalations"] or 0) > 0) / n, 3),
        "latency_ms_avg": round(sum(lat) / n, 1),
        "latency_ms_p50": round(percentile(lat, 0.50), 1),
        "latency_ms_p95": round(percentile(lat, 0.95), 1),
        "tokens_in": sum(r["tokens_in"] or 0 for r in rows),
        "tokens_out": sum(r["tokens_out"] or 0 for r in rows),
        "final_tier_counts": tiers,
    }
