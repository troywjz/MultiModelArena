from arena.assessment.models import AssessmentModelResult, AssessmentPhaseResponse
from arena.assessment.scoring import score_assessment_result
from arena.assessment.tasks import DEFAULT_ASSESSMENT_TASKS


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
