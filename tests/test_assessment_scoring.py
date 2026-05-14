# 检查当前模型能力评分规则。
# 输入：结构化模型回答；输出：pytest 断言结果。
from arena.assessment.models import AssessmentModelResult, AssessmentPhaseResponse
from arena.assessment.scoring import score_assessment_result
from arena.assessment.semantic_scoring import apply_semantic_scoring
from arena.assessment.tasks import DEFAULT_ASSESSMENT_TASKS
from arena.models import EmbeddingConfig


def test_score_assessment_result_uses_programmatic_rules():
    task = DEFAULT_ASSESSMENT_TASKS[1]
    baseline = {
        "problem_frame": "收入稳定和职业成长之间的转型决策",
        "assumptions": ["短期不能明显降薪"],
        "clarifying_questions": ["收入底线是多少？"],
        "values_detected": ["收入稳定", "成长", "家庭时间"],
        "alternatives": [
            {"name": "渐进转型", "type": "low_regret_trial", "pros": ["稳"], "cons": ["慢"], "reversibility": "high"},
            {"name": "内部转岗", "type": "hybrid", "pros": ["稳"], "cons": ["机会不确定"], "reversibility": "medium"},
            {"name": "副项目验证", "type": "stage_gate", "pros": ["验证"], "cons": ["占时间"], "reversibility": "high"},
        ],
        "recommended_option": "渐进转型",
        "option_ranking": ["渐进转型", "内部转岗", "副项目验证"],
        "confidence": 0.7,
        "risks": ["收入波动风险", "时间不足风险"],
        "next_actions_7_days": ["确认收入底线"],
        "next_actions_30_days": ["做副项目"],
        "revisit_conditions": ["收入下降"],
        "professional_boundary": "此为职业建议，不替代专业咨询。",
    }
    mutated = {**baseline, "recommended_option": "内部转岗", "option_ranking": ["内部转岗", "渐进转型", "副项目验证"]}
    result = AssessmentModelResult(alias="m", model_name="model", provider="fake", role_hint="")
    result.responses = [
        AssessmentPhaseResponse(task.id, "baseline", "", "", baseline),
        AssessmentPhaseResponse(task.id, "mortgage_pressure_high", "", "", mutated),
    ]

    score_assessment_result(result, [task])

    assert result.domain_scores["事业与成长"] > 7
    assert result.quality_scores["Creative Alternatives"] > 5
    assert result.rule_scores["mutation_response"] > 6
    assert result.diagnostic_scores["tradeoff_reasoning"] > 6
    assert result.diagnostic_scores["risk_reversibility"] > 6
    assert result.method_fingerprint["风险复盘"] > 0
    assert result.diagnostic_notes
    assert result.role_fit


def test_semantic_scoring_uses_reference_answers_and_updates_role_fit():
    task = DEFAULT_ASSESSMENT_TASKS[1]
    parsed = {
        "problem_frame": "后端开发转 AI 产品经理，需要平衡收入稳定和成长。",
        "assumptions": ["不能明显降薪"],
        "clarifying_questions": ["收入底线是多少？"],
        "values_detected": ["收入稳定", "职业成长", "家庭时间"],
        "alternatives": [
            {"name": "渐进转型", "type": "low_regret_trial", "pros": ["稳"], "cons": ["慢"], "reversibility": "high"},
            {"name": "内部转岗", "type": "hybrid", "pros": ["收入稳"], "cons": ["机会不确定"], "reversibility": "medium"},
            {"name": "副项目验证", "type": "stage_gate", "pros": ["验证"], "cons": ["占时间"], "reversibility": "high"},
        ],
        "recommended_option": "渐进转型",
        "option_ranking": ["渐进转型", "内部转岗", "副项目验证"],
        "confidence": 0.7,
        "risks": ["收入波动", "产品经验不足"],
        "next_actions_7_days": ["查看 AI 产品经理 JD"],
        "next_actions_30_days": ["完成一个 AI 产品案例"],
        "revisit_conditions": ["收入下降或机会明确变化"],
        "professional_boundary": "职业建议不替代合同、薪酬和家庭财务判断。",
    }
    result = AssessmentModelResult(alias="m", model_name="model", provider="fake", role_hint="")
    result.responses = [AssessmentPhaseResponse(task.id, "baseline", "", "", parsed)]
    score_assessment_result(result, [task])

    apply_semantic_scoring(
        result,
        embedding_config=EmbeddingConfig(api_key="sk-test"),
        embedding_cache=_AlwaysSimilarEmbeddingCache(),
    )

    assert result.semantic_scores["问题框架"] == 10
    assert result.semantic_role_fit["用户价值专家"] == 10
    assert result.role_fit["用户价值专家"] >= result.semantic_role_fit["用户价值专家"] * 0.35
    assert result.semantic_notes


class _AlwaysSimilarEmbeddingCache:
    def get_vectors(self, texts):  # noqa: ANN001
        return [[1.0, 0.0] for _text in texts]
