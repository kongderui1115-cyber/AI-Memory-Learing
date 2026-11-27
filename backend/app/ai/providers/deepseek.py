"""DeepSeek Provider（AIProviderType.DEEPSEEK）。

真实端点 ``https://api.deepseek.com/v1/chat/completions``，采用与 OpenAI
兼容的 chat-completions 协议，同样启用 JSON mode。默认模型
``deepseek-chat``；如供应商后续调整模型名，仅需改配置（AI_MODEL）。
"""

from __future__ import annotations

from .base import OpenAIProtocolProvider


class DeepSeekProvider(OpenAIProtocolProvider):
    """DeepSeek 实现：协议兼容 OpenAI，但端点、默认模型与计费主体不同。"""

    provider_type = "deepseek"
    default_base_url = "https://api.deepseek.com/v1"
    default_model = "deepseek-chat"
    supports_json_mode = True
