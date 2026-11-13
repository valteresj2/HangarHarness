"""Turns benchmark results into the model team the router uses (hangar/roster.json).

  python bench/roster.py                 # read bench/results/*.json, print the table, write hangar/roster.json
  python bench/roster.py --dry           # print only
  python bench/roster.py --out ~/.hangar/roster.json      # a roster of your own runs, used instead of the shipped one

Only plain runs count: workflow `loop`, no variant label. A model enters a role when it solved every run of every task
of the tiers that role needs, with at least --min-runs runs per task; inside a role the order is cost per solved task.

  tier      tasks                          what it shows
  core      bugfix, feature, ask, mcp      everyday coding and tool use
  media     image, audio, video            working with attachments (directly or through the perception model)
  hard      kvstore, pipeline, refactor    multi-file work with hidden tests
  frontier  tinylang                       the hardest task we have: where cheap models start to fail

  role                         needs                         ordered by cost per solved task of
  worker                       core + media + hard           core + media + hard
  light, helper                core                          core
  verifier                     core + hard                   core + hard
  deep, planner, escalation    core + hard + frontier        frontier
  perception                   media, and the model itself   media
                               takes image, audio and video
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TIERS = {"core": ["bugfix", "feature", "ask", "mcp"], "media": ["image", "audio", "video"],
         "hard": ["kvstore", "pipeline", "refactor"], "frontier": ["tinylang"]}
RULES = {  # role: (tiers the model must clear, tiers whose cost orders the role)
    "worker": (["core", "media", "hard"], ["core", "media", "hard"]),
    "light": (["core"], ["core"]),
    "deep": (["core", "hard", "frontier"], ["frontier"]),
    "planner": (["core", "hard", "frontier"], ["frontier"]),
    "verifier": (["core", "hard"], ["core", "hard"]),
    "escalation": (["core", "hard", "frontier"], ["frontier"]),
    "helper": (["core"], ["core"]),
    "perception": (["media"], ["media"]),
}
SENSES = {"image", "audio", "video"}


def collect(files: list[str]) -> dict:
    """{model: {task: {"runs", "solved", "cost"}}} from plain loop runs."""
    out: dict = {}
    for f in files:
        try:
            rows = json.loads(Path(f).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for r in rows:
            if r.get("harness") != "hangar" or r.get("ok") is None or r.get("workflow") != "loop" or r.get("label") != r.get("model"):
                continue
            t = out.setdefault(r["model"], {}).setdefault(r["task"], {"runs": 0, "solved": 0, "cost": 0.0})
            t["runs"] += 1
            t["solved"] += 1 if r["ok"] else 0
            t["cost"] += float(r.get("cost") or 0)
    return out


def score(tasks: dict, tiers: list[str], min_runs: int) -> dict | None:
    """Runs, solved and cost over the tasks of these tiers; None when a task is missing or has too few runs."""
    runs = solved = 0
    cost = 0.0
    for tier in tiers:
        for task in TIERS[tier]:
            t = tasks.get(task)
            if not t or t["runs"] < min_runs:
                return None
            runs, solved, cost = runs + t["runs"], solved + t["solved"], cost + t["cost"]
    return {"runs": runs, "solved": solved, "cost_per_solved": round(cost / solved, 5) if solved else None}


def build(data: dict, min_runs: int, modalities: dict) -> dict:
    roles: dict = {}
    for role, (need, order) in RULES.items():
        rows = []
        for model, tasks in data.items():
            cleared, ranked = score(tasks, need, min_runs), score(tasks, order, min_runs)
            if not cleared or not ranked or cleared["solved"] != cleared["runs"]:
                continue
            if role == "perception" and not SENSES <= set(modalities.get(model) or []):
                continue
            rows.append({"model": model, "solved": cleared["solved"], "runs": cleared["runs"],
                         "cost_per_solved": ranked["cost_per_solved"], "cleared": need, "ranked_on": order})
        roles[role] = sorted(rows, key=lambda r: (r["cost_per_solved"], r["model"]))
    return roles


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=str(ROOT / "bench" / "results" / "*.json"))
    ap.add_argument("--out", default=str(ROOT / "hangar" / "roster.json"))
    ap.add_argument("--min-runs", type=int, default=2)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    files = sorted(glob.glob(a.results))
    data = collect(files)
    if not data:
        print(f"no plain loop runs found in {a.results}")
        return 1
    from hangar import config
    from hangar.models import Catalog
    known = Catalog(config.load(ROOT))._load()
    modalities = {m: (known.get(m) or {}).get("modalities") or [] for m in data}
    out = Path(a.out).expanduser()
    if not known:                                        # offline: keep the senses we already knew
        try:
            modalities = json.loads(out.read_text(encoding="utf-8")).get("modalities") or {}
        except (OSError, ValueError):
            modalities = {}
    roles = build(data, a.min_runs, modalities)
    for role, rows in roles.items():
        print(f"{role:11s} " + (" > ".join(f"{r['model']} (${r['cost_per_solved']:.4f}, {r['solved']}/{r['runs']})" for r in rows) or "— nobody cleared it"))
    empty = [r for r, rows in roles.items() if not rows]
    if empty:
        print(f"\nnot written: no model cleared {', '.join(empty)}. Run those tiers (or lower --min-runs).")
        return 1
    if a.dry:
        return 0
    doc = {"generated": time.strftime("%Y-%m-%d"), "min_runs": a.min_runs, "result_files": len(files), "tiers": TIERS,
           "rules": {role: {"cleared": need, "ranked_on": order} for role, (need, order) in RULES.items()},
           "modalities": {m: sorted(v) for m, v in sorted(modalities.items()) if v}, "roles": roles}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
