#!/usr/bin/env python3
"""
Experiment runner for Router + Cascade Gateway eval suite.
Streams Aider output live so you can watch every edit as it happens.

Usage:
  python runner.py --pilot                        # 3 tasks x 2 modes (quick sanity check)
  python runner.py --tasks e01 e02 m06 --runs 3  # specific tasks, 3 runs each
  python runner.py --all --runs 3                 # full 90-run experiment
  python runner.py --tuning --runs 1              # tuning set only
"""
import argparse, csv, json, os, pathlib, shutil, subprocess, sys, tempfile, time
from datetime import datetime

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.rule import Rule
    console = Console()
    HAS_RICH = True
except ImportError:
    console = None
    HAS_RICH = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# ─── Configuration ────────────────────────────────────────────────────────────
GATEWAY        = os.getenv("GATEWAY_URL", "http://localhost:8001")
EVAL_ROOT      = pathlib.Path(__file__).resolve().parent
RESULTS_DIR    = EVAL_ROOT / "results"
AIDER_TIMEOUT  = int(os.getenv("AIDER_TIMEOUT", "180"))   # seconds per run
PAUSE_BETWEEN  = 3                                          # seconds between runs
RESULTS_DIR.mkdir(exist_ok=True)
TIMESTAMP      = datetime.now().strftime("%Y%m%d_%H%M%S")
RESULTS_CSV    = RESULTS_DIR / f"results_{TIMESTAMP}.csv"
LOG_FILE       = RESULTS_DIR / f"log_{TIMESTAMP}.txt"

CSV_COLS = [
    "run_id", "task", "difficulty", "mode", "run_num",
    "solved", "wall_time_s", "gateway_requests", "escalations",
    "cost_usd", "tokens_in", "tokens_out", "wasted_cost_usd",
    "aider_exit_code", "timestamp",
]

TUNING_TASKS  = None   # filled from task_index.json
HELD_OUT_TASKS = None

# ─── Display helpers ──────────────────────────────────────────────────────────
def _log(msg, style=None, file=None):
    if console:
        console.print(msg, style=style)
    else:
        print(msg)
    if file:
        file.write(str(msg) + "\n")
        file.flush()

def banner(text, style="bold blue"):
    if console:
        console.print(Panel(f"[bold]{text}[/bold]", style=style, padding=(0, 2)))
    else:
        print(f"\n{'═'*64}\n  {text}\n{'═'*64}")

def rule(text=""):
    if console:
        console.print(Rule(text, style="dim"))
    else:
        print(f"{'─'*64}" + (f" {text}" if text else ""))

def ok(text):
    sym = "✅" if sys.platform != "win32" or os.getenv("WT_SESSION") else "[PASS]"
    _log(f"{sym} {text}", style="bold green")

def err(text):
    sym = "❌" if sys.platform != "win32" or os.getenv("WT_SESSION") else "[FAIL]"
    _log(f"{sym} {text}", style="bold red")

def info(text):
    sym = "ℹ" if sys.platform != "win32" or os.getenv("WT_SESSION") else "[INFO]"
    _log(f"{sym}  {text}", style="cyan")

def warn(text):
    sym = "⚠" if sys.platform != "win32" or os.getenv("WT_SESSION") else "[WARN]"
    _log(f"{sym}  {text}", style="yellow")

# ─── Core helpers ─────────────────────────────────────────────────────────────
def run_pytest(repo_path, timeout=30):
    """Run pytest in repo_path. Returns (passed: bool, output: str)."""
    # -B prevents writing/reading stale .pyc bytecode
    result = subprocess.run(
        [sys.executable, "-B", "-m", "pytest", str(repo_path), "-v", "--tb=short", "-q",
         "--no-header", "-p", "no:cacheprovider"],
        cwd=repo_path,
        capture_output=True, text=True, timeout=timeout,
    )
    return result.returncode == 0, (result.stdout + result.stderr)

def run_aider_streaming(task_name, mode, repo_path, instruction, logfile, timeout=AIDER_TIMEOUT):
    """
    Run Aider with output streamed line-by-line to the terminal.
    Returns (exit_code: int, elapsed_seconds: float).
    """
    env = os.environ.copy()
    env["OPENAI_API_BASE"] = f"{GATEWAY}/v1"
    env["OPENAI_API_KEY"]  = "dummy"

    source_files = sorted([
        str(f) for f in repo_path.glob("*.py")
        if not f.name.startswith("test_")
    ])

    cmd = [
        sys.executable, "-m", "aider",
        "--model",   f"openai/{mode}",
        "--no-git",
        "--yes",
        "--no-stream",
        "--no-show-model-warnings",
        "--message", instruction.strip(),
    ] + source_files

    if console:
        console.rule(f"[bold cyan]Aider [{mode.upper()}] — {task_name}[/bold cyan]")
        console.print(f"  [dim]Files: {[pathlib.Path(f).name for f in source_files]}[/dim]")
        console.print(f"  [dim]Timeout: {timeout}s | Gateway: {GATEWAY}[/dim]")
        console.rule()
    else:
        print(f"\n--- Aider [{mode}] on {task_name} ---")
        print(f"    Files: {[pathlib.Path(f).name for f in source_files]}")

    start = time.time()
    aider_exit = -1

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=repo_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )

        while True:
            line = proc.stdout.readline()
            if line == "" and proc.poll() is not None:
                break
            if line:
                stripped = line.rstrip()
                # Print live — this is what the user sees
                if console:
                    console.print(f"  [dim]│[/dim] {stripped}")
                else:
                    print(f"  │ {stripped}")
                logfile.write(stripped + "\n")
                logfile.flush()

            if time.time() - start > timeout:
                proc.kill()
                warn(f"TIMEOUT after {timeout}s — Aider killed")
                logfile.write(f"[TIMEOUT after {timeout}s]\n")
                break

        proc.wait(timeout=5)
        aider_exit = proc.returncode if proc.returncode is not None else 0

    except FileNotFoundError:
        err("Aider not found. Run: pip install aider-chat")
    except Exception as exc:
        err(f"Aider error: {exc}")
        logfile.write(f"[ERROR: {exc}]\n")

    elapsed = time.time() - start
    if console:
        console.rule()
    return aider_exit, elapsed

def get_traces_in_window(start_ts, end_ts, mode, buffer=5.0):
    """Fetch gateway traces that fall within [start_ts-buffer, end_ts+buffer] and match mode."""
    if not HAS_REQUESTS:
        return []
    try:
        resp = requests.get(f"{GATEWAY}/api/traces", timeout=10)
        if resp.status_code != 200:
            return []
        data = resp.json()
        traces = data if isinstance(data, list) else list(data.values())
        return [
            t for t in traces
            if t.get("mode") == mode
            and (start_ts - buffer) <= float(t.get("ts", 0)) <= (end_ts + buffer)
        ]
    except Exception as exc:
        warn(f"Could not fetch traces: {exc}")
        return []

def trace_stats(traces):
    """Aggregate trace data into summary stats."""
    n       = len(traces)
    esc     = sum(int(t.get("escalations", 0)) for t in traces)
    cost    = sum(float(t.get("cost_usd", 0) or 0) for t in traces)
    tin     = sum(int(t.get("tokens_in",  0) or 0) for t in traces)
    tout    = sum(int(t.get("tokens_out", 0) or 0) for t in traces)
    wasted  = sum(float(t.get("cost_usd", 0) or 0) for t in traces if not t.get("passed"))
    return n, esc, cost, tin, tout, wasted

# ─── Single run ───────────────────────────────────────────────────────────────
def run_one(task_name, mode, run_num, writer, logfile):
    task_dir  = EVAL_ROOT / "tasks" / task_name
    diff      = (task_dir / "difficulty.txt").read_text(encoding="utf-8").strip()
    instr     = (task_dir / "instruction.txt").read_text(encoding="utf-8").strip()
    repo_src  = task_dir / "repo"
    run_id    = f"{task_name}_{mode}_{run_num}"

    banner(f"[{run_num}]  {task_name}  │  mode={mode}  │  difficulty={diff}", style="bold blue")

    # Fresh temporary copy of the repo
    tmp = pathlib.Path(tempfile.mkdtemp(prefix=f"eval_{task_name}_r{run_num}_"))
    for f in repo_src.glob("*.py"):
        shutil.copy2(f, tmp / f.name)
    info(f"Fresh repo: {tmp}")

    # Pre-check: tests must fail
    info("Pre-check → tests should FAIL before fix …")
    passed_before, pre_out = run_pytest(tmp)
    if passed_before:
        warn("Tests already pass — skipping this run (task may be trivial or env issue)")
        shutil.rmtree(tmp, ignore_errors=True)
        return False
    ok("Pre-check passed — tests are failing as expected")

    # Aider run
    start_ts = time.time()
    aider_exit, wall_time = run_aider_streaming(task_name, mode, tmp, instr, logfile)
    end_ts = time.time()

    # Post-check: did Aider fix it?
    info("Post-check → running tests after Aider …")
    passed_after, post_out = run_pytest(tmp)

    if passed_after:
        ok(f"SOLVED ✓  ({wall_time:.1f}s)")
    else:
        err(f"NOT SOLVED  ({wall_time:.1f}s)")

    # Show test output (last 40 lines)
    test_lines = post_out.strip().splitlines()
    shown = test_lines[-40:] if len(test_lines) > 40 else test_lines
    for line in shown:
        style = "green" if "PASSED" in line else ("red" if "FAILED" in line or "ERROR" in line else "dim")
        if console:
            console.print(f"  {line}", style=style)
        else:
            print(f"  {line}")
    logfile.write(post_out + "\n")

    # Traces
    info("Fetching gateway traces …")
    traces = get_traces_in_window(start_ts, end_ts, mode)
    n_req, esc, cost, tin, tout, wasted = trace_stats(traces)
    info(f"Traces: {n_req} requests | {esc} escalations | ${cost:.6f} cost | {tin+tout} tokens")

    # CSV
    row = {
        "run_id":          run_id,
        "task":            task_name,
        "difficulty":      diff,
        "mode":            mode,
        "run_num":         run_num,
        "solved":          "yes" if passed_after else "no",
        "wall_time_s":     round(wall_time, 1),
        "gateway_requests":n_req,
        "escalations":     esc,
        "cost_usd":        round(cost, 8),
        "tokens_in":       tin,
        "tokens_out":      tout,
        "wasted_cost_usd": round(wasted, 8),
        "aider_exit_code": aider_exit,
        "timestamp":       datetime.fromtimestamp(start_ts).isoformat(),
    }
    writer.writerow(row)

    shutil.rmtree(tmp, ignore_errors=True)
    return passed_after

# ─── Verification helpers ─────────────────────────────────────────────────────
def verify_task(task_name):
    """
    Checks:
      1. Tests fail on the buggy repo.
      2. Tests pass when the reference solution is applied.
    Returns (pre_fails: bool, post_passes: bool).
    """
    task_dir = EVAL_ROOT / "tasks" / task_name
    sol_dir  = EVAL_ROOT / "solutions" / task_name

    tmp = pathlib.Path(tempfile.mkdtemp(prefix=f"verify_{task_name}_"))
    # Copy buggy repo
    for f in (task_dir / "repo").glob("*.py"):
        shutil.copy(f, tmp / f.name)
    before_ok, _ = run_pytest(tmp)

    # Clear pycache if created
    for pyc in tmp.glob("**/__pycache__"):
        shutil.rmtree(pyc, ignore_errors=True)

    # Overlay solution files (keep test file from repo)
    for f in sol_dir.glob("*.py"):
        shutil.copy(f, tmp / f.name)
    after_ok, _ = run_pytest(tmp)

    shutil.rmtree(tmp, ignore_errors=True)
    return (not before_ok), after_ok

# ─── Summary table ────────────────────────────────────────────────────────────
def print_summary(results_csv_path):
    rows = []
    with open(results_csv_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return

    if console:
        t = Table(title="📊 Results Summary", show_lines=True)
        t.add_column("Task",       style="cyan",    no_wrap=True)
        t.add_column("Difficulty", style="yellow")
        t.add_column("Mode",       style="magenta")
        t.add_column("Run",        justify="right")
        t.add_column("Solved",     justify="center")
        t.add_column("Cost $",     justify="right")
        t.add_column("Requests",   justify="right")
        t.add_column("Escl.",      justify="right")
        t.add_column("Time (s)",   justify="right")
        for r in rows:
            solved_str = "[green]✅ yes[/green]" if r["solved"] == "yes" else "[red]❌ no[/red]"
            t.add_row(r["task"], r["difficulty"], r["mode"], r["run_num"],
                      solved_str, r["cost_usd"], r["gateway_requests"],
                      r["escalations"], r["wall_time_s"])
        console.print(t)
    else:
        hdr = f"{'task':<30} {'diff':<8} {'mode':<8} {'run':<4} {'solved':<8} {'cost':>10} {'reqs':>5} {'esc':>5} {'time':>8}"
        print("\n" + hdr)
        print("─" * len(hdr))
        for r in rows:
            print(f"{r['task']:<30} {r['difficulty']:<8} {r['mode']:<8} {r['run_num']:<4} "
                  f"{r['solved']:<8} {float(r['cost_usd']):>10.6f} {r['gateway_requests']:>5} "
                  f"{r['escalations']:>5} {r['wall_time_s']:>8}")

# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    p = argparse.ArgumentParser(description="Router+Cascade Gateway eval runner")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--pilot",   action="store_true", help="Pilot: 1 easy+1 medium+1 hard, 1 run each mode")
    g.add_argument("--verify",  action="store_true", help="Verify all tasks (fail before, pass after solution)")
    g.add_argument("--tuning",  action="store_true", help="Run tuning set only (first 5 tasks)")
    g.add_argument("--held",    action="store_true", help="Run held-out set only (tasks 6-15)")
    g.add_argument("--all",     action="store_true", help="Run all 15 tasks")
    g.add_argument("--tasks",   nargs="+",           help="Specific task name prefixes e.g. e01 m06 h12")
    p.add_argument("--modes",   nargs="+", default=["single", "auto"], help="Modes (default: single auto)")
    p.add_argument("--runs",    type=int,  default=1,  help="Runs per task per mode (default: 1)")
    p.add_argument("--threshold", type=float, default=None, help="Override gateway routing threshold")
    args = p.parse_args()

    # Load task index
    index_path = EVAL_ROOT / "task_index.json"
    if not index_path.exists():
        err("task_index.json not found — run generate_tasks.py first")
        sys.exit(1)
    index = json.loads(index_path.read_text(encoding="utf-8"))
    all_names = [t["name"] for t in index]
    tuning_tasks  = all_names[:5]
    held_out_tasks = all_names[5:]

    # ── verify mode ──────────────────────────────────────────────────────────
    if args.verify:
        banner("Task Verification Suite", style="bold yellow")
        all_ok = True
        for name in all_names:
            pre_fails, post_passes = verify_task(name)
            status = "✅" if (pre_fails and post_passes) else "❌"
            detail = ""
            if not pre_fails:
                detail += " [WARN: tests pass on buggy code!]"
            if not post_passes:
                detail += " [WARN: tests fail on solution!]"
            if console:
                style = "green" if (pre_fails and post_passes) else "red"
                console.print(f"  {status} {name}{detail}", style=style)
            else:
                print(f"  {status} {name}{detail}")
            if not (pre_fails and post_passes):
                all_ok = False
        banner("All tasks valid ✅" if all_ok else "Some tasks have issues ❌",
               style="bold green" if all_ok else "bold red")
        return

    # ── select tasks ─────────────────────────────────────────────────────────
    if args.pilot:
        easy   = next((n for n in all_names if n.startswith("e")), None)
        medium = next((n for n in all_names if n.startswith("m")), None)
        hard   = next((n for n in all_names if n.startswith("h")), None)
        selected = [t for t in [easy, medium, hard] if t]
        args.runs = 1
    elif args.tuning:
        selected = tuning_tasks
    elif args.held:
        selected = held_out_tasks
    elif args.all:
        selected = all_names
    elif args.tasks:
        selected = [n for n in all_names if any(n.startswith(a) for a in args.tasks)]
    else:
        p.print_help()
        sys.exit(0)

    if not selected:
        err("No matching tasks found")
        sys.exit(1)

    modes  = args.modes
    n_runs = args.runs
    total  = len(selected) * len(modes) * n_runs

    # ── optional: set gateway threshold ─────────────────────────────────────
    if args.threshold is not None and HAS_REQUESTS:
        try:
            r = requests.put(f"{GATEWAY}/api/config",
                             json={"threshold": args.threshold},
                             headers={"X-Admin-Key": os.getenv("ADMIN_KEY", "change-me")},
                             timeout=5)
            info(f"Gateway threshold set to {args.threshold} → {r.status_code}")
        except Exception as exc:
            warn(f"Could not set threshold: {exc}")

    banner(
        f"🧪 Eval Suite\n"
        f"   Tasks: {len(selected)}  │  Modes: {modes}  │  Runs each: {n_runs}  │  Total: {total}\n"
        f"   Results: {RESULTS_CSV}\n"
        f"   Log:     {LOG_FILE}"
    )

    run_count = 0
    with open(RESULTS_CSV, "w", newline="", encoding="utf-8") as csv_f, \
         open(LOG_FILE,    "w",             encoding="utf-8") as log_f:

        writer = csv.DictWriter(csv_f, fieldnames=CSV_COLS)
        writer.writeheader()

        for task_name in selected:
            for run_num in range(1, n_runs + 1):
                # Alternate mode order to avoid ordering bias
                ordered_modes = modes if run_num % 2 == 1 else list(reversed(modes))
                for mode in ordered_modes:
                    run_count += 1
                    _log(f"\n[{run_count}/{total}]", style="bold white")
                    log_f.write(f"\n{'='*64}\n[{run_count}/{total}] {task_name} {mode} run{run_num}\n")

                    try:
                        run_one(task_name, mode, run_num, writer, log_f)
                        csv_f.flush()
                    except KeyboardInterrupt:
                        warn("\nInterrupted by user. Saving results so far …")
                        break
                    except Exception as exc:
                        err(f"Run failed with exception: {exc}")
                        import traceback
                        traceback.print_exc()
                        log_f.write(f"[EXCEPTION: {exc}]\n")

                    if run_count < total:
                        info(f"Pausing {PAUSE_BETWEEN}s before next run …")
                        time.sleep(PAUSE_BETWEEN)

    rule()
    print_summary(RESULTS_CSV)
    banner(f"Done! Results saved to:\n  {RESULTS_CSV}", style="bold green")

if __name__ == "__main__":
    main()

