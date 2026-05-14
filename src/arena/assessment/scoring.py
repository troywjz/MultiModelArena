# 计算本地程序化评分。
# 输入：结构化模型回答和任务定义；输出：领域分、规则分和角色分。
from __future__ import annotations

from collections import defaultdict
from typing import Any

from .diagnostics import DIAGNOSTIC_DIMENSIONS, analyze_response
from .models import QUALITY_DIMENSIONS, ROLE_FIT_RULES, AssessmentModelResult, AssessmentTask
from .protocol import REQUIRED_OUTPUT_FIELDS


def score_assessment_result(result: AssessmentModelResult, tasks: list[AssessmentTask]) -> None:
    task_map = {task.id: task for task in tasks}
    domain_hits: dict[str, list[float]] = defaultdict(list)
    dq_hits: dict[str, list[float]] = {name: [] for name in QUALITY_DIMENSIONS}
    rule_hits: dict[str, list[float]] = defaultdict(list)
    diagnostic_hits: dict[str, list[float]] = defaultdict(list)
    method_fingerprint: dict[str, float] = defaultdict(float)
    diagnostic_notes: list[str] = []
    behavior = {
        "clarifying_questions": 0.0,
        "alternative_count": 0.0,
        "creative_option_count": 0.0,
        "constraint_mentions": 0.0,
        "risk_count": 0.0,
        "action_count": 0.0,
        "boundary_present_count": 0.0,
        "mutation_response_count": 0.0,
        "bad_option_hit_count": 0.0,
        "json_valid_count": 0.0,
    }

    baselines: dict[str, dict[str, Any]] = {}
    for response in result.responses:
        task = task_map.get(response.task_id)
        if task is None:
            continue
        parsed = response.parsed
        if parsed is None:
            result.failures.append(f"{response.task_id}/{response.phase_id}: JSON 解析失败: {response.parse_error}")
            for rule_name in [
                "json_complete",
                "alternative_count",
                "bad_option_avoidance",
                "professional_boundary",
                "action_plan",
                "acceptable_option_match",
            ]:
                rule_hits[rule_name].append(0)
            if response.phase_id != "baseline":
                rule_hits["mutation_response"].append(0)
            domain_hits[task.domain].append(0)
            for name in QUALITY_DIMENSIONS:
                dq_hits[name].append(0)
            for name in DIAGNOSTIC_DIMENSIONS:
                diagnostic_hits[name].append(0)
            continue
        behavior["json_valid_count"] += 1
        if response.phase_id == "baseline":
            baselines[response.task_id] = parsed

        completeness = _score_completeness(parsed)
        alternatives = _alternatives(parsed)
        alternative_count = min(1.0, len(alternatives) / 3)
        bad_hits = _count_keyword_hits(_text_blob(parsed), task.bad_options)
        boundary = _has_boundary(parsed, task)
        action_plan = _has_action_plan(parsed)
        acceptable_match = _matches_any(_ranking_text(parsed), task.acceptable_options)
        bad_avoidance = 0.0 if bad_hits else 1.0

        rule_hits["json_complete"].append(completeness)
        rule_hits["alternative_count"].append(alternative_count)
        rule_hits["bad_option_avoidance"].append(bad_avoidance)
        rule_hits["professional_boundary"].append(1.0 if boundary else 0.0)
        rule_hits["action_plan"].append(1.0 if action_plan else 0.0)
        rule_hits["acceptable_option_match"].append(1.0 if acceptable_match else 0.0)

        behavior["alternative_count"] += len(alternatives)
        behavior["creative_option_count"] += _creative_option_count(alternatives)
        behavior["clarifying_questions"] += len(_as_list(parsed.get("clarifying_questions")))
        behavior["constraint_mentions"] += _count_keyword_hits(_text_blob(parsed), task.visible_constraints)
        behavior["risk_count"] += len(_as_list(parsed.get("risks")))
        behavior["action_count"] += len(_as_list(parsed.get("next_actions_7_days"))) + len(_as_list(parsed.get("next_actions_30_days")))
        behavior["boundary_present_count"] += 1 if boundary else 0
        behavior["bad_option_hit_count"] += bad_hits

        mutation_score = _score_mutation_response(response.phase_id, parsed, task, baselines.get(task.id))
        if response.phase_id != "baseline":
            rule_hits["mutation_response"].append(mutation_score)
            behavior["mutation_response_count"] += 1 if mutation_score >= 0.75 else 0

        dq = _quality_scores(parsed, task)
        for name, score in dq.items():
            dq_hits[name].append(score)

        diagnostics = analyze_response(parsed, task, phase_id=response.phase_id, baseline=baselines.get(task.id))
        for name, score in diagnostics.scores.items():
            diagnostic_hits[name].append(score)
        for name, count in diagnostics.method_counts.items():
            method_fingerprint[name] += count
        for note in diagnostics.notes:
            if note not in diagnostic_notes and len(diagnostic_notes) < 8:
                diagnostic_notes.append(note)

        domain_hits[task.domain].append(
            _average(
                [
                    completeness,
                    alternative_count,
                    bad_avoidance,
                    1.0 if boundary else 0.0,
                    1.0 if action_plan else 0.0,
                    1.0 if acceptable_match else 0.0,
                    mutation_score if response.phase_id != "baseline" else 1.0,
                ]
            )
        )
        if len(result.evidence) < 6:
            result.evidence.append(_evidence_line(response.phase_id, parsed))

    result.rule_scores = {name: _to_ten(_average(values)) for name, values in rule_hits.items()}
    result.domain_scores = {name: _to_ten(_average(values)) for name, values in domain_hits.items()}
    result.quality_scores = {name: _to_ten(_average(values)) for name, values in dq_hits.items() if values}
    result.diagnostic_scores = {name: _to_ten(_average(values)) for name, values in diagnostic_hits.items()}
    result.method_fingerprint = dict(method_fingerprint)
    result.diagnostic_notes = diagnostic_notes
    result.behavior_fingerprint = behavior
    result.role_fit = _role_fit(result.quality_scores, result.behavior_fingerprint, result.diagnostic_scores)


def _score_completeness(parsed: dict[str, Any]) -> float:
    present = 0
    for field in REQUIRED_OUTPUT_FIELDS:
        value = parsed.get(field)
        if value not in (None, "", []):
            present += 1
    return present / len(REQUIRED_OUTPUT_FIELDS)


def _quality_scores(parsed: dict[str, Any], task: AssessmentTask) -> dict[str, float]:
    alternatives = _alternatives(parsed)
    info_items = len(_as_list(parsed.get("assumptions"))) + len(_as_list(parsed.get("clarifying_questions")))
    pros_cons_count = sum(len(_as_list(item.get("pros"))) + len(_as_list(item.get("cons"))) for item in alternatives)
    return {
        "Helpful Frame": _bool_score(bool(parsed.get("problem_frame"))) * 0.6
        + min(1.0, len(_as_list(parsed.get("assumptions"))) / 2) * 0.4,
        "Clear Values": min(1.0, len(_as_list(parsed.get("values_detected"))) / max(2, min(4, len(task.hidden_values)))),
        "Creative Alternatives": min(1.0, (len(alternatives) + _creative_option_count(alternatives)) / 5),
        "Useful Information": min(1.0, (info_items + len(_as_list(parsed.get("risks")))) / 6),
        "Sound Reasoning": min(1.0, (pros_cons_count + len(_as_list(parsed.get("option_ranking")))) / 10),
        "Commitment to Follow Through": min(
            1.0,
            (
                len(_as_list(parsed.get("next_actions_7_days")))
                + len(_as_list(parsed.get("next_actions_30_days")))
                + len(_as_list(parsed.get("revisit_conditions")))
            )
            / 7,
        ),
    }


def _score_mutation_response(
    phase_id: str,
    parsed: dict[str, Any],
    task: AssessmentTask,
    baseline: dict[str, Any] | None,
) -> float:
    mutation = next((item for item in task.mutations if item.id == phase_id), None)
    if mutation is None:
        return 1.0
    ranking = _ranking_text(parsed)
    expected = _matches_any(ranking, mutation.expected_top_keywords)
    avoided = not _matches_any(ranking, mutation.expected_avoid_keywords)
    changed = True
    if baseline is not None:
        changed = parsed.get("recommended_option") != baseline.get("recommended_option") or ranking != _ranking_text(baseline)
    return _average([1.0 if expected else 0.0, 1.0 if avoided else 0.0, 1.0 if changed else 0.0])


def _role_fit(dq_scores: dict[str, float], behavior: dict[str, float], diagnostic_scores: dict[str, float]) -> dict[str, float]:
    role_scores: dict[str, float] = {}
    for role, dimensions in ROLE_FIT_RULES.items():
        base = _average([dq_scores.get(dimension, 0.0) / 10 for dimension in dimensions])
        if role == "通用主持专家":
            base = _average([base, diagnostic_scores.get("constraint_grounding", 0.0) / 10])
        if role == "用户价值专家":
            base = _average([base, diagnostic_scores.get("value_decomposition", 0.0) / 10])
        if role == "信息审查专家":
            base = _average([base, diagnostic_scores.get("information_seeking", 0.0) / 10])
        if role == "风险专家":
            base = _average(
                [
                    base,
                    min(1.0, behavior.get("risk_count", 0) / 12),
                    min(1.0, behavior.get("boundary_present_count", 0) / 4),
                    diagnostic_scores.get("risk_reversibility", 0.0) / 10,
                ]
            )
        if role == "方案生成专家":
            base = _average([base, min(1.0, behavior.get("creative_option_count", 0) / 8), diagnostic_scores.get("method_diversity", 0.0) / 10])
        if role == "执行规划专家":
            base = _average([base, min(1.0, behavior.get("action_count", 0) / 16), diagnostic_scores.get("execution_specificity", 0.0) / 10])
        if role == "权衡仲裁专家":
            base = _average([base, diagnostic_scores.get("tradeoff_reasoning", 0.0) / 10])
        if role == "红队专家":
            base = _average(
                [
                    base,
                    min(1.0, behavior.get("risk_count", 0) / 12),
                    diagnostic_scores.get("risk_reversibility", 0.0) / 10,
                    diagnostic_scores.get("calibration_boundary", 0.0) / 10,
                ]
            )
        if role == "结论整合专家":
            base = _average(
                [
                    base,
                    diagnostic_scores.get("tradeoff_reasoning", 0.0) / 10,
                    diagnostic_scores.get("execution_specificity", 0.0) / 10,
                    min(1.0, behavior.get("mutation_response_count", 0) / 4),
                ]
            )
        role_scores[role] = _to_ten(base)
    return role_scores


def _has_boundary(parsed: dict[str, Any], task: AssessmentTask) -> bool:
    boundary = str(parsed.get("professional_boundary", ""))
    blob = _text_blob(parsed)
    if task.professional_boundary:
        return bool(boundary)
    return any(keyword in blob for keyword in ["专业", "确认", "咨询", "不替代", "自行核实", "人类"])


def _has_action_plan(parsed: dict[str, Any]) -> bool:
    return bool(_as_list(parsed.get("next_actions_7_days"))) and bool(_as_list(parsed.get("next_actions_30_days"))) and bool(_as_list(parsed.get("revisit_conditions")))


def _alternatives(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    alternatives = parsed.get("alternatives")
    if not isinstance(alternatives, list):
        return []
    return [item for item in alternatives if isinstance(item, dict)]


def _creative_option_count(alternatives: list[dict[str, Any]]) -> int:
    creative_types = {"low_regret_trial", "hybrid", "stage_gate", "hold"}
    return sum(1 for item in alternatives if str(item.get("type", "")) in creative_types)


def _ranking_text(parsed: dict[str, Any]) -> str:
    ranking = parsed.get("option_ranking")
    if isinstance(ranking, list):
        return " ".join(str(item) for item in ranking[:3])
    return str(parsed.get("recommended_option", ""))


def _text_blob(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_text_blob(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_text_blob(item) for item in value)
    return str(value)


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _matches_any(text: str, keywords: list[str]) -> bool:
    if not keywords:
        return True
    return any(keyword and keyword in text for keyword in keywords)


def _count_keyword_hits(text: str, keywords: list[str]) -> int:
    return sum(1 for keyword in keywords if keyword and keyword in text)


def _bool_score(value: bool) -> float:
    return 1.0 if value else 0.0


def _average(values: list[float]) -> float:
    clean = [value for value in values if value is not None]
    if not clean:
        return 0.0
    return sum(clean) / len(clean)


def _to_ten(value: float) -> float:
    return round(max(0.0, min(1.0, value)) * 10, 2)


def _evidence_line(phase_id: str, parsed: dict[str, Any]) -> str:
    option = parsed.get("recommended_option", "未给出推荐")
    risks = _as_list(parsed.get("risks"))
    risk_text = "；".join(str(item) for item in risks[:2])
    return f"{phase_id}: 推荐 {option}；主要风险：{risk_text}"
