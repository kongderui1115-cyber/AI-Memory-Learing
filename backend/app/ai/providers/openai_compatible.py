"""OpenAI-compatible 通用 Provider（AIProviderType.OPENAI_COMPATIBLE）。

用于任意兼容 OpenAI chat-completions 协议的第三方/自托管端点：
``AI_BASE_URL`` 必填（没有内置默认端点），``AI_MODEL`` 必填。

保守起见默认**不**启用 JSON mode（并非所有兼容端点都实现
``response_format=json_object``），改为在 system 提示中要求纯 JSON 输出；
部分端点使用 ``api-key`` 头而非 ``Authorization``，可通过构造参数
``auth_header`` / ``auth_scheme`` 适配，无需改动业务代码。
"""

from __future__ import annotations

from ..config import AIProviderConfig
from ..errors import ConfigMissingError, ErrorDetail
from ..ports import Transport
from .base import OpenAIProtocolProvider


class OpenAICompatibleProvider(OpenAIProtocolProvider):
    """通用兼容实现：端点与模型完全由配置驱动。"""

    provider_type = "openai_compatible"
    default_base_url = ""
    default_model = ""
    supports_json_mode = False

    def __init__(
        self,
        config: AIProviderConfig,
        transport: Transport | None = None,
        *,
        extra_headers: dict[str, str] | None = None,
        auth_header: str = "Authorization",
        auth_scheme: str = "Bearer",
    ) -> None:
        if not (config.base_url or "").strip():
            raise ConfigMissingError(
                "openai_compatible 必须通过 AI_BASE_URL 指定兼容端点，拒绝猜测地址",
                details=[ErrorDetail("AI_BASE_URL", "required")],
            )
        super().__init__(
            config,
            transport,
            extra_headers=extra_headers,
            auth_header=auth_header,
            auth_scheme=auth_scheme,
        )
