from __future__ import annotations

from arena.models import DIMENSIONS, TEAM_ROLES, ModelRunResult


KEYWORDS = {
    "准确性": ["事实", "推理", "约束", "证据", "校准"],
    "完整性": ["目标", "非目标", "边界", "验收", "风险"],
    "协作性": ["反馈", "共识", "修订", "协作", "吸收"],
    "稳定性": ["格式", "失败", "降级", "一致", "重试"],
    "工程可用性": ["模块", "测试", "实现", "数据", "运行"],
    "表达质量": ["结构", "清晰", "简洁", "报告", "说明"],
}


def score_result(result: ModelRunResult) -> None:
    joined = "\n".join(
        list(result.answers.values())
        + list(result.peer_reviews.values())
        + list(result.revisions.values())
    )
    for dimension in DIMENSIONS:
        base = 6
        hits = sum(1 for keyword in KEYWORDS[dimension] if keyword in joined)
        length_bonus = 1 if len(joined) > 240 else 0
        error_penalty = min(3, len(result.errors))
        result.scores[dimension] = max(1, min(10, base + hits + length_bonus - error_penalty))

    result.strengths = infer_strengths(result)
    result.weaknesses = infer_weaknesses(result)
    result.recommended_roles = infer_roles(result)
    result.evidence = infer_evidence(result)


def infer_strengths(result: ModelRunResult) -> list[str]:
    top_dimensions = sorted(result.scores.items(), key=lambda item: item[1], reverse=True)[:2]
    strengths = [f"{name}表现较好，评分 {score}/10" for name, score in top_dimensions]
    if result.role_hint:
        strengths.append(f"输出风格贴近预期角色：{result.role_hint}")
    return strengths


def infer_weaknesses(result: ModelRunResult) -> list[str]:
    bottom_dimensions = sorted(result.scores.items(), key=lambda item: item[1])[:2]
    weaknesses = [f"{name}仍需用更多任务校准，当前评分 {score}/10" for name, score in bottom_dimensions]
    if result.errors:
        weaknesses.append("运行过程中出现调用错误，需要先解决稳定性问题")
    return weaknesses


def infer_roles(result: ModelRunResult) -> list[str]:
    if result.role_hint and result.role_hint in TEAM_ROLES:
        return [result.role_hint]
    ordered = sorted(result.scores.items(), key=lambda item: item[1], reverse=True)
    mapping = {
        "准确性": "风险与安全审查者",
        "完整性": "需求澄清者",
        "协作性": "文档与总结者",
        "稳定性": "测试与质量审查者",
        "工程可用性": "代码实现者",
        "表达质量": "文档与总结者",
    }
    roles: list[str] = []
    for dimension, _score in ordered:
        role = mapping[dimension]
        if role not in roles:
            roles.append(role)
        if len(roles) == 2:
            break
    return roles


def infer_evidence(result: ModelRunResult) -> list[str]:
    snippets: list[str] = []
    for collection in (result.revisions, result.answers, result.peer_reviews):
        for text in collection.values():
            cleaned = " ".join(text.split())
            if cleaned and cleaned not in snippets:
                snippets.append(cleaned[:220])
            if len(snippets) == 3:
                return snippets
    return snippets
