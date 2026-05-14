# 定义模型供应商适配器基类。
# 输入：模型配置；输出：统一 complete 接口。
from __future__ import annotations

from abc import ABC, abstractmethod

from arena.models import ModelConfig, ProviderResponse


class Provider(ABC):
    def __init__(self, config: ModelConfig) -> None:
        self.config = config

    @abstractmethod
    def complete(self, messages: list[dict[str, str]]) -> ProviderResponse:
        raise NotImplementedError
