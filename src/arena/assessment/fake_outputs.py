from __future__ import annotations

import json
import re


def is_assessment_prompt(prompt: str) -> bool:
    return ("请输出 JSON，字段必须包含：" in prompt or "输出JSON字段:" in prompt) and "recommended_option" in prompt


def build_fake_assessment_response(model_name: str, prompt: str) -> str:
    task_id = _infer_task_id(prompt)
    phase_id = _infer_phase_id(prompt)
    option = _recommended_option(task_id, phase_id)
    alternatives = _alternatives(task_id, phase_id)
    if option not in [item["name"] for item in alternatives]:
        alternatives.insert(0, _alternative(option, "low_regret_trial"))
    ranking = [item["name"] for item in alternatives]
    if option in ranking:
        ranking.remove(option)
    ranking.insert(0, option)
    response = {
        "problem_frame": _problem_frame(task_id),
        "assumptions": ["当前信息仍不完整，建议先按低后悔路径验证。", f"本回答由 {model_name} 的 fake provider 生成。"],
        "clarifying_questions": _questions(task_id),
        "values_detected": _values(task_id),
        "alternatives": alternatives[:4],
        "recommended_option": option,
        "option_ranking": ranking[:4],
        "confidence": 0.74,
        "risks": _risks(task_id),
        "next_actions_7_days": ["补齐关键约束", "和相关人确认真实偏好", "做一个低成本试验"],
        "next_actions_30_days": ["根据试验结果复盘", "更新预算和时间安排", "决定是否扩大投入"],
        "revisit_conditions": ["预算或健康条件变化", "关键关系人反馈明显不同", "试验结果低于预期"],
        "professional_boundary": _boundary(task_id),
    }
    return json.dumps(response, ensure_ascii=False)


def _extract(prompt: str, key: str) -> str:
    match = re.search(rf"^{key}:\s*(.+)$", prompt, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _infer_task_id(prompt: str) -> str:
    if "7 天假期" in prompt and "预算 8000" in prompt:
        return "life_travel_001"
    if "后端开发 8 年" in prompt and "AI 产品经理" in prompt:
        return "career_switch_001"
    if "多年朋友合伙" in prompt or "朋友经常拖延" in prompt:
        return "relationship_partner_001"
    if "投入 5 万元" in prompt and "个人 AI 产品" in prompt:
        return "resource_project_001"
    return "unknown"


def _infer_phase_id(prompt: str) -> str:
    phase_markers = {
        "最重视安静": "prefer_quiet",
        "同行朋友预算只有 4000": "companion_budget_4000",
        "房贷压力较大": "mortgage_pressure_high",
        "每周最多只有 8 小时": "learning_time_limited",
        "家庭出现问题": "friend_family_issue",
        "各自投入了一笔钱": "money_already_involved",
        "安全垫": "savings_low",
        "20 个目标用户": "market_signal_strong",
    }
    for marker, phase_id in phase_markers.items():
        if marker in prompt:
            return phase_id
    return "baseline"


def _recommended_option(task_id: str, phase_id: str) -> str:
    mapping = {
        "life_travel_001": {
            "baseline": "低强度海边城市",
            "prefer_quiet": "低强度海边城市",
            "companion_budget_4000": "云南慢旅行",
        },
        "career_switch_001": {
            "baseline": "渐进转型",
            "mortgage_pressure_high": "内部转岗",
            "learning_time_limited": "副项目验证",
        },
        "relationship_partner_001": {
            "baseline": "重新约定边界",
            "friend_family_issue": "降低合作承诺",
            "money_already_involved": "拆分职责试运行",
        },
        "resource_project_001": {
            "baseline": "小规模试点",
            "savings_low": "暂缓大额投入",
            "market_signal_strong": "阶段性投入",
        },
    }
    options = mapping.get(task_id, {"baseline": "低后悔试点"})
    return options.get(phase_id, options.get("baseline", "低后悔试点"))


def _alternatives(task_id: str, phase_id: str) -> list[dict[str, object]]:
    options = {
        "life_travel_001": ["低强度海边城市", "云南慢旅行", "在家深度休息", "日本城市轻旅行"],
        "career_switch_001": ["渐进转型", "内部转岗", "副项目验证", "直接跳槽"],
        "relationship_partner_001": ["重新约定边界", "降低合作承诺", "暂停合作", "拆分职责试运行"],
        "resource_project_001": ["小规模试点", "阶段性投入", "先做需求验证", "暂缓大额投入"],
    }.get(task_id, ["低后悔试点", "维持现状", "阶段性投入"])
    return [_alternative(name, _option_type(index, phase_id)) for index, name in enumerate(options)]


def _alternative(name: str, option_type: str) -> dict[str, object]:
    return {
        "name": name,
        "type": option_type,
        "pros": ["成本可控", "便于复盘"],
        "cons": ["需要持续跟踪", "短期结果可能不明显"],
        "reversibility": "high" if option_type in {"low_regret_trial", "hold"} else "medium",
    }


def _option_type(index: int, phase_id: str) -> str:
    if index == 0:
        return "low_regret_trial"
    if index == 1:
        return "hybrid"
    if "pressure" in phase_id or "budget" in phase_id or "savings" in phase_id:
        return "hold"
    return "direct_path"


def _problem_frame(task_id: str) -> str:
    frames = {
        "life_travel_001": "在预算、疲惫度和新鲜感之间选择低后悔假期方案。",
        "career_switch_001": "在收入稳定和职业成长之间选择可验证的转型路径。",
        "relationship_partner_001": "在维护关系和保护项目进度之间重新设定合作边界。",
        "resource_project_001": "在上行机会和下行风险之间决定个人项目投入节奏。",
    }
    return frames.get(task_id, "在多个约束下选择低后悔行动方案。")


def _questions(task_id: str) -> list[str]:
    questions = {
        "life_travel_001": ["同行人数和体力限制是什么？", "预算是否包含购物和应急费用？"],
        "career_switch_001": ["当前收入底线是多少？", "是否有内部转岗机会？"],
        "relationship_partner_001": ["双方投入和收益如何约定？", "项目是否有硬截止时间？"],
        "resource_project_001": ["安全垫还剩几个月？", "愿意付费的用户是否代表目标市场？"],
    }
    return questions.get(task_id, ["最重要的价值排序是什么？"])


def _values(task_id: str) -> list[str]:
    values = {
        "life_travel_001": ["休息", "新鲜感", "预算", "低疲惫"],
        "career_switch_001": ["收入稳定", "成长", "家庭时间", "职业机会"],
        "relationship_partner_001": ["关系", "项目进度", "公平", "情绪成本"],
        "resource_project_001": ["下行保护", "学习", "上行空间", "速度"],
    }
    return values.get(task_id, ["低后悔", "可执行"])


def _risks(task_id: str) -> list[str]:
    risks = {
        "life_travel_001": ["行程过密导致更疲惫", "同行预算不一致引发冲突"],
        "career_switch_001": ["收入波动", "转型投入不足导致半途而废"],
        "relationship_partner_001": ["边界不清继续拖延", "沟通方式伤害关系"],
        "resource_project_001": ["未验证需求直接开发", "投入超过安全垫"],
    }
    return risks.get(task_id, ["信息不足导致误判"])


def _boundary(task_id: str) -> str:
    if task_id == "resource_project_001":
        return "涉及个人资金投入，不能替代财务建议；大额投入前需要人类确认。"
    if task_id == "life_travel_001":
        return "如涉及健康限制或签证政策，需要自行核实最新信息。"
    if task_id == "relationship_partner_001":
        return "涉及人际关系，建议由用户结合真实沟通反馈决定。"
    return "此为个人行动领域评估回答，不替代职业咨询或法律、财务等专业意见。"
