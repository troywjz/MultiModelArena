from __future__ import annotations

from pathlib import Path

_src_arena = Path(__file__).resolve().parent.parent / "src" / "arena"
if _src_arena.exists():
    __path__.append(str(_src_arena))
