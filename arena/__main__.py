# 从源码目录外启动 arena CLI。
# 输入：命令行参数；输出：CLI 退出码。
from __future__ import annotations

import sys
from pathlib import Path

if __package__:
    from .cli import main
else:
    project_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(project_root))
    sys.path.insert(0, str(project_root / "src"))
    from arena.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
