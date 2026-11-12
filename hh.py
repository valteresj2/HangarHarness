"""Launcher that works from any directory: `python path/to/hh.py run "task"`."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hangar.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
