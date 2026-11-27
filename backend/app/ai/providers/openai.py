"""OpenAI 官方 Provider（AIProviderType.OPENAI）。

真实端点 ``https://api.openai.com/v1/chat/completions``，使用
``Authorization: Bearer`` 认证并启用 ``response_format=json_object`` 的
JSON mode，保证结构化输出可被 ``parse_response`` 校验。
"""

from __future__ import annotations

from .base import OpenAIProtocolProvider


class OpenAIProvider(OpenAIProtocolProvider):
    """OpenAI 官方实现；与 DeepSeek / 兼容端点共享协议，业务层无感切换。"""

    provider_type = "openai"
    default_base_url = "https://api.openai.com/v1"
    default_model = "gpt-4o-mini"
    supports_json_mode = True
