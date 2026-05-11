from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from arena.models import DIMENSIONS
from arena.security import redact_text


def generate_markdown_report(summary: dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(redact_text(_render(summary)), encoding="utf-8")
    return output_path


def _render(summary: dict[str, Any]) -> str:
    results = sorted(summary["results"], key=lambda item: item["average_score"], reverse=True)
    lines: list[str] = [
        "# 多模型评测报告",
        "",
        f"- 运行 ID：`{summary['run_id']}`",
        f"- 生成时间：`{summary['created_at']}`",
        f"- 模型数量：{len(results)}",
        f"- 任务数量：{len(summary['tasks'])}",
        f"- 错误数量：{sum(len(result['errors']) for result in results)}",
        "",
        "## 总体结论",
        "",
        summary.get("consensus", "没有可用结论。"),
        "",
        "## 平均分对比",
        "",
        "| 模型 | Provider | 平均分 | 推荐角色 |",
        "|---|---|---:|---|",
    ]
    for result in results:
        roles = "、".join(result["recommended_roles"]) or "待定"
        lines.append(f"| {_cell(result['model_name'])} | {_cell(result['provider'])} | {result['average_score']} | {_cell(roles)} |")

    lines.extend(["", "## 维度分", ""])
    lines.append("| 模型 | " + " | ".join(DIMENSIONS) + " |")
    lines.append("|---" + "|---:" * len(DIMENSIONS) + "|")
    for result in results:
        scores = [str(result["scores"].get(name, 0)) for name in DIMENSIONS]
        lines.append(f"| {_cell(result['model_name'])} | " + " | ".join(scores) + " |")

    lines.extend(["", "## 模型画像", ""])
    for result in results:
        lines.extend(_model_section(result))

    lines.extend(["", "## 任务证据", ""])
    for task in summary["tasks"]:
        lines.extend(_task_section(task, results))

    return "\n".join(lines) + "\n"


def _model_section(result: dict[str, Any]) -> list[str]:
    lines = [
        f"### {result['model_name']}",
        "",
        f"- Alias：`{result['alias']}`",
        f"- Provider：`{result['provider']}`",
        f"- 平均分：{result['average_score']}/10",
        "",
        "优点：",
    ]
    lines.extend(f"- {item}" for item in result["strengths"])
    lines.append("")
    lines.append("缺点：")
    lines.extend(f"- {item}" for item in result["weaknesses"])
    lines.append("")
    lines.append("证据摘录：")
    lines.extend(f"- {item}" for item in result["evidence"])
    if result["errors"]:
        lines.extend(["", "错误："])
        lines.extend(f"- {item}" for item in result["errors"])
    lines.append("")
    return lines


def _task_section(task: dict[str, Any], results: list[dict[str, Any]]) -> list[str]:
    lines = [
        f"### {task['title']}",
        "",
        f"- ID：`{task['id']}`",
        f"- 题面：{task['prompt']}",
        "",
    ]
    for result in results:
        answer = result["revisions"].get(task["id"]) or result["answers"].get(task["id"])
        if answer:
            lines.extend(
                [
                    f"#### {result['model_name']}",
                    "",
                    answer,
                    "",
                ]
            )
    return lines


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
