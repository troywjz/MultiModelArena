from __future__ import annotations

from .models import AssessmentMutation, AssessmentTask


DEFAULT_ASSESSMENT_TASKS = [
    AssessmentTask(
        id="life_travel_001",
        domain="个人生活",
        title="假期旅行选择",
        prompt=(
            "用户有 7 天假期，预算 8000 元，想放松但又怕无聊。候选方向包括日本、云南、"
            "在家休息、海边城市。请给出结构化建议。"
        ),
        visible_constraints=["7 天假期", "预算 8000 元", "想放松", "怕无聊"],
        hidden_values={"rest": 0.35, "novelty": 0.25, "budget": 0.25, "logistics": 0.15},
        acceptable_options=["低强度海边城市", "云南慢旅行", "在家深度休息", "日本城市轻旅行"],
        bad_options=["高强度打卡游", "超预算远途旅行"],
        scoring_points=["mentions_budget", "offers_low_intensity_option", "defines_revisit_condition"],
        mutations=[
            AssessmentMutation(
                id="prefer_quiet",
                kind="value_shift",
                prompt="新增信息：用户最重视安静和低疲惫，讨厌排队打卡。",
                expected_top_keywords=["低强度海边", "在家深度休息", "安静"],
                expected_avoid_keywords=["高强度", "打卡"],
            ),
            AssessmentMutation(
                id="companion_budget_4000",
                kind="new_evidence",
                prompt="新增信息：同行朋友预算只有 4000 元，且不想承担太多交通成本。",
                expected_top_keywords=["云南慢旅行", "在家深度休息", "近程", "低强度海边"],
                expected_avoid_keywords=["日本", "超预算"],
            ),
        ],
    ),
    AssessmentTask(
        id="career_switch_001",
        domain="事业与成长",
        title="职业转型选择",
        prompt=(
            "用户 32 岁，做后端开发 8 年，想转 AI 产品经理，但收入不能下降太多。"
            "请给出结构化建议。"
        ),
        visible_constraints=["32 岁", "后端开发 8 年", "转 AI 产品经理", "收入不能下降太多"],
        hidden_values={"income_stability": 0.35, "growth": 0.25, "family_time": 0.25, "prestige": 0.15},
        acceptable_options=["渐进转型", "内部转岗", "副项目验证", "直接跳槽"],
        bad_options=["无准备裸辞", "忽略收入约束直接转行"],
        scoring_points=["mentions_income_constraint", "offers_gradual_path", "defines_revisit_condition"],
        mutations=[
            AssessmentMutation(
                id="mortgage_pressure_high",
                kind="new_evidence",
                prompt="新增信息：用户家庭房贷压力较大，短期现金流不能明显波动。",
                expected_top_keywords=["渐进转型", "内部转岗", "副项目验证"],
                expected_avoid_keywords=["裸辞", "收入下降"],
            ),
            AssessmentMutation(
                id="learning_time_limited",
                kind="new_evidence",
                prompt="新增信息：用户每周最多只有 8 小时学习和做项目。",
                expected_top_keywords=["副项目验证", "内部转岗", "渐进转型"],
                expected_avoid_keywords=["全职备考", "裸辞"],
            ),
        ],
    ),
    AssessmentTask(
        id="relationship_partner_001",
        domain="人际与关系",
        title="朋友合作边界",
        prompt=(
            "用户和多年朋友合伙做个人项目，朋友经常拖延但关系很好。用户纠结是否继续合作。"
            "请给出结构化建议。"
        ),
        visible_constraints=["多年朋友", "合伙做个人项目", "朋友经常拖延", "关系很好"],
        hidden_values={"relationship": 0.35, "project_progress": 0.3, "fairness": 0.2, "emotional_cost": 0.15},
        acceptable_options=["重新约定边界", "降低合作承诺", "暂停合作", "拆分职责试运行"],
        bad_options=["无条件继续合作", "情绪化断交"],
        scoring_points=["mentions_boundary", "protects_relationship", "defines_trial_period"],
        mutations=[
            AssessmentMutation(
                id="friend_family_issue",
                kind="new_evidence",
                prompt="新增信息：朋友最近家庭出现问题，短期内精力确实不足。",
                expected_top_keywords=["降低合作承诺", "短期支持", "重新约定边界"],
                expected_avoid_keywords=["断交", "指责"],
            ),
            AssessmentMutation(
                id="money_already_involved",
                kind="new_evidence",
                prompt="新增信息：双方已经各自投入了一笔钱，继续拖延会造成实际损失。",
                expected_top_keywords=["重新约定边界", "拆分职责", "暂停合作"],
                expected_avoid_keywords=["无条件继续", "口头约定"],
            ),
        ],
    ),
    AssessmentTask(
        id="resource_project_001",
        domain="资源与风险",
        title="个人项目投入",
        prompt=(
            "用户想投入 5 万元和半年业余时间做一个个人 AI 产品，但还没有验证真实需求。"
            "请给出结构化建议。"
        ),
        visible_constraints=["投入 5 万元", "半年业余时间", "个人 AI 产品", "没有验证真实需求"],
        hidden_values={"downside_protection": 0.35, "learning": 0.25, "upside": 0.25, "speed": 0.15},
        acceptable_options=["小规模试点", "阶段性投入", "先做需求验证", "暂缓大额投入"],
        bad_options=["一次性投入全部预算", "不验证需求直接开发"],
        scoring_points=["mentions_validation", "offers_stage_gate", "defines_stop_loss"],
        mutations=[
            AssessmentMutation(
                id="savings_low",
                kind="new_evidence",
                prompt="新增信息：用户可支配储蓄并不多，5 万元会明显影响安全垫。",
                expected_top_keywords=["暂缓大额投入", "小规模试点", "先做需求验证"],
                expected_avoid_keywords=["一次性投入", "全部预算"],
            ),
            AssessmentMutation(
                id="market_signal_strong",
                kind="new_evidence",
                prompt="新增信息：用户已经访谈 20 个目标用户，其中 8 个愿意为原型付费试用。",
                expected_top_keywords=["阶段性投入", "小规模试点", "需求验证"],
                expected_avoid_keywords=["一次性投入全部预算"],
            ),
        ],
    ),
]
