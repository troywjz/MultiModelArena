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
        previous_text = json.dumps(previous_response, ensure_ascii=False)
    system = (
        "你正在参与个人行动领域的模型能力评估。请严格输出一个 JSON 对象，不要输出 Markdown、代码块或额外解释。"
        "你可以说明不确定性和边界，但必须给出可程序评分的结构化回答。"
    )
    user = f"""
MODEL_ASSESSMENT_JSON_TASK
TASK_ID: {task.id}
PHASE_ID: {phase_label}
DOMAIN: {task.domain}
TITLE: {task.title}

用户问题：
{task.prompt}

本轮新增信息：
{mutation_text}

上一轮答案摘要：
{previous_text}

请输出 JSON，字段必须包含：
{", ".join(REQUIRED_OUTPUT_FIELDS)}

字段要求：
- alternatives 至少 3 个，每个包含 name、type、pros、cons、reversibility。
- option_ranking 从最推荐到最不推荐排序。
- confidence 为 0 到 1 的数字。
- next_actions_7_days、next_actions_30_days、revisit_conditions 都必须是列表。
- 如果涉及健康、法律、投资或高风险现实行动，professional_boundary 必须说明需要人类或专业人士确认。
""".strip()
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


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
