"""Ablation table: the same model and tasks with and without one piece of the harness.

  python bench/run_bench.py --models M --tasks T --tag base
  python bench/run_bench.py --models M --tasks T --tag noskills --label sem-habilidades --extra "--no-skills"
  python bench/run_bench.py --models M --tasks T --tag aids --label com-licoes --lessons --memory
  python bench/compare.py bench/results/*base*.json bench/results/*noskills*.json

One row per label (a plain run is labelled with the model id). A piece that changes neither what is solved nor what it
costs is a piece to delete. `sugeridas` and `carregadas` count runs where a skill was pointed at and where it was
actually loaded: a pass says nothing about a skill the run never opened."""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path


def collect(files: list[str]) -> dict:
    out: dict = {}
    for f in files:
        try:
            rows = json.loads(Path(f).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for r in rows if isinstance(rows, list) else []:
            if not isinstance(r, dict) or r.get("ok") is None or r.get("status") == "crash":
                continue
            a, aids = out.setdefault(r.get("label") or r.get("model") or "?", {"runs": 0, "solved": 0, "cost": 0.0, "time": 0.0,
                                                                              "suggested": 0, "loaded": 0, "lessons": 0}), r.get("aids") or {}
            a["runs"] += 1
            a["solved"] += 1 if r["ok"] else 0
            a["cost"] += float(r.get("cost") or 0)
            a["time"] += float(r.get("duration_s") or 0)
            a["suggested"] += 1 if aids.get("skills_suggested") else 0
            a["loaded"] += 1 if aids.get("skills_loaded") else 0
            a["lessons"] += 1 if aids.get("lessons_shown") else 0
    return out


def table(data: dict) -> str:
    out = ["| variante | resolvidas | custo médio US$ | tempo médio | habilidade sugeridas | carregadas | com lições |", "|---|---|---|---|---|---|---|"]
    for label, a in sorted(data.items()):
        n = a["runs"]
        out.append(f"| {label} | {a['solved']}/{n} | {a['cost'] / n:.5f} | {a['time'] / n:.1f}s | {a['suggested']} | {a['loaded']} | {a['lessons']} |")
    return "\n".join(out)


def main() -> int:
    files = [f for pat in sys.argv[1:] for f in sorted(glob.glob(pat))]
    data = collect(files)
    if not data:
        print("usage: python bench/compare.py <result files>   (no rows found)")
        return 1
    print(table(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
