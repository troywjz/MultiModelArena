from __future__ import annotations

"""模型响应拆解诊断。

这里评估的是“模型已经返回的结构化 JSON 里体现出的分析行为”，不会再次调用模型。
设计目标是用低成本方式回答：模型为什么得分高或低、它用了哪些分析角度、哪些能力只是表面完整。
"""

import re
from dataclasses import dataclass, field
from typing import Any

from .models import AssessmentTask


# 来源说明：
# 1. 本模块没有复制 HELM、lm-evaluation-harness、BIG-bench 或 Decision Quality 的源码、题库、权重。
# 2. 这里只借鉴它们的公开评估思想：多维指标、证据透明、任务-指标-聚合分离。
# 3. 具体字段、关键词和分数阈值是为本项目“个人行动领域”评测重新设计的本地规则。
# 4. 对应项目链接、许可证和 Decision Quality 概念来源写在 README 的“评测体系参考”中。
DIAGNOSTIC_DIMENSIONS = {
    "constraint_grounding": "约束锚定",
    "value_decomposition": "价值拆解",
    "tradeoff_reasoning": "权衡推理",
    "information_seeking": "信息追问",
    "risk_reversibility": "风险与可逆性",
    "execution_specificity": "行动可执行性",
    "adaptation_to_change": "变化适配",
    "calibration_boundary": "校准与边界",
    "method_diversity": "方法多样性",
}

# 方法指纹不是直接评分答案“对不对”，而是识别模型是否使用了可复核的分析角度。
# 例如出现“试点、阶段、复盘”通常说明模型在做小步验证；出现“权衡、取舍、排序”
# 说明模型不只是给单一建议，而是在比较备选方案。关键词命中只作为弱信号，
# 最终仍要结合 JSON 完整性、扰动响应和人工查看原始记录。
METHOD_KEYWORDS = {
    "阶段门/试点验证": ["阶段", "试点", "原型", "MVP", "验证", "小规模", "复盘", "扩大"],
    "权衡矩阵/优先级": ["权衡", "取舍", "优先级", "排序", "性价比", "成本", "收益", "机会成本"],
    "约束检查": ["预算", "收入", "时间", "交通", "签证", "房贷", "安全垫", "储蓄"],
    "风险复盘": ["风险", "不确定", "预案", "应急", "边界", "触发", "退路", "止损"],
    "相关方对齐": ["同行", "朋友", "家人", "相关人", "沟通", "关系", "同伴", "双方"],
    "信息缺口管理": ["假设", "确认", "澄清", "信息", "访谈", "数据", "证据"],
    "用户价值识别": ["价值", "偏好", "目标", "放松", "成长", "公平", "下行保护"],
    "执行计划": ["7天", "30天", "行动", "清单", "指标", "截止", "安排", "预订"],
}


@dataclass(frozen=True)
class ResponseDiagnostics:
    scores: dict[str, float]
    method_counts: dict[str, int]
    notes: list[str] = field(default_factory=list)


def analyze_response(
    parsed: dict[str, Any],
    task: AssessmentTask,
    *,
    phase_id: str,
    baseline: dict[str, Any] | None = None,
) -> ResponseDiagnostics:
    # 将整个 JSON 展平为文本后做关键词和结构检测。
    # 这样可以兼容不同模型在字段内使用略有差异的中文表述，不要求它们逐字命中模板。
    blob = _text_blob(parsed)
    visible_hits = _count_keyword_hits(blob, task.visible_constraints)
    alternatives = _alternatives(parsed)
    actions = _as_list(parsed.get("next_actions_7_days")) + _as_list(parsed.get("next_actions_30_days"))
    revisit_conditions = _as_list(parsed.get("revisit_conditions"))
    method_counts = _method_counts(blob)
    method_hit_count = sum(1 for value in method_counts.values() if value > 0)
    pros_cons_count = sum(len(_as_list(item.get("pros"))) + len(_as_list(item.get("cons"))) for item in alternatives)
    confidence = _numeric_confidence(parsed.get("confidence"))
    changed = _changed_from_baseline(parsed, baseline) if phase_id != "baseline" else True

    scores = {
        # 约束锚定：题面约束、具体数字、约束类方法同时出现时更可信。
        # 只说“要综合考虑”但不提预算/时间/房贷等约束，会在这里失分。
        "constraint_grounding": _average(
            [
                _ratio(visible_hits, len(task.visible_constraints)),
                _ratio(_specific_number_count(blob), 2),
                1.0 if method_counts["约束检查"] else 0.0,
            ]
        ),
        # 价值拆解：检查模型是否识别用户偏好和目标张力，而不只是直接给结论。
        "value_decomposition": _average(
            [
                _ratio(len(_as_list(parsed.get("values_detected"))), max(2, len(task.hidden_values))),
                1.0 if method_counts["用户价值识别"] else 0.0,
                1.0 if parsed.get("problem_frame") else 0.0,
            ]
        ),
        # 权衡推理：看 alternatives 的 pros/cons、排序和权衡类词汇。
        # 这能区分“列清单”与“真的比较过方案”。
        "tradeoff_reasoning": _average(
            [
                _ratio(pros_cons_count, 6),
                _ratio(len(_as_list(parsed.get("option_ranking"))), 3),
                1.0 if method_counts["权衡矩阵/优先级"] else 0.0,
            ]
        ),
        # 信息追问：看模型是否明确假设和需要澄清的问题。
        # 个人行动类任务信息常常不完整，能否暴露信息缺口是重要能力。
        "information_seeking": _average(
            [
                _ratio(len(_as_list(parsed.get("assumptions"))), 2),
                _ratio(len(_as_list(parsed.get("clarifying_questions"))), 2),
                1.0 if method_counts["信息缺口管理"] else 0.0,
            ]
        ),
        # 风险与可逆性：看风险、可逆性、复盘条件是否同时出现。
        # 这是红队/风险类角色画像的重要来源之一。
        "risk_reversibility": _average(
            [
                _ratio(len(_as_list(parsed.get("risks"))), 2),
                _ratio(_reversibility_count(alternatives), 3),
                _ratio(len(revisit_conditions), 2),
                1.0 if method_counts["风险复盘"] else 0.0,
            ]
        ),
        # 行动可执行性：看 7 天/30 天行动是否具体，并尽量包含时间、数量或阈值。
        # 只给抽象建议会得分较低。
        "execution_specificity": _average(
            [
                _ratio(len(actions), 4),
                _ratio(_specific_number_count(" ".join(str(item) for item in actions)), 1),
                1.0 if method_counts["执行计划"] else 0.0,
            ]
        ),
        # 变化适配：只在扰动轮次中评分。扰动后仍沿用旧推荐，说明更新能力不足。
        "adaptation_to_change": _average(
            [
                1.0 if changed else 0.0,
                1.0 if _ranking_matches_expected(parsed, task) else 0.0,
            ]
        )
        if phase_id != "baseline"
        else 1.0,
        # 校准与边界：看置信度是否落在合理范围，以及是否说明专业边界。
        # 过度自信或完全不提边界，都不利于高风险场景使用。
        "calibration_boundary": _average(
            [
                1.0 if confidence is not None else 0.0,
                1.0 if confidence is not None and 0.35 <= confidence <= 0.9 else 0.0,
                1.0 if parsed.get("professional_boundary") else 0.0,
            ]
        ),
        # 方法多样性：统计不同方法指纹的覆盖数，避免模型只靠单一套路回答。
        "method_diversity": _ratio(method_hit_count, 4),
    }
    return ResponseDiagnostics(scores=scores, method_counts=method_counts, notes=_notes(scores, method_counts, visible_hits, task))


def _notes(
    scores: dict[str, float],
    method_counts: dict[str, int],
    visible_hits: int,
    task: AssessmentTask,
) -> list[str]:
    notes: list[str] = []
    if visible_hits:
        notes.append(f"提到 {visible_hits}/{len(task.visible_constraints)} 个显式约束，说明回答会锚定题面限制。")
    strong_methods = [name for name, count in method_counts.items() if count > 0][:4]
    if strong_methods:
        notes.append(f"使用{'、'.join(strong_methods)}等分析角度，说明回答不只停留在结论。")
    weak_dimensions = [DIAGNOSTIC_DIMENSIONS[key] for key, value in scores.items() if value < 0.45][:3]
    if weak_dimensions:
        notes.append(f"{'、'.join(weak_dimensions)}偏弱，报告结论需结合原始记录复核。")
    return notes


def _changed_from_baseline(parsed: dict[str, Any], baseline: dict[str, Any] | None) -> bool:
    if baseline is None:
        return True
    return parsed.get("recommended_option") != baseline.get("recommended_option") or _ranking_text(parsed) != _ranking_text(baseline)


def _ranking_matches_expected(parsed: dict[str, Any], task: AssessmentTask) -> bool:
    ranking = _ranking_text(parsed)
    return any(keyword in ranking for keyword in task.acceptable_options)


def _method_counts(text: str) -> dict[str, int]:
    return {name: _count_keyword_hits(text, keywords) for name, keywords in METHOD_KEYWORDS.items()}


def _specific_number_count(text: str) -> int:
    return len(re.findall(r"\d+(?:\.\d+)?\s*(?:天|元|万|小时|个月|人|个|次|%|％)?", text))


def _reversibility_count(alternatives: list[dict[str, Any]]) -> int:
    return sum(1 for item in alternatives if item.get("reversibility") not in (None, "", []))


def _numeric_confidence(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if 0 <= number <= 1:
        return number
    return None


def _alternatives(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    alternatives = parsed.get("alternatives")
    if not isinstance(alternatives, list):
        return []
    return [item for item in alternatives if isinstance(item, dict)]


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


def _count_keyword_hits(text: str, keywords: list[str]) -> int:
    normalized_text = _normalize_text(text)
    return sum(1 for keyword in keywords if keyword and _normalize_text(keyword) in normalized_text)


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", str(text)).lower()


def _ratio(value: int | float, target: int | float) -> float:
    if target <= 0:
        return 1.0
    return max(0.0, min(1.0, float(value) / float(target)))


def _average(values: list[float]) -> float:
    clean = [value for value in values if value is not None]
    if not clean:
        return 0.0
    return sum(clean) / len(clean)
