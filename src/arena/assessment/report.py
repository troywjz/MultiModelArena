from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import re
from types import SimpleNamespace
from typing import Any

from arena.security import redact_text

from .diagnostics import DIAGNOSTIC_DIMENSIONS, analyze_response
from .models import AssessmentModelResult, AssessmentMutation, AssessmentPhaseResponse, AssessmentTask, format_model_display_name
from .scoring import score_assessment_result


QUALITY_SCORE_LABELS = {
    "Helpful Frame": "有效问题框架（Helpful Frame）",
    "Clear Values": "清晰价值识别（Clear Values）",
    "Creative Alternatives": "创造性备选方案（Creative Alternatives）",
    "Useful Information": "有用信息利用（Useful Information）",
    "Sound Reasoning": "稳健推理（Sound Reasoning）",
    "Commitment to Follow Through": "执行承诺（Commitment to Follow Through）",
}

RULE_SCORE_LABELS = {
    "json_complete": "JSON 完整性（json_complete）",
    "alternative_count": "备选方案数量（alternative_count）",
    "bad_option_avoidance": "坏方案规避（bad_option_avoidance）",
    "professional_boundary": "专业边界（professional_boundary）",
    "action_plan": "行动计划（action_plan）",
    "acceptable_option_match": "可接受方案匹配（acceptable_option_match）",
    "mutation_response": "扰动响应（mutation_response）",
}

BEHAVIOR_LABELS = {
    "clarifying_questions": "澄清问题数（clarifying_questions）",
    "alternative_count": "备选方案数（alternative_count）",
    "creative_option_count": "创造性方案数（creative_option_count）",
    "constraint_mentions": "约束命中数（constraint_mentions）",
    "risk_count": "风险条目数（risk_count）",
    "action_count": "行动条目数（action_count）",
    "boundary_present_count": "边界提示次数（boundary_present_count）",
    "mutation_response_count": "有效扰动响应次数（mutation_response_count）",
    "bad_option_hit_count": "坏方案命中次数（bad_option_hit_count）",
    "json_valid_count": "合法 JSON 响应数（json_valid_count）",
}

METHOD_FINGERPRINT_LABELS = {
    "阶段门/试点验证": "阶段门/试点验证",
    "权衡矩阵/优先级": "权衡矩阵/优先级",
    "约束检查": "约束检查",
    "风险复盘": "风险复盘",
    "相关方对齐": "相关方对齐",
    "信息缺口管理": "信息缺口管理",
    "用户价值识别": "用户价值识别",
    "执行计划": "执行计划",
}

PROVIDER_LABELS = {
    "fake": "离线模拟（fake）",
    "openai_compatible": "OpenAI 兼容接口（openai_compatible）",
    "anthropic_compatible": "Anthropic 兼容接口（anthropic_compatible）",
}

MUTATION_KIND_LABELS = {
    "value_shift": "价值变化（value_shift）",
    "new_evidence": "新增证据（new_evidence）",
}

PHASE_LABELS = {
    "baseline": "基准回答（baseline）",
    "prefer_quiet": "偏好安静扰动（prefer_quiet）",
    "companion_budget_4000": "同行预算 4000 元扰动（companion_budget_4000）",
    "mortgage_pressure_high": "房贷压力高扰动（mortgage_pressure_high）",
    "learning_time_limited": "学习时间有限扰动（learning_time_limited）",
    "friend_family_issue": "朋友家庭问题扰动（friend_family_issue）",
    "money_already_involved": "已投入资金扰动（money_already_involved）",
    "savings_low": "储蓄安全垫不足扰动（savings_low）",
    "market_signal_strong": "市场信号较强扰动（market_signal_strong）",
}

TASK_LABELS = {
    "life_travel_001": "假期旅行选择（life_travel_001）",
    "career_switch_001": "职业转型选择（career_switch_001）",
    "relationship_partner_001": "朋友合作边界（relationship_partner_001）",
    "resource_project_001": "个人项目投入（resource_project_001）",
}


def generate_assessment_markdown_report(summary: dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(redact_text(_render(summary)), encoding="utf-8")
    return output_path


def _render(summary: dict[str, Any]) -> str:
    tasks = summary["tasks"]
    results = sorted(_with_current_scoring(summary["results"], tasks), key=lambda item: item["total_score"], reverse=True)
    summary_text = _build_report_summary(results, summary.get("summary", "没有可用摘要。"))
    validity_notice = _validity_notice(results)
    lines: list[str] = [
        "# 模型能力评估报告",
        "",
        f"- 运行标识（ID）：`{summary['run_id']}`",
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
    lines.extend(["", "## 评分方法说明", "", _scoring_method_section()])
    lines.extend(
        [
            "",
            "## 总评分排名",
            "",
            "| 排名 | 模型 | 供应商类型（Provider） | 总评分 | 建议角色 | 失败项 |",
            "|---:|---|---|---:|---|---|",
        ]
    )
    for index, result in enumerate(results, start=1):
        roles = _role_names(result, 2)
        failures = _format_failure_list(result["failures"][:2] + result["errors"][:2])
        model_name = _display_model_name(result)
        lines.append(
            f"| {index} | {_cell(model_name)} | {_cell(_provider_label(result['provider']))} | {result['total_score']} | {_cell(roles)} | {_cell(failures)} |"
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
            f"- SQLite（轻量数据库）汇总：[{output_dir}/summary.sqlite3]({output_dir}/summary.sqlite3)",
        ]
    )

    return "\n".join(lines) + "\n"


def _with_current_scoring(results: list[dict[str, Any]], tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """用当前本地规则重算报告分数。

    summary.json 保存了每轮 parsed JSON，因此报告重建时可以复用这些本地证据重新评分。
    这不会访问模型 API，也不会增加调用成本；好处是评分规则修正后，旧运行报告也能反映当前规则。
    """
    task_objects = [_task_from_dict(task) for task in tasks]
    enriched: list[dict[str, Any]] = []
    for result in results:
        responses = result.get("responses", [])
        if not isinstance(responses, list):
            enriched.append(result)
            continue
        model_result = AssessmentModelResult(
            alias=str(result.get("alias", "")),
            model_name=str(result.get("model_name", "")),
            provider=str(result.get("provider", "")),
            role_hint=str(result.get("role_hint", "")),
            temperature=result.get("temperature"),
            errors=list(result.get("errors", [])),
        )
        model_result.responses = [
            AssessmentPhaseResponse(
                task_id=str(response.get("task_id", "")),
                phase_id=str(response.get("phase_id", "baseline")),
                prompt=str(response.get("prompt", "")),
                raw_text=str(response.get("raw_text", "")),
                parsed=response.get("parsed") if isinstance(response.get("parsed"), dict) else None,
                parse_error=str(response.get("parse_error", "")),
                usage=response.get("usage", {}) if isinstance(response.get("usage"), dict) else {},
            )
            for response in responses
            if isinstance(response, dict)
        ]
        score_assessment_result(model_result, task_objects)
        item = dict(result)
        item.update(model_result.to_dict())
        enriched.append(item)
    return enriched


def _task_from_dict(task: dict[str, Any]) -> AssessmentTask:
    mutations = [
        AssessmentMutation(
            id=str(mutation.get("id", "")),
            kind=str(mutation.get("kind", "")),
            prompt=str(mutation.get("prompt", "")),
            expected_top_keywords=list(mutation.get("expected_top_keywords", [])),
            expected_avoid_keywords=list(mutation.get("expected_avoid_keywords", [])),
        )
        for mutation in task.get("mutations", [])
        if isinstance(mutation, dict)
    ]
    return AssessmentTask(
        id=str(task.get("id", "")),
        domain=str(task.get("domain", "")),
        title=str(task.get("title", "")),
        prompt=str(task.get("prompt", "")),
        visible_constraints=list(task.get("visible_constraints", [])),
        hidden_values=dict(task.get("hidden_values", {})),
        acceptable_options=list(task.get("acceptable_options", [])),
        bad_options=list(task.get("bad_options", [])),
        scoring_points=list(task.get("scoring_points", [])),
        mutations=mutations,
        professional_boundary=str(task.get("professional_boundary", "")),
    )


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


def _scoring_method_section() -> str:
    return "\n".join(
        [
            "收到模型回答后，程序按以下顺序评估：",
            "",
            "1. 先解析 JSON（结构化数据格式）。只有顶层是合法 JSON 对象，才会进入字段、任务和拆解评分；解析失败的轮次在核心评分项上按 0 计入。",
            "2. 再做程序化规则评分，检查字段完整性、备选方案数量、坏方案规避、专业边界、行动计划、可接受方案匹配和扰动响应。",
            "3. 同时计算过程质量（Assessment Quality），参考 Decision Quality（决策质量）概念，判断问题框架、价值识别、备选方案、信息利用、推理和执行承诺。",
            "4. 然后做响应拆解评估，识别约束锚定、价值拆解、权衡推理、信息追问、风险与可逆性、行动可执行性、变化适配、校准边界和方法多样性。",
            "5. 最后先分别计算领域分、过程质量分、程序化规则分、响应拆解分和角色适配分的组内均分，再对这些组均分取平均，得到总评分；每个子项和每个分组满分都是 10；不调用模型裁判。",
            "",
            "完整公式见 [docs/quality/scoring.md](docs/quality/scoring.md)。",
            "",
            "| 评分项 | 主要计算方式 |",
            "|---|---|",
            "| JSON 完整性 | 13 个必填字段中非空字段占比；JSON 是本项目要求模型返回的结构化数据格式。 |",
            "| 备选方案数量 | `alternatives`（备选方案字段）至少 3 个得满分，不足按比例扣分。 |",
            "| 坏方案规避 | 回答中没有命中题目定义的明显坏方案关键词得满分。 |",
            "| 专业边界 | 高风险题必须给出边界；普通题需提示核实、咨询或个人判断边界。 |",
            "| 行动计划 | `next_actions_7_days`（7 天行动）、`next_actions_30_days`（30 天行动）、`revisit_conditions`（复盘条件）都存在才得满分。 |",
            "| 可接受方案匹配 | 推荐或排序命中题目允许的合理方案关键词得分。 |",
            "| 扰动响应 | 扰动后推荐发生变化、命中预期方向、避开应规避方向，三项取平均。 |",
            "| 过程质量 | 根据问题框架、价值、备选方案、信息、推理、执行六组结构化信号打分。 |",
            "| 响应拆解 | 根据具体约束、数字、利弊、风险、可逆性、行动细节、置信度和方法关键词打分。 |",
            "| 方法覆盖评分 | 先统计八类方法关键词命中次数，再按“命中次数 / 2”截断到 1，换算成 0-10 分；原始命中次数另表展示，不当作分数。 |",
        ]
    )


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
        return f"> 本次运行有 {failed}/{total} 条响应未能解析为 JSON。这些轮次已按 0 计入核心评分项；其余 {valid} 条成功解析响应继续参与细项评分，比较结论需要结合失败项谨慎解读。"
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
        f"- 别名（Alias）：`{result['alias']}`",
        f"- 供应商类型（Provider）：{_provider_label(result['provider'])}",
        f"- 温度（Temperature）：{_temperature_text(result)}",
        f"- 总评分：{result['total_score']}/10",
        f"- 推荐角色：{_role_scores(result, limit=3)}",
        "",
        "#### 过程质量（Assessment Quality）",
        "",
        _score_table(result.get("quality_scores", {}), QUALITY_SCORE_LABELS),
        "",
        "#### 响应拆解评估",
        "",
        _diagnostic_table(result.get("diagnostic_scores", {})),
        "",
        "#### 方法与分析角度指纹",
        "",
        _method_fingerprint_score_table(result.get("method_fingerprint", {})),
        "",
        "#### 方法关键词命中次数",
        "",
        _score_table(result.get("method_fingerprint", {}), METHOD_FINGERPRINT_LABELS),
        "",
        "#### 拆解证据",
        "",
        _diagnostic_notes(result),
        "",
        "#### 程序化规则评分",
        "",
        _score_table(result.get("rule_scores", {}), RULE_SCORE_LABELS),
        "",
        "#### 行为指纹计数",
        "",
        _score_table(result.get("behavior_fingerprint", {}), BEHAVIOR_LABELS),
        "",
        "#### 证据摘录",
        "",
    ]
    for item in result["evidence"][:6]:
        lines.append(f"- {_format_evidence_item(item)}")
    if result["failures"] or result["errors"]:
        lines.extend(["", "#### 失败项", ""])
        for item in result["failures"] + result["errors"]:
            lines.append(f"- {_format_failure(item)}")
    lines.append("")
    return lines


def _task_section(task: dict[str, Any]) -> list[str]:
    lines = [
        f"### {task['title']}",
        "",
        f"- 任务标识（ID）：`{task['id']}`",
        f"- 领域：{task['domain']}",
        f"- 题面：{task['prompt']}",
        f"- 显式约束：{', '.join(task['visible_constraints'])}",
        f"- 可接受方案：{', '.join(task['acceptable_options'])}",
        f"- 明显坏方案：{', '.join(task['bad_options'])}",
        "",
        "扰动：",
    ]
    for mutation in task["mutations"]:
        lines.append(f"- {_phase_label(mutation['id'])}，类型：{_mutation_kind_label(mutation['kind'])}：{mutation['prompt']}")
    lines.append("")
    return lines


def _score_table(scores: dict[str, Any], labels: dict[str, str] | None = None) -> str:
    if not scores:
        return "无"
    lines = ["| 项目 | 值 |", "|---|---:|"]
    for name, value in scores.items():
        display_name = labels.get(str(name), str(name)) if labels else str(name)
        lines.append(f"| {_cell(display_name)} | {_cell(str(value))} |")
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


def _method_fingerprint_score_table(counts: dict[str, Any]) -> str:
    if not counts:
        return "无"
    lines = ["| 分析角度 | 覆盖评分 | 计算说明 |", "|---|---:|---|"]
    for name, value in counts.items():
        count = _safe_float(value)
        score = _to_ten(min(1.0, count / 2))
        lines.append(f"| {_cell(METHOD_FINGERPRINT_LABELS.get(str(name), str(name)))} | {score} | 命中 {count:g} 次；按 min(命中次数 / 2, 1) × 10 计算。 |")
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


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _display_model_name(result: dict[str, Any]) -> str:
    return format_model_display_name(result["model_name"], result.get("temperature"), result.get("alias", ""))


def _temperature_text(result: dict[str, Any]) -> str:
    display_name = _display_model_name(result)
    if display_name == result["model_name"]:
        return "未设置"
    return display_name.removeprefix(result["model_name"]).strip("（）").replace("温度 ", "")


def _provider_label(provider: str) -> str:
    return PROVIDER_LABELS.get(provider, f"未翻译供应商（{provider}）")


def _mutation_kind_label(kind: str) -> str:
    return MUTATION_KIND_LABELS.get(kind, f"未翻译扰动类型（{kind}）")


def _phase_label(phase_id: str) -> str:
    return PHASE_LABELS.get(phase_id, f"扰动阶段（{phase_id}）")


def _format_failure_list(items: list[str]) -> str:
    if not items:
        return "无"
    return "；".join(_format_failure(item) for item in items)


def _format_failure(item: str) -> str:
    text = str(item)
    for task_id, label in TASK_LABELS.items():
        text = text.replace(f"{task_id}/", f"{label}/")
    for phase_id, label in PHASE_LABELS.items():
        text = text.replace(f"/{phase_id}:", f"/{label}:")
        text = text.replace(f"{phase_id}:", f"{label}:")
    if "JSON 解析失败:" in text:
        prefix, details = text.split("JSON 解析失败:", 1)
        text = prefix + "JSON 解析失败: " + details.split(";")[0].strip()
    return _translate_parse_error(text)


def _translate_parse_error(text: str) -> str:
    replacements = {
        "Expecting property name enclosed in double quotes": "JSON 格式错误：对象字段名必须使用双引号",
        "Expecting ',' delimiter": "JSON 格式错误：缺少逗号或括号结构不完整",
        "Expecting value": "JSON 格式错误：缺少可解析的值",
    }
    translated = text
    for english, chinese in replacements.items():
        translated = translated.replace(english, f"{chinese}（{english}）")
    translated = re.sub(r"line (\d+) column (\d+) \(char (\d+)\)", r"第 \1 行第 \2 列（字符 \3）", translated)
    return _dedupe_semicolon_parts(translated)


def _dedupe_semicolon_parts(text: str) -> str:
    parts = [part.strip() for part in text.split(";")]
    seen: set[str] = set()
    output: list[str] = []
    for part in parts:
        if not part or part in seen:
            continue
        seen.add(part)
        output.append(part)
    return "；".join(output)


def _format_evidence_item(item: str) -> str:
    text = str(item)
    for phase_id, label in PHASE_LABELS.items():
        if text.startswith(f"{phase_id}:"):
            return text.replace(f"{phase_id}:", f"{label}：", 1)
    return text


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
