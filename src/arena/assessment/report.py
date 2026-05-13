from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from arena.security import redact_text

from .diagnostics import DIAGNOSTIC_DIMENSIONS, analyze_response
from .models import format_model_display_name


def generate_assessment_markdown_report(summary: dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(redact_text(_render(summary)), encoding="utf-8")
    return output_path


def _render(summary: dict[str, Any]) -> str:
    tasks = summary["tasks"]
    results = sorted(_with_legacy_diagnostics(summary["results"], tasks), key=lambda item: item["total_score"], reverse=True)
    summary_text = _build_report_summary(results, summary.get("summary", "没有可用摘要。"))
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
        model_name = _display_model_name(result)
        lines.append(
            f"| {index} | {_cell(model_name)} | {_cell(result['provider'])} | {result['total_score']} | {_cell(roles)} | {_cell(failures)} |"
        )

    lines.extend(["", "## 领域评分", ""])
    domains = sorted({task["domain"] for task in tasks})
    lines.append("| 模型 | " + " | ".join(domains) + " |")
    lines.append("|---" + "|---:" * len(domains) + "|")
    for result in results:
        values = [str(result["domain_scores"].get(domain, 0)) for domain in domains]
        lines.append(f"| {_cell(_display_model_name(result))} | " + " | ".join(values) + " |")

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


def _with_legacy_diagnostics(results: list[dict[str, Any]], tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """为旧 summary 补算响应拆解指标。

    早期运行的 summary.json 里没有 diagnostic_scores，但它已经保存了每轮 parsed JSON。
    这里只读取本地历史结果并重新跑规则分析，不会访问模型 API，也不会增加任何调用成本。
    这样用户可以对旧评测结果重新生成更详细的报告。
    """
    task_map = {task["id"]: _task_view(task) for task in tasks}
    enriched: list[dict[str, Any]] = []
    for result in results:
        item = dict(result)
        if item.get("diagnostic_scores") or not isinstance(item.get("responses"), list):
            enriched.append(item)
            continue
        diagnostic_hits: dict[str, list[float]] = defaultdict(list)
        method_fingerprint: dict[str, float] = defaultdict(float)
        diagnostic_notes: list[str] = []
        baselines: dict[str, dict[str, Any]] = {}
        for response in item["responses"]:
            if not isinstance(response, dict) or not isinstance(response.get("parsed"), dict):
                continue
            task = task_map.get(response.get("task_id", ""))
            if task is None:
                continue
            phase_id = str(response.get("phase_id", "baseline"))
            parsed = response["parsed"]
            if phase_id == "baseline":
                baselines[str(response.get("task_id", ""))] = parsed
            # 拆解逻辑集中在 diagnostics.py；报告层只负责对旧数据补算、聚合并展示。
            # baseline 用作扰动轮次的对照，以判断模型是否随新增信息调整建议。
            diagnostics = analyze_response(parsed, task, phase_id=phase_id, baseline=baselines.get(str(response.get("task_id", ""))))
            for key, value in diagnostics.scores.items():
                diagnostic_hits[key].append(value)
            for key, value in diagnostics.method_counts.items():
                method_fingerprint[key] += value
            for note in diagnostics.notes:
                if note not in diagnostic_notes and len(diagnostic_notes) < 8:
                    diagnostic_notes.append(note)
        item["diagnostic_scores"] = {key: _to_ten(_average(values)) for key, values in diagnostic_hits.items()}
        item["method_fingerprint"] = dict(method_fingerprint)
        item["diagnostic_notes"] = diagnostic_notes
        enriched.append(item)
    return enriched


def _task_view(task: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(
        visible_constraints=task.get("visible_constraints", []),
        hidden_values=task.get("hidden_values", {}),
        acceptable_options=task.get("acceptable_options", []),
    )


def _build_report_summary(results: list[dict[str, Any]], fallback: str) -> str:
    if not results:
        return _normalize_report_wording(fallback)
    lines = ["本次总评分仅来自程序化规则，不包含模型裁判。"]
    for result in results:
        lines.append(
            f"{_display_model_name(result)}: 总分 {result['total_score']}/10，建议角色 {_role_names(result, 2)}"
        )
    return "\n".join(lines)


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
    display_name = _display_model_name(result)
    lines = [
        f"### {display_name}",
        "",
        f"- Alias：`{result['alias']}`",
        f"- Provider：`{result['provider']}`",
        f"- Temperature：{_temperature_text(result)}",
        f"- 总评分：{result['total_score']}/10",
        f"- 推荐角色：{_role_scores(result, limit=3)}",
        "",
        "#### Assessment Quality",
        "",
        _score_table(result.get("quality_scores", {})),
        "",
        "#### 响应拆解评估",
        "",
        _diagnostic_table(result.get("diagnostic_scores", {})),
        "",
        "#### 方法与分析角度指纹",
        "",
        _score_table(result.get("method_fingerprint", {})),
        "",
        "#### 拆解证据",
        "",
        _diagnostic_notes(result),
        "",
        "#### 程序化规则评分",
        "",
        _score_table(result.get("rule_scores", {})),
        "",
        "#### 行为指纹计数",
        "",
        _score_table(result.get("behavior_fingerprint", {})),
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


def _diagnostic_table(scores: dict[str, Any]) -> str:
    # 报告里的“响应拆解评估”把英文内部指标转成中文解释，方便人工复核。
    # 分数来自 diagnostics.py 的结构化规则，不来自模型自评或模型裁判。
    if not scores:
        return "无"
    lines = ["| 拆解项 | 值 | 说明 |", "|---|---:|---|"]
    descriptions = {
        "constraint_grounding": "是否抓住题面约束和具体数字。",
        "value_decomposition": "是否拆出用户价值、偏好和目标张力。",
        "tradeoff_reasoning": "是否通过利弊、排序或成本收益做权衡。",
        "information_seeking": "是否识别假设、澄清问题和信息缺口。",
        "risk_reversibility": "是否提出风险、可逆性和复盘条件。",
        "execution_specificity": "行动是否具体到时间、指标或下一步。",
        "adaptation_to_change": "扰动后是否调整建议并避开坏方案。",
        "calibration_boundary": "是否给出置信度和专业边界。",
        "method_diversity": "是否使用多种分析方法而非单一结论。",
    }
    for key, value in scores.items():
        label = DIAGNOSTIC_DIMENSIONS.get(key, key)
        lines.append(f"| {_cell(label)} | {_cell(str(value))} | {_cell(descriptions.get(key, ''))} |")
    return "\n".join(lines)


def _diagnostic_notes(result: dict[str, Any]) -> str:
    # “拆解证据”只放简短解释，避免把完整模型回答塞进报告。
    # 完整回答仍保存在 runs/<run_id>/events.jsonl 和 summary.json 里。
    notes = result.get("diagnostic_notes", [])
    if not notes:
        return "无"
    return "\n".join(f"- {item}" for item in notes[:6])


def _inline_scores(scores: dict[str, float], limit: int) -> str:
    items = _top_items(scores, limit)
    if not items:
        return "待定"
    return "、".join(f"{name}({score})" for name, score in items)


def _top_items(scores: dict[str, float], count: int) -> list[tuple[str, float]]:
    return sorted(scores.items(), key=lambda item: item[1], reverse=True)[:count]


def _average(values: list[float]) -> float:
    clean = [value for value in values if value is not None]
    if not clean:
        return 0.0
    return sum(clean) / len(clean)


def _to_ten(value: float) -> float:
    return round(max(0.0, min(1.0, value)) * 10, 2)


def _display_model_name(result: dict[str, Any]) -> str:
    return format_model_display_name(result["model_name"], result.get("temperature"), result.get("alias", ""))


def _temperature_text(result: dict[str, Any]) -> str:
    display_name = _display_model_name(result)
    if display_name == result["model_name"]:
        return "未设置"
    return display_name.removeprefix(result["model_name"]).strip("（）").replace("温度 ", "")


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
