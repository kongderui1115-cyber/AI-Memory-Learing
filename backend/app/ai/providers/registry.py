"""Provider 注册表：按配置解析实现，切换供应商不改业务代码（AI-01）。"""

from __future__ import annotations

from typing import Mapping, Type

from ..config import AIProviderConfig
from ..errors import ErrorDetail, StructuredOutputError
from ..ports import AIProvider, Transport
from ..validation import AI_PROVIDER_TYPES
from .base import OpenAIProtocolProvider
from .deepseek import DeepSeekProvider
from .openai import OpenAIProvider
from .openai_compatible import OpenAICompatibleProvider

PROVIDER_CLASSES: Mapping[str, Type[OpenAIProtocolProvider]] = {
    "openai": OpenAIProvider,
    "deepseek": DeepSeekProvider,
    "openai_compatible": OpenAICompatibleProvider,
}


def resolve_provider(
    config: AIProviderConfig, *, transport: Transport | None = None
) -> AIProvider:
    """按 ``config.provider`` 返回对应实现。

    ``transport`` 仅用于注入测试替身以隔离外部 HTTP；生产为 None，
    使用真实 ``UrllibTransport``。本函数不发起任何网络请求。
    """
    if config.provider not in AI_PROVIDER_TYPES:
        raise StructuredOutputError(
            f"未知 provider={config.provider!r}",
            details=[ErrorDetail("provider", "unsupported provider type")],
        )
    provider_class = PROVIDER_CLASSES.get(config.provider)
    if provider_class is None:  # 防御：常量与注册表保持一致
        raise StructuredOutputError(
            f"provider={config.provider!r} 暂无注册实现",
            details=[ErrorDetail("provider", "no implementation registered")],
        )
    return provider_class(config, transport=transport)
