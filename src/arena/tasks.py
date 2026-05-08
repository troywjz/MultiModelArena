from __future__ import annotations

from .models import Task


DEFAULT_TASKS = [
    Task(
        id="requirements",
        title="需求澄清",
        prompt=(
            "一个团队想开发多模型评测工具。请提炼核心用户、目标、非目标、"
            "验收标准和主要风险。回答需要结构化、可执行。"
        ),
    ),
    Task(
        id="architecture",
        title="工程设计",
        prompt=(
            "请为一个本地运行的多模型评测和 HTML 报告工具设计模块边界、"
            "数据流、存储方案和失败降级策略。"
        ),
    ),
    Task(
        id="review",
        title="质量审查",
        prompt=(
            "下面是一个计划：读取多个模型配置，调用模型，生成评分和报告。"
            "请指出最容易出错的地方、需要的测试和安全约束。"
        ),
    ),
]
