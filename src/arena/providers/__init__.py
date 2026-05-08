from __future__ import annotations

from arena.models import ModelConfig

from .base import Provider
from .fake import FakeProvider
from .openai_compatible import OpenAICompatibleProvider


def build_provider(config: ModelConfig) -> Provider:
    if config.provider == "fake":
        return FakeProvider(config)
    if config.provider == "openai_compatible":
        return OpenAICompatibleProvider(config)
    raise ValueError(f"不支持的 provider: {config.provider}")


__all__ = ["Provider", "build_provider"]
