# 定义当前评测数据结构。
# 输入：评测过程数据；输出：可序列化的结果对象。
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any


QUALITY_DIMENSIONS = [
    "Helpful Frame",
    "Clear Values",
    "Creative Alternatives",
    "Useful Information",
    "Sound Reasoning",
    "Commitment to Follow Through",
]

BEHAVIOR_FINGERPRINT_KEYS = [
    "clarifying_questions",
    "alternative_count",
    "creative_option_count",
    "constraint_mentions",
    "risk_count",
    "action_count",
    "boundary_present_count",
    "mutation_response_count",
    "bad_option_hit_count",
    "json_valid_count",
]

ROLE_FIT_RULES = {
    "通用主持专家": ["Helpful Frame", "Sound Reasoning"],
    "用户价值专家": ["Clear Values"],
    "信息审查专家": ["Useful Information"],
    "风险专家": ["Useful Information", "Commitment to Follow Through"],
    "方案生成专家": ["Creative Alternatives"],
    "权衡仲裁专家": ["Sound Reasoning", "Clear Values"],
    "执行规划专家": ["Commitment to Follow Through"],
    "红队专家": ["Useful Information"],
    "结论整合专家": ["Helpful Frame", "Sound Reasoning", "Commitment to Follow Through"],
}


ROLE_DEFINITIONS = {
    "通用主持专家": "负责框定议题、维持讨论顺序、让不同角色围绕同一问题充分表达，并在必要时把讨论拉回目标。",
    "用户价值专家": "负责识别用户真实目标、偏好、价值冲突和隐含优先级，避免会议只优化表面指标。",
    "信息审查专家": "负责区分事实、假设和未知信息，提出需要补充验证的问题，防止用不充分信息直接定案。",
    "方案生成专家": "负责提出多样化备选方案，包括低后悔、小步试点、折中和暂缓方案，避免只给单一路径。",
    "权衡仲裁专家": "负责比较备选方案的收益、成本、机会成本和约束匹配度，帮助会议形成可辩护排序。",
    "风险专家": "负责识别不确定性、下行风险、止损条件、可逆性和预案，保护决策不被乐观叙事带偏。",
    "执行规划专家": "负责把结论转成 7 天、30 天和复盘节点的行动计划，检查下一步是否具体可执行。",
    "红队专家": "负责主动挑战推荐方案，寻找反例、失败模式、过度自信和专业边界问题。",
    "结论整合专家": "负责把多角色意见压缩成最终建议、分歧点、触发条件和待复核事项，服务后续民主集中制会议形成决议。",
}


@dataclass(frozen=True)
class AssessmentMutation:
    id: str
    kind: str
    prompt: str
    expected_top_keywords: list[str]
    expected_avoid_keywords: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AssessmentTask:
    id: str
    domain: str
    title: str
    prompt: str
    visible_constraints: list[str]
    hidden_values: dict[str, float]
    acceptable_options: list[str]
    bad_options: list[str]
    scoring_points: list[str]
    mutations: list[AssessmentMutation]
    professional_boundary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "domain": self.domain,
            "title": self.title,
            "prompt": self.prompt,
            "visible_constraints": self.visible_constraints,
            "hidden_values": self.hidden_values,
            "acceptable_options": self.acceptable_options,
            "bad_options": self.bad_options,
            "scoring_points": self.scoring_points,
            "mutations": [mutation.__dict__ for mutation in self.mutations],
            "professional_boundary": self.professional_boundary,
        }


@dataclass
class AssessmentPhaseResponse:
    task_id: str
    phase_id: str
    prompt: str
    raw_text: str
    parsed: dict[str, Any] | None
    parse_error: str = ""
    usage: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "phase_id": self.phase_id,
            "prompt": self.prompt,
            "raw_text": self.raw_text,
            "parsed": self.parsed,
            "parse_error": self.parse_error,
            "usage": self.usage,
        }


@dataclass
class AssessmentModelResult:
    alias: str
    model_name: str
    provider: str
    role_hint: str
    temperature: float | None = None
    responses: list[AssessmentPhaseResponse] = field(default_factory=list)
    domain_scores: dict[str, float] = field(default_factory=dict)
    quality_scores: dict[str, float] = field(default_factory=dict)
    behavior_fingerprint: dict[str, float] = field(default_factory=dict)
    role_fit: dict[str, float] = field(default_factory=dict)
    rule_scores: dict[str, float] = field(default_factory=dict)
    diagnostic_scores: dict[str, float] = field(default_factory=dict)
    method_fingerprint: dict[str, float] = field(default_factory=dict)
    semantic_scores: dict[str, float] = field(default_factory=dict)
    semantic_role_fit: dict[str, float] = field(default_factory=dict)
    semantic_notes: list[str] = field(default_factory=list)
    diagnostic_notes: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def total_score(self) -> float:
        score_groups = [
            self.domain_scores,
            self.quality_scores,
            self.rule_scores,
            self.diagnostic_scores,
            self.semantic_scores,
            self.role_fit,
        ]
        group_scores = [_average(list(group.values())) for group in score_groups if group]
        if not group_scores:
            return 0.0
        return round(sum(group_scores) / len(group_scores), 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "alias": self.alias,
            "model_name": self.model_name,
            "provider": self.provider,
            "role_hint": self.role_hint,
            "temperature": self.temperature,
            "responses": [response.to_dict() for response in self.responses],
            "domain_scores": self.domain_scores,
            "quality_scores": self.quality_scores,
            "behavior_fingerprint": self.behavior_fingerprint,
            "role_fit": self.role_fit,
            "rule_scores": self.rule_scores,
            "diagnostic_scores": self.diagnostic_scores,
            "method_fingerprint": self.method_fingerprint,
            "semantic_scores": self.semantic_scores,
            "semantic_role_fit": self.semantic_role_fit,
            "semantic_notes": self.semantic_notes,
            "diagnostic_notes": self.diagnostic_notes,
            "total_score": self.total_score,
            "evidence": self.evidence,
            "failures": self.failures,
            "errors": self.errors,
        }


@dataclass
class AssessmentRunSummary:
    run_id: str
    created_at: str
    output_dir: Path
    tasks: list[AssessmentTask]
    results: list[AssessmentModelResult]
    mode: str = "assessment"

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "run_id": self.run_id,
            "created_at": self.created_at,
            "output_dir": str(self.output_dir),
            "tasks": [task.to_dict() for task in self.tasks],
            "results": [result.to_dict() for result in self.results],
            "summary": build_summary(self.results),
        }


def build_summary(results: list[AssessmentModelResult]) -> str:
    if not results:
        return "没有可用评估结果。"
    ranked = sorted(results, key=lambda result: result.total_score, reverse=True)
    has_semantic = any(result.semantic_scores for result in ranked)
    lines = [
        "本次总评分来自本地规则和参考答案语义相似度，不包含模型裁判。"
        if has_semantic
        else "本次总评分仅来自本地程序化规则，不包含模型裁判。"
    ]
    for result in ranked:
        best_roles = sorted(result.role_fit.items(), key=lambda item: item[1], reverse=True)[:2]
        role_text = "、".join(name for name, _score in best_roles) or "待定"
        display_name = format_model_display_name(result.model_name, result.temperature, result.alias)
        lines.append(f"{display_name}: 总分 {result.total_score}/10，建议角色 {role_text}")
    return "\n".join(lines)


def format_model_display_name(model_name: str, temperature: Any = None, alias: str = "") -> str:
    inferred_temperature = _normalize_temperature(temperature)
    if inferred_temperature is None:
        inferred_temperature = infer_temperature_from_alias(alias)
    if inferred_temperature is None:
        return model_name
    return f"{model_name}（温度 {inferred_temperature:g}）"


def infer_temperature_from_alias(alias: str) -> float | None:
    match = re.search(r"(?:^|_)t(\d{2})$", alias)
    if not match:
        return None
    return int(match.group(1)) / 10


def _normalize_temperature(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _average(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)
