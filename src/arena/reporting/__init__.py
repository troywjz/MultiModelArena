# 导出旧版报告生成函数。
# 输入：无；输出：可导入的报告接口。
from .markdown_report import generate_markdown_report

__all__ = ["generate_markdown_report"]
