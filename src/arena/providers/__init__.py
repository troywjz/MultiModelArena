# 构建模型供应商适配器。
# 输入：模型配置；输出：具体 Provider 实例。
from __future__ import annotations

from arena.models import ModelConfig

from .base import Provider
from .anthropic_compatible import AnthropicCompatibleProvider
from .fake import FakeProvider
from .openai_compatible import OpenAICompatibleProvider


def build_provider(config: ModelConfig) -> Provider:
    if config.provider == "fake":
        return FakeProvider(config)
    if config.provider == "anthropic_compatible":
        return AnthropicCompatibleProvider(config)
    if config.provider == "openai_compatible":
        return OpenAICompatibleProvider(config)
    raise ValueError(f"不支持的 provider: {config.provider}")


__all__ = ["Provider", "build_provider"]
