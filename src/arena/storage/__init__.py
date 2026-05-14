# 标记旧版存储模块包。
# 输入：无；输出：模块导入结果。
from .run_store import RunStore, load_summary

__all__ = ["RunStore", "load_summary"]
