from __future__ import annotations

import sys
from pathlib import Path

if __package__:
    from .cli import main
else:
    project_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(project_root / "src"))
    from arena.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
