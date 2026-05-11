from __future__ import annotations

from pathlib import Path
from typing import Any

from arena.security import redact_text


def generate_assessment_markdown_report(summary: dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(redact_text(_render(summary)), encoding="utf-8")
    return output_path


def _render(summary: dict[str, Any]) -> str:
    results = sorted(summary["results"], key=lambda item: item["total_score"], reverse=True)
    tasks = summary["tasks"]
    lines: list[str] = [
        "# 模型能力评估报告",
        "",
        f"- 运行 ID：`{summary['run_id']}`",
        f"- 生成时间：`{summary['created_at']}`",
        f"- 模型组合数：{len(results)}",
        f"- 基准任务数：{len(tasks)}",
        f"- 扰动脚本数：{sum(len(task['mutations']) for task in tasks)}",
        "",
        "> 本报告主分仅来自程序化规则，不包含模型裁判评分。个人生活、事业与成长、人际与关系、资源与风险是评测领域，不代表当前项目替用户做真实决策。",
        "",
        "## 总体结论",
        "",
        summary.get("summary", "没有可用摘要。"),
        "",
        "## 主分排名",
        "",
        "| 排名 | 模型 | Provider | 主分 | 建议角色 | 失败项 |",
        "|---:|---|---|---:|---|---|",
    ]
    for index, result in enumerate(results, start=1):
        roles = "、".join(name for name, _score in _top_items(result["role_fit"], 2)) or "待定"
        failures = "; ".join(result["failures"][:2] + result["errors"][:2]) or "无"
        lines.append(
            f"| {index} | {_cell(result['model_name'])} | {_cell(result['provider'])} | {result['total_score']} | {_cell(roles)} | {_cell(failures)} |"
        )

    lines.extend(["", "## 领域评分", ""])
    domains = sorted({task["domain"] for task in tasks})
    lines.append("| 模型 | " + " | ".join(domains) + " |")
    lines.append("|---" + "|---:" * len(domains) + "|")
    for result in results:
        values = [str(result["domain_scores"].get(domain, 0)) for domain in domains]
        lines.append(f"| {_cell(result['model_name'])} | " + " | ".join(values) + " |")

    lines.extend(["", "## 模型画像", ""])
    for result in results:
        lines.extend(_model_section(result))

    lines.extend(["", "## 任务定义", ""])
    for task in tasks:
        lines.extend(_task_section(task))

    output_dir = str(summary["output_dir"]).replace("\\", "/")
    lines.extend(
        [
            "",
            "## 原始记录文件",
            "",
            f"- 运行摘要：[{output_dir}/summary.json]({output_dir}/summary.json)",
            f"- 完整事件：[{output_dir}/events.jsonl]({output_dir}/events.jsonl)",
            f"- SQLite 汇总：[{output_dir}/summary.sqlite3]({output_dir}/summary.sqlite3)",
        ]
    )

    return "\n".join(lines) + "\n"


def _model_section(result: dict[str, Any]) -> list[str]:
    lines = [
        f"### {result['model_name']}",
        "",
        f"- Alias：`{result['alias']}`",
        f"- Provider：`{result['provider']}`",
        f"- 主分：{result['total_score']}/10",
        f"- 推荐角色：{_inline_scores(result['role_fit'], limit=3)}",
        "",
        "#### Assessment Quality",
        "",
        _score_table(result["quality_scores"]),
        "",
        "#### 程序化规则评分",
        "",
        _score_table(result["rule_scores"]),
        "",
        "#### 行为指纹计数",
        "",
        _score_table(result["behavior_fingerprint"]),
        "",
        "#### 证据摘录",
        "",
    ]
    for item in result["evidence"][:6]:
        lines.append(f"- {item}")
    if result["failures"] or result["errors"]:
        lines.extend(["", "#### 失败项", ""])
        for item in result["failures"] + result["errors"]:
            lines.append(f"- {item}")
    lines.append("")
    return lines


def _task_section(task: dict[str, Any]) -> list[str]:
    lines = [
        f"### {task['title']}",
        "",
        f"- ID：`{task['id']}`",
        f"- 领域：{task['domain']}",
        f"- 题面：{task['prompt']}",
        f"- 显式约束：{', '.join(task['visible_constraints'])}",
        f"- 可接受方案：{', '.join(task['acceptable_options'])}",
        f"- 明显坏方案：{', '.join(task['bad_options'])}",
        "",
        "扰动：",
    ]
    for mutation in task["mutations"]:
        lines.append(f"- `{mutation['id']}` ({mutation['kind']})：{mutation['prompt']}")
    lines.append("")
    return lines


def _score_table(scores: dict[str, Any]) -> str:
    if not scores:
        return "无"
    lines = ["| 项目 | 值 |", "|---|---:|"]
    for name, value in scores.items():
        lines.append(f"| {_cell(str(name))} | {_cell(str(value))} |")
    return "\n".join(lines)


def _inline_scores(scores: dict[str, float], limit: int) -> str:
    items = _top_items(scores, limit)
    if not items:
        return "待定"
    return "、".join(f"{name}({score})" for name, score in items)


def _top_items(scores: dict[str, float], count: int) -> list[tuple[str, float]]:
    return sorted(scores.items(), key=lambda item: item[1], reverse=True)[:count]


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
