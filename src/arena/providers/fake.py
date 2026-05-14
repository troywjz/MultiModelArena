# 提供离线 fake 模型适配器。
# 输入：消息列表；输出：模拟模型响应。
from __future__ import annotations

import hashlib

from arena.assessment.fake_outputs import build_fake_assessment_response, is_assessment_prompt
from arena.models import DIMENSIONS, TEAM_ROLES, ProviderResponse

from .base import Provider


class FakeProvider(Provider):
    def complete(self, messages: list[dict[str, str]]) -> ProviderResponse:
        prompt = "\n".join(message["content"] for message in messages)
        if is_assessment_prompt(prompt):
            return ProviderResponse(
                text=build_fake_assessment_response(self.config.model_name, prompt),
                usage={"fake_tokens": len(prompt)},
            )
        digest = hashlib.sha256(f"{self.config.alias}:{prompt}".encode("utf-8")).hexdigest()
        style = int(digest[:2], 16) % 3
        role = self.config.role_hint or TEAM_ROLES[int(digest[2:4], 16) % len(TEAM_ROLES)]
        dimension = DIMENSIONS[int(digest[4:6], 16) % len(DIMENSIONS)]
        if style == 0:
            text = (
                f"{self.config.model_name} 给出偏工程化的回答。重点关注{dimension}，"
                f"建议担任{role}。优点是结构清晰、能拆解风险；不足是可能保守，"
                "需要更多真实数据校准。"
            )
        elif style == 1:
            text = (
                f"{self.config.model_name} 给出偏产品化的回答。重点关注用户目标、"
                f"验收标准和共识形成，适合担任{role}。不足是实现细节需要工程审查。"
            )
        else:
            text = (
                f"{self.config.model_name} 给出偏审查型的回答。强调失败降级、测试和密钥脱敏，"
                f"适合担任{role}。不足是表达较谨慎，可能降低推进速度。"
            )
        return ProviderResponse(text=text, usage={"fake_tokens": len(prompt)})
