from __future__ import annotations

import json
import re
from typing import Any

from .models import AssessmentMutation, AssessmentTask


REQUIRED_OUTPUT_FIELDS = [
    "problem_frame",
    "assumptions",
    "clarifying_questions",
    "values_detected",
    "alternatives",
    "recommended_option",
    "option_ranking",
    "confidence",
    "risks",
    "next_actions_7_days",
    "next_actions_30_days",
    "revisit_conditions",
    "professional_boundary",
]


def build_assessment_messages(
    task: AssessmentTask,
    *,
    mutation: AssessmentMutation | None = None,
    previous_response: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    phase_label = "baseline" if mutation is None else mutation.id
    mutation_text = "无"
    if mutation is not None:
        mutation_text = f"{mutation.kind}: {mutation.prompt}"
    previous_text = "无"
    if previous_response is not None:
        previous_text = _previous_response_summary(previous_response)
    system = (
        "只输出紧凑JSON对象，必须以{开头以}结尾。禁止Markdown、解释、分析过程、<think>。"
        "必须是严格JSON：所有字段名和字符串都用英文双引号，禁止{problem_frame:...}这类JS对象写法，"
        "禁止尾逗号，数组用[]且对象用{}正确闭合。"
        "总字数尽量700字以内，短语尽量16字内；在字段内容里体现依据、权衡、风险和下一步。"
    )
    user = (
        f"题:{task.title};域:{task.domain};问题:{task.prompt};新增:{mutation_text};上轮:{previous_text}。"
        f"输出JSON字段:{','.join(REQUIRED_OUTPUT_FIELDS)}。"
        "约束:alternatives恰好3项,每项含name,type,pros,cons,reversibility,pros/cons各1短句;"
        "assumptions,clarifying_questions,values_detected,risks,next_actions_7_days,next_actions_30_days,"
        "revisit_conditions各最多2项;option_ranking恰好3个名称;confidence为0到1;"
        "行动和复盘条件尽量带时间、阈值或可验证信号;professional_boundary一句,无专业风险写个人判断即可。"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _previous_response_summary(previous_response: dict[str, Any]) -> str:
    summary = {
        "recommended_option": previous_response.get("recommended_option", ""),
        "option_ranking": previous_response.get("option_ranking", [])[:3]
        if isinstance(previous_response.get("option_ranking"), list)
        else previous_response.get("option_ranking", ""),
        "risks": previous_response.get("risks", [])[:2]
        if isinstance(previous_response.get("risks"), list)
        else previous_response.get("risks", ""),
    }
    return json.dumps(summary, ensure_ascii=False, separators=(",", ":"))


def parse_json_response(text: str) -> tuple[dict[str, Any] | None, str]:
    stripped = text.strip()
    if not stripped:
        return None, "空响应"
    candidates = [stripped]
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.DOTALL)
    if fence_match:
        candidates.insert(0, fence_match.group(1))
    object_match = re.search(r"\{.*\}", stripped, re.DOTALL)
    if object_match:
        candidates.append(object_match.group(0))
    errors: list[str] = []
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as exc:
            errors.append(str(exc))
            continue
        if isinstance(parsed, dict):
            return parsed, ""
        errors.append("JSON 顶层不是对象")
    return None, "; ".join(errors[:2]) or "无法解析 JSON"
