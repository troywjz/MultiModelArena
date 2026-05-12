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
    summary_text = _normalize_report_wording(summary.get("summary", "没有可用摘要。"))
    validity_notice = _validity_notice(results)
    lines: list[str] = [
        "# 模型能力评估报告",
        "",
        f"- 运行 ID：`{summary['run_id']}`",
        f"- 生成时间：`{summary['created_at']}`",
        f"- 模型组合数：{len(results)}",
        f"- 基准任务数：{len(tasks)}",
        f"- 扰动脚本数：{sum(len(task['mutations']) for task in tasks)}",
        "",
        "> 本报告总评分仅来自程序化规则，不包含模型裁判评分。个人生活、事业与成长、人际与关系、资源与风险是评测领域，不代表当前项目替用户做真实决策。",
        "",
        "## 总体结论",
        "",
        summary_text,
    ]
    if validity_notice:
        lines.extend(["", "## 有效性提示", "", validity_notice])
    lines.extend(
        [
            "",
            "## 总评分排名",
            "",
            "| 排名 | 模型 | Provider | 总评分 | 建议角色 | 失败项 |",
            "|---:|---|---|---:|---|---|",
        ]
    )
    for index, result in enumerate(results, start=1):
        roles = _role_names(result, 2)
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


def _normalize_report_wording(text: str) -> str:
    return text.replace("本次主分", "本次总评分").replace("进入主分", "计入总评分")


def _validity_notice(results: list[dict[str, Any]]) -> str:
    total, valid = _response_counts(results)
    if total == 0:
        return ""
    if valid == 0:
        return "> 本次运行没有任何可解析的 JSON 响应，因此总评分、排名和角色建议不能作为模型能力结论，只能用于诊断模型输出协议或截断问题。"
    if valid < total:
        failed = total - valid
        return f"> 本次运行有 {failed}/{total} 条响应未能解析为 JSON。总评分仅基于成功解析的 {valid} 条响应，比较结论需要结合失败项谨慎解读。"
    return ""


def _response_counts(results: list[dict[str, Any]]) -> tuple[int, int]:
    total = 0
    valid = 0
    for result in results:
        responses = result.get("responses", [])
        if not isinstance(responses, list):
            continue
        total += len(responses)
        valid += sum(1 for response in responses if isinstance(response, dict) and response.get("parsed") is not None)
    return total, valid


def _has_valid_responses(result: dict[str, Any]) -> bool:
    responses = result.get("responses")
    if not isinstance(responses, list) or not responses:
        return True
    return any(isinstance(response, dict) and response.get("parsed") is not None for response in responses)


def _role_names(result: dict[str, Any], limit: int) -> str:
    if not _has_valid_responses(result):
        return "待定"
    return "、".join(name for name, _score in _top_items(result["role_fit"], limit)) or "待定"


def _role_scores(result: dict[str, Any], limit: int) -> str:
    if not _has_valid_responses(result):
        return "待定"
    return _inline_scores(result["role_fit"], limit=limit)


def _model_section(result: dict[str, Any]) -> list[str]:
    lines = [
        f"### {result['model_name']}",
        "",
        f"- Alias：`{result['alias']}`",
        f"- Provider：`{result['provider']}`",
        f"- 总评分：{result['total_score']}/10",
        f"- 推荐角色：{_role_scores(result, limit=3)}",
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
