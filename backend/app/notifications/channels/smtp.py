"""NOTIF-04 邮件 SMTP 渠道（FR-08）。

秘密（SMTP_USER / SMTP_PASSWORD）只从环境变量读取；host / port / from / to / tls 为
非秘密，可存 settings 或走 .env.example 环境变量。发送经注入的 SmtpTransport，
本批次不发真实邮件。
"""

from __future__ import annotations

from ..config import ChannelConfig
from ..contract_values import ChannelType
from ..errors import ChannelDeliveryError
from ..ports import RenderedMessage, SendResult
from ..transports import SmtpEnvelope, SmtpTransport, HttpTransport
from .base import BaseChannel


class SmtpChannel(BaseChannel):
    """SMTP 邮件：subject = 渲染标题，正文 = 渲染后的具体知识点内容。"""

    channel_type = ChannelType.SMTP
    max_length = 100000
    length_unit = "char"
    credential_spec = (
        ("user", "SMTP_USER"),
        ("password", "SMTP_PASSWORD"),
    )
    settings_spec = ("to_addresses",)

    def _validate_extra(self, config: ChannelConfig, missing: list[str]) -> None:
        if not config.setting_or_env("host", "SMTP_HOST"):
            missing.append("SMTP_HOST / settings.host")
        if not config.setting_or_env("from_addr", "SMTP_FROM"):
            missing.append("SMTP_FROM / settings.from_addr")

    def _send(
        self,
        message: RenderedMessage,
        config: ChannelConfig,
        http: HttpTransport,
        smtp: SmtpTransport,
    ) -> SendResult:
        creds = self.creds(config)
        host = str(config.setting_or_env("host", "SMTP_HOST"))
        port = int(config.setting_or_env("port", "SMTP_PORT", 587))
        from_addr = str(config.setting_or_env("from_addr", "SMTP_FROM"))
        use_tls = str(config.setting_or_env("tls", "SMTP_TLS", "true")).lower() in (
            "1", "true", "yes", "on",
        )
        to_value = config.setting("to_addresses")
        if isinstance(to_value, str):
            to_addrs = [addr.strip() for addr in to_value.split(",") if addr.strip()]
        else:
            to_addrs = [str(addr) for addr in (to_value or [])]

        envelope = SmtpEnvelope(
            host=host,
            port=port,
            user=creds["user"],
            password=creds["password"],
            from_addr=from_addr,
            to_addrs=to_addrs,
            subject=message.title,
            body=message.body,
            use_tls=use_tls,
        )
        result = smtp.send(envelope)
        if not result.ok:
            raise ChannelDeliveryError(
                f"SMTP 发送失败: {result.error_message}",
                error_code=result.error_code or "EXTERNAL_SERVICE_ERROR",
                retryable=result.retryable,
                response_metadata=envelope.redacted(),
            )
        return SendResult(
            ok=True,
            provider_message_id=result.provider_message_id,
            request_metadata=envelope.redacted(),
            response_metadata={"smtp": "accepted"},
        )
