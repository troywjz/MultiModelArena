# 存放语义评分参考答案。
# 输入：任务和阶段标识；输出：字段级参考答案片段。
from __future__ import annotations

from dataclasses import dataclass


SEMANTIC_SEGMENT_LABELS = {
    "problem_frame": "问题框架",
    "values_detected": "价值识别",
    "alternatives": "备选方案",
    "recommendation": "推荐与排序",
    "risks_revisit": "风险与复盘",
    "actions": "行动计划",
    "professional_boundary": "专业边界",
}


SEGMENT_ROLES = {
    "problem_frame": ("通用主持专家", "结论整合专家"),
    "values_detected": ("用户价值专家",),
    "alternatives": ("方案生成专家",),
    "recommendation": ("权衡仲裁专家", "结论整合专家"),
    "risks_revisit": ("风险专家", "红队专家"),
    "actions": ("执行规划专家",),
    "professional_boundary": ("信息审查专家", "风险专家", "红队专家"),
}


@dataclass(frozen=True)
class ReferenceAnswerSegment:
    task_id: str
    phase_id: str
    segment: str
    texts: tuple[str, ...]
    roles: tuple[str, ...]


def reference_segments_for(task_id: str, phase_id: str) -> list[ReferenceAnswerSegment]:
    phase_data = REFERENCE_ANSWERS.get((task_id, phase_id), {})
    return [
        ReferenceAnswerSegment(
            task_id=task_id,
            phase_id=phase_id,
            segment=segment,
            texts=tuple(texts),
            roles=SEGMENT_ROLES[segment],
        )
        for segment, texts in phase_data.items()
    ]


def all_reference_segments() -> list[ReferenceAnswerSegment]:
    output: list[ReferenceAnswerSegment] = []
    for task_id, phase_id in sorted(REFERENCE_ANSWERS):
        output.extend(reference_segments_for(task_id, phase_id))
    return output


def _phase(
    *,
    frame: str,
    values: str,
    alternatives: str,
    recommendation: str,
    risks: str,
    actions: str,
    boundary: str,
) -> dict[str, tuple[str, ...]]:
    return {
        "problem_frame": (frame,),
        "values_detected": (values,),
        "alternatives": (alternatives,),
        "recommendation": (recommendation,),
        "risks_revisit": (risks,),
        "actions": (actions,),
        "professional_boundary": (boundary,),
    }


# 参考答案是语义评分的本地基准，不是唯一标准答案。
# 每个任务阶段按“子项”拆解，方便分别评估问题框架、价值识别、方案、推荐、风险、行动和边界。
REFERENCE_ANSWERS: dict[tuple[str, str], dict[str, tuple[str, ...]]] = {
    ("life_travel_001", "baseline"): _phase(
        frame="在 7 天和 8000 元预算内平衡放松、趣味、新鲜感和交通成本，避免把假期变成高强度打卡。",
        values="用户重视休息恢复，也担心无聊；同时需要控制预算、交通疲劳和目的地不确定性。",
        alternatives="可比较低强度海边城市、云南慢旅行、在家深度休息加本地活动、日本城市轻旅行等方案，并说明成本、疲劳和可逆性。",
        recommendation="优先推荐低强度海边城市或云南慢旅行；日本因预算和签证交通不确定性靠后，在家休息可作为低成本备选。",
        risks="主要风险是超预算、旅途疲劳、旺季排队、天气和同行偏好变化；需要设置可取消住宿、预算上限和改期条件。",
        actions="7 天内确定同行、预算和城市候选，查交通住宿并保留可退选项；30 天内完成预订、制定轻量行程和备用方案。",
        boundary="这是个人旅行决策建议，不替代签证、保险、健康和目的地政策核实；出行前应确认实时价格和退改规则。",
    ),
    ("life_travel_001", "prefer_quiet"): _phase(
        frame="新增安静和低疲惫偏好后，核心从新鲜感最大化转为低强度恢复和避免排队打卡。",
        values="安静、低疲惫、可控节奏优先于景点数量；预算和交通便利仍然重要。",
        alternatives="低强度海边城市、安静民宿度假、在家深度休息加少量本地活动更匹配；高强度打卡和热门排队线路应降级。",
        recommendation="优先推荐安静海边城市或在家深度休息；选择可步行、可临时调整、景点密度低的方案。",
        risks="热门海滨和假期人流可能破坏安静目标；需要避开热门商圈、选择可取消住宿和非高峰交通。",
        actions="先筛掉高强度和排队景点，确认安静住宿、交通时长和每天不超过一到两个活动；保留一天完全放空。",
        boundary="安静程度和疲惫感主观差异大，最终需按用户身体状态、同行偏好和实时客流信息确认。",
    ),
    ("life_travel_001", "companion_budget_4000"): _phase(
        frame="同行预算降到 4000 元后，问题变成双方预算公平、交通成本和体验质量的重新平衡。",
        values="用户仍想放松和避免无聊，但需要尊重同行支付能力，降低费用压力和关系摩擦。",
        alternatives="近程低强度海边、云南精简慢旅行、在家深度休息加本地活动更合理；日本和远途高成本方案应靠后。",
        recommendation="优先推荐近程海边或在家加本地活动；如选云南，应压缩城市数量、控制住宿和交通成本。",
        risks="预算差异可能导致消费压力和体验不一致；若坚持日本或远途，容易超预算并影响同行关系。",
        actions="先共同确认每人预算上限和费用分摊，再筛选交通住宿总价，设置每日餐饮娱乐上限和可取消预订。",
        boundary="费用分摊属于同行协商问题，建议提前书面确认预算边界和可接受消费档位。",
    ),
    ("career_switch_001", "baseline"): _phase(
        frame="用户想从 8 年后端开发转 AI 产品经理，但收入不能明显下降，核心是成长机会和现金流稳定之间的权衡。",
        values="收入稳定、长期成长、家庭时间和职业身份变化都重要，不能只追求转型速度。",
        alternatives="渐进转型、内部转岗、副项目验证、直接跳槽都可比较；无准备裸辞应排除。",
        recommendation="优先推荐渐进转型：保留后端收入，叠加 AI 产品项目、内部机会和作品集，再择机转岗或跳槽。",
        risks="风险包括收入下降、产品经验不足、学习时间被高估、市场岗位要求不清；需要设置现金流和阶段验收。",
        actions="7 天内梳理收入底线和目标岗位 JD；30 天内完成一个 AI 产品分析或原型作品，并访谈产品经理校准路径。",
        boundary="职业建议不能替代个人财务、劳动合同和家庭决策；跳槽前应核实薪酬、岗位职责和试用期风险。",
    ),
    ("career_switch_001", "mortgage_pressure_high"): _phase(
        frame="房贷压力较大时，转型策略必须优先保护现金流，不能用高风险裸辞换取不确定成长。",
        values="收入稳定和家庭安全垫优先，成长目标需要通过低风险路径推进。",
        alternatives="内部转岗、渐进转型、副项目验证更合适；无准备裸辞和大幅降薪转行应排除。",
        recommendation="优先内部转岗或现职叠加 AI 产品职责，等作品集和机会成熟后再跳槽。",
        risks="房贷压力会放大试用期失败、降薪和学习投入不足的风险；需要设置收入底线和储蓄安全垫。",
        actions="先计算 6 到 12 个月现金流安全线，向公司争取 AI 相关项目，低成本做作品集和行业访谈。",
        boundary="涉及房贷和家庭财务时，应结合家庭预算、合同条款和专业财务意见，不建议凭模型建议直接辞职。",
    ),
    ("career_switch_001", "learning_time_limited"): _phase(
        frame="每周只有 8 小时时，转型重点从高强度学习变成最小可验证路径和时间利用效率。",
        values="用户需要兼顾工作、家庭和成长，不能制定依赖大量空闲时间的计划。",
        alternatives="副项目验证、内部转岗、渐进转型适合；全职备考和重度课程计划不匹配。",
        recommendation="优先用 8 小时做一个可展示的 AI 产品案例，每周固定访谈、竞品分析和原型输出。",
        risks="学习计划过大容易中断；作品集质量不足、岗位要求误判和长期疲劳都是主要风险。",
        actions="把 8 小时拆成调研、产品文档、原型和复盘四块；30 天内产出一个完整案例并找 2 位业内人士反馈。",
        boundary="时间安排需要结合工作强度和家庭责任，若长期疲劳应降低目标密度或延长转型周期。",
    ),
    ("relationship_partner_001", "baseline"): _phase(
        frame="多年朋友合作拖延问题同时涉及项目进展和关系维护，关键是把友情和合作责任拆开处理。",
        values="用户重视关系、项目推进、公平感和情绪成本，不能只用继续或断交二选一。",
        alternatives="重新约定边界、拆分职责试运行、降低合作承诺、暂停合作都可比较；无条件继续和情绪化断交应避免。",
        recommendation="优先重新约定边界并设置试运行周期，明确交付、截止时间、决策权和退出条件。",
        risks="风险包括关系受损、继续拖延、责任不清和投入浪费；需要把口头承诺变成可复盘约定。",
        actions="7 天内约一次非指责沟通，列出任务和截止时间；30 天内跑一个试运行周期，按交付结果决定继续或调整。",
        boundary="人际合作建议不能替代法律合同或财务协议；若涉及资金和权益，应保留书面记录并必要时咨询专业人士。",
    ),
    ("relationship_partner_001", "friend_family_issue"): _phase(
        frame="朋友短期家庭问题使拖延原因更复杂，决策应兼顾支持关系和保护项目进度。",
        values="用户需要表达理解，同时维护公平和项目边界，避免把短期困难无限期延长。",
        alternatives="降低合作承诺、短期支持、重新约定边界或临时拆分职责较合适；指责和断交不应优先。",
        recommendation="优先短期降低朋友责任，设定支持期和复盘点，同时把关键任务转给用户或第三方。",
        risks="同情可能导致边界继续模糊；若没有时间点，项目会继续停滞并积累怨气。",
        actions="沟通中先确认朋友可投入时间，再设两到四周临时安排、关键任务负责人和复盘日期。",
        boundary="家庭问题涉及隐私和情绪压力，应尊重对方边界；若资金权益已复杂化，应补充书面约定。",
    ),
    ("relationship_partner_001", "money_already_involved"): _phase(
        frame="双方已经投入资金后，合作问题从情绪纠结升级为损失控制和责任边界问题。",
        values="关系仍重要，但公平、止损和资金安全权重上升，不能继续只靠口头信任。",
        alternatives="重新约定边界、拆分职责、暂停合作和清算投入都应进入比较；无条件继续和口头约定应避免。",
        recommendation="优先书面化职责、预算、交付和退出机制；若短期无法达成，暂停新增投入并做清算方案。",
        risks="继续拖延会扩大实际损失；口头约定不足以处理分歧，可能伤害关系和财务。",
        actions="7 天内整理已投入金额、资产和责任清单；30 天内签署简短合作备忘或暂停协议并设止损点。",
        boundary="涉及资金、权益和合同风险时，模型建议不能替代法律意见；关键约定应书面化。",
    ),
    ("resource_project_001", "baseline"): _phase(
        frame="用户想投入 5 万元和半年业余时间做 AI 产品，但尚未验证需求，核心是上行机会和下行保护的阶段性决策。",
        values="用户重视学习、潜在收益和速度，但下行保护、真实需求和机会成本更需要被显性化。",
        alternatives="小规模试点、先做需求验证、阶段性投入、暂缓大额投入都可比较；一次性投入全部预算应排除。",
        recommendation="优先先做需求验证和小规模试点，只有达到明确指标后再阶段性增加投入。",
        risks="风险包括伪需求、预算消耗、时间机会成本、技术过度开发和获客困难；需要设置止损条件。",
        actions="7 天内定义目标用户和访谈提纲；30 天内完成访谈、落地页或原型测试，并用付费意愿决定是否投入。",
        boundary="这是创业和资源配置建议，不替代投资、法律、税务或商业咨询；投入前应核实现金流承受能力。",
    ),
    ("resource_project_001", "savings_low"): _phase(
        frame="可支配储蓄不足时，5 万元投入会影响安全垫，决策重点应转向暂缓大额投入和低成本验证。",
        values="下行保护优先于速度和规模，学习收益也应通过低成本方式获得。",
        alternatives="暂缓大额投入、小规模试点、先做需求验证更合适；一次性投入全部预算应避免。",
        recommendation="优先暂缓 5 万元投入，只用小预算做访谈、原型和获客验证，达到阈值后再追加。",
        risks="安全垫下降会放大生活压力；需求未验证时投入越大，沉没成本和决策偏差越强。",
        actions="先设个人安全垫底线和单阶段预算上限，30 天内完成低成本需求验证而不进入重开发。",
        boundary="涉及个人储蓄和风险承受能力，需结合真实现金流和家庭责任，不应仅凭模型建议投入资金。",
    ),
    ("resource_project_001", "market_signal_strong"): _phase(
        frame="已有 20 个访谈和 8 个付费意愿后，项目从纯假设进入有初步信号的阶段，但仍需阶段性验证。",
        values="上行机会和速度权重提高，但下行保护、付费真实性和交付能力仍需控制。",
        alternatives="阶段性投入、小规模试点、付费原型验证较合理；仍不应一次性投入全部预算。",
        recommendation="优先阶段性投入，围绕 8 个愿付费用户做最小付费试点，再按留存和转化指标决定扩大。",
        risks="付费意愿不等于真实付款；样本偏差、交付难度和获客成本可能导致信号失真。",
        actions="7 天内确认愿付费用户的具体价格和场景；30 天内完成可收费原型、收款验证和阶段复盘。",
        boundary="市场信号需要真实交易验证；涉及公司注册、合同、税务和投资时应咨询专业人士。",
    ),
}
