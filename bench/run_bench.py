"""Benchmark runner.
  python bench/run_bench.py --models openai/gpt-6-luna,anthropic/claude-sonnet-5.5 --tasks bugfix,feature
  python bench/run_bench.py --claude --tasks bugfix,feature,image,mcp        # same tasks through Claude Code
Every run gets a fresh directory; success is decided by the deterministic checks in tasks.py."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bench"))
from tasks import TASKS  # noqa: E402


EXTRA: list[str] = []
KEEP_LESSONS = False
KEEP_MEMORY = False


def slug(s: str) -> str:
    return re.sub(r"[^\w.-]+", "_", s)


def workdir(base: Path, label: str, task: str) -> Path:
    """Each run gets its own randomly named parent, so an agent cannot peek at sibling runs."""
    d = Path(tempfile.mkdtemp(prefix="hb_", dir=str(base))) / "work"
    d.mkdir(parents=True)
    (d.parent / "_run.txt").write_text(f"{label} | {task}\n", encoding="utf-8")
    return d


def run_hangar(model: str, task: str, base: Path, workflow: str, planner: str, label: str) -> dict:
    d = workdir(base, label, task)
    spec = TASKS[task][0](d)
    row = {"harness": "hangar", "label": label, "model": model, "workflow": workflow, "task": task}
    if spec is None:
        return {**row, "status": "skipped", "ok": None, "detail": "fixture unavailable on this machine"}
    cmd = [sys.executable, "-m", "hangar", "run", spec["prompt"], "--cwd", str(d), "-m", model, "-w", workflow,
           "--json", "--no-interactive", "--max-cost", "1.5"]
    if not KEEP_LESSONS:
        cmd.append("--no-lessons")                       # benchmark runs must not teach or be taught by each other
    if not KEEP_MEMORY:
        cmd.append("--no-memory")                        # nor carry project facts: every run starts cold
    if planner:
        cmd += ["--planner", planner]
    cmd += EXTRA
    for a in spec.get("attachments", []):
        cmd += ["-a", a]
    if spec.get("answers"):
        (base / "_answers").mkdir(exist_ok=True)         # far from the working directory: the agent must not find it
        af = base / "_answers" / f"{d.parent.name}.json"
        af.write_text(json.dumps(spec["answers"]), encoding="utf-8")
        cmd += ["--answers", str(af)]
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=2400, encoding="utf-8", errors="replace")
        res = json.loads(p.stdout.strip().splitlines()[-1])
    except Exception as e:
        return {**row, "status": "crash", "ok": False, "detail": f"{type(e).__name__}: {e}"[:200], "duration_s": round(time.time() - t0, 1)}
    try:
        ok, detail = TASKS[task][1](d)
    except Exception as e:
        ok, detail = False, f"check crashed: {e}"
    return {**row, "workdir": str(d), "status": res["status"], "ok": bool(ok), "detail": detail, "cost": res["cost"], "prompt": res["prompt"],
            "cached": res["cached"], "completion": res["completion"], "llm_calls": res["llm_calls"], "tool_calls": res["tool_calls"],
            "tool_errors": res["tool_errors"], "questions": res["questions"], "duration_s": res["duration_s"], "session": res["session"],
            "by_model": res["by_model"], "aids": res.get("aids") or {}}


def run_claude(task: str, base: Path, model: str) -> dict:
    d = workdir(base, "claude-code " + model, task)
    spec = TASKS[task][0](d)
    row = {"harness": "claude-code", "label": "claude-code" + (f" ({model})" if model else ""), "model": model or "default", "workflow": "-", "task": task}
    if spec is None:
        return {**row, "status": "skipped", "ok": None, "detail": "fixture unavailable"}
    if spec.get("answers"):
        return {**row, "status": "skipped", "ok": None, "detail": "headless `claude -p` cannot ask the user"}
    prompt = spec["prompt"]
    cmd = ["claude", "-p", prompt, "--output-format", "json", "--permission-mode", "acceptEdits",
           "--allowedTools", "Bash,PowerShell,Read,Edit,Write,Glob,Grep,mcp__vault"]
    if model:
        cmd += ["--model", model]
    if spec.get("mcp"):
        cmd += ["--mcp-config", str(d / ".mcp.json")]
    t0 = time.time()
    try:
        # a clean environment: started from inside another Claude session, the child would inherit that session's
        # host settings (base URL, auth refresh) and fail to authenticate with the CLI's own login
        env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE", "ANTHROPIC"))}
        p = subprocess.run(cmd, cwd=str(d), capture_output=True, text=True, timeout=1800, encoding="utf-8", errors="replace",
                           stdin=subprocess.DEVNULL, shell=False, env=env)
        res = json.loads(p.stdout.strip().splitlines()[-1])
    except Exception as e:
        return {**row, "status": "crash", "ok": False, "detail": f"{type(e).__name__}: {e}"[:200], "duration_s": round(time.time() - t0, 1)}
    if res.get("is_error") and not (res.get("usage") or {}).get("output_tokens"):
        # the model never worked (not logged in, quota, bad flag): that is "did not run", not "did not solve"
        return {**row, "status": "error", "ok": None, "detail": str(res.get("result") or "claude -p failed before any work")[:200],
                "duration_s": round(time.time() - t0, 1)}
    try:
        ok, detail = TASKS[task][1](d)
    except Exception as e:
        ok, detail = False, f"check crashed: {e}"
    u = res.get("usage") or {}
    cached = int(u.get("cache_read_input_tokens") or 0)
    prompt_t = int(u.get("input_tokens") or 0) + cached + int(u.get("cache_creation_input_tokens") or 0)
    return {**row, "status": "error" if res.get("is_error") else "done", "ok": bool(ok), "detail": detail,
            "cost": float(res.get("total_cost_usd") or 0), "prompt": prompt_t, "cached": cached,
            "completion": int(u.get("output_tokens") or 0), "llm_calls": res.get("num_turns"), "tool_calls": None,
            "duration_s": round((res.get("duration_ms") or 0) / 1000, 1), "models": list((res.get("modelUsage") or {}).keys()),
            # what the harness refused to do: a run full of denials measured the setup, not the agent
            "workdir": str(d), "denials": [f"{d.get('tool_name')} {str((d.get('tool_input') or {}).get('file_path') or '')[:160]}".strip()
                        for d in (res.get("permission_denials") or [])]}


def table(rows: list[dict]) -> str:
    out = ["| harness / modelo | workflow | tarefa | ok | custo US$ | tokens in (cache) | out | chamadas LLM | tools | tempo |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if r["status"] in ("skipped", "crash") and "cost" not in r:
            out.append(f"| {r['label']} | {r['workflow']} | {r['task']} | {'—' if r['ok'] is None else '❌'} | | | | | | {r['detail'][:60]} |")
            continue
        out.append(f"| {r['label']} | {r['workflow']} | {r['task']} | {'✅' if r['ok'] else '❌'} | {r['cost']:.5f} | "
                   f"{r['prompt']} ({r['cached']}) | {r['completion']} | {r['llm_calls']} | {r.get('tool_calls') if r.get('tool_calls') is not None else '-'} | {r['duration_s']}s |")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="")
    ap.add_argument("--tasks", default=",".join(TASKS))
    ap.add_argument("--workflow", default="loop")
    ap.add_argument("--planner", default="")
    ap.add_argument("--claude", action="store_true")
    ap.add_argument("--claude-model", default="")
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--tag", default="")
    ap.add_argument("--lessons", action="store_true", help="let runs read/write the lesson library (off by default)")
    ap.add_argument("--memory", action="store_true", help="let runs read/write project memory (off by default)")
    ap.add_argument("--label", default="", help="suffix shown in the results table")
    ap.add_argument("--extra", default="", help="extra flags passed to `hangar run`, e.g. \"--escalate anthropic/claude-sonnet-5.5\"")
    a = ap.parse_args()
    EXTRA[:] = a.extra.split()
    global KEEP_LESSONS, KEEP_MEMORY
    KEEP_LESSONS, KEEP_MEMORY = a.lessons, a.memory
    stamp = time.strftime("%Y%m%d-%H%M%S") + (f"-{a.tag}" if a.tag else "")
    base = Path(os.path.realpath(tempfile.gettempdir())) / "hangar_bench" / stamp
    base.mkdir(parents=True, exist_ok=True)
    tasks = [t for t in a.tasks.split(",") if t in TASKS]
    jobs = []
    for m in [m for m in a.models.split(",") if m]:
        label = (m + (f" [{a.label}]" if a.label else "")) if a.workflow == "loop" else f"{m} [{a.workflow}" + (f", planner {a.planner}" if a.planner else "") + "]"
        jobs += [(run_hangar, (m, t, base, a.workflow, a.planner, label)) for t in tasks]
    if a.claude:
        jobs += [(run_claude, (t, base, a.claude_model)) for t in tasks]
    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        futs = [ex.submit(fn, *args) for fn, args in jobs]
        rows = []
        for f in futs:
            r = f.result()
            rows.append(r)
            print(f"{'OK  ' if r['ok'] else 'SKIP' if r['ok'] is None else 'FAIL'} {r['label']:48s} {r['task']:8s} "
                  f"${r.get('cost', 0):.5f} {r.get('duration_s', 0)}s  {str(r.get('detail', ''))[:70]}", flush=True)
    out = ROOT / "bench" / "results"
    out.mkdir(exist_ok=True)
    (out / f"{stamp}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / f"{stamp}.md").write_text(table(rows) + "\n", encoding="utf-8")
    print(f"\nsaved bench/results/{stamp}.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
