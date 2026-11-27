"""NOTIF-04 钉钉渠道：群机器人 Webhook + 企业内部应用消息（FR-08）。

两种实现的 HTTP 调用都经注入的 HttpTransport；本批次不发真实请求。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
import urllib.parse

from ..config import ChannelConfig
from ..contract_values import ChannelType
from ..errors import ChannelDeliveryError
from ..ports import RenderedMessage, SendResult
from ..transports import HttpTransport, SmtpTransport, redact_mapping, safe_url
from .base import BaseChannel


def _sign(secret: str, timestamp_ms: str) -> str:
    """钉钉机器人加签：HMAC-SHA256(secret, ts\\nsecret) -> base64（标准库实现）。"""
    string_to_sign = f"{timestamp_ms}\n{secret}"
    digest = hmac.new(secret.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")


class DingtalkWebhookChannel(BaseChannel):
    """钉钉群机器人 Webhook（可选加签）。"""

    channel_type = ChannelType.DINGTALK_WEBHOOK
    max_length = 20000
    length_unit = "byte"
    credential_spec = (("webhook_url", "DINGTALK_WEBHOOK_URL"),)

    def _send(
        self,
        message: RenderedMessage,
        config: ChannelConfig,
        http: HttpTransport,
        smtp: SmtpTransport,
    ) -> SendResult:
        creds = self.creds(config)
        url = creds["webhook_url"]
        # 加签凭据可选：提供则按钉钉规范追加 timestamp / sign（不发起额外请求）
        secret = config.credential("webhook_secret", "DINGTALK_WEBHOOK_SECRET")
        if secret:
            timestamp_ms = str(int(time.time() * 1000))
            sign = _sign(secret, timestamp_ms)
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}" + urllib.parse.urlencode({
                "timestamp": timestamp_ms,
                "sign": sign,
            })
        payload = {"msgtype": "text", "text": {"content": message.full_text()}}
        data = self._post_json(http, url, payload)
        self._biz_ok(data, retryable_codes=(-1, 310000, 130101))
        return SendResult(
            ok=True,
            provider_message_id=None,
            request_metadata=self._base_request_meta(config, message),
            response_metadata=redact_mapping({
                "errcode": data.get("errcode"),
                "errmsg": data.get("errmsg"),
                "signed": bool(secret),
                "url": safe_url(url),
            }),
        )


class DingtalkAppChannel(BaseChannel):
    """钉钉企业内部应用消息（工作通知）。"""

    channel_type = ChannelType.DINGTALK_APP
    max_length = 20000
    length_unit = "byte"
    credential_spec = (
        ("app_key", "DINGTALK_APP_KEY"),
        ("app_secret", "DINGTALK_APP_SECRET"),
    )
    settings_spec = ("agent_id", "userid_list")

    def _send(
        self,
        message: RenderedMessage,
        config: ChannelConfig,
        http: HttpTransport,
        smtp: SmtpTransport,
    ) -> SendResult:
        creds = self.creds(config)
        token_url = "https://oapi.dingtalk.com/gettoken?" + urllib.parse.urlencode({
            "appkey": creds["app_key"],
            "appsecret": creds["app_secret"],
        })
        token_data = self._get_json(http, token_url)
        self._biz_ok(token_data, retryable_codes=(-1,))
        access_token = token_data.get("access_token")
        if not access_token:
            raise ChannelDeliveryError(
                "钉钉未返回 access_token",
                retryable=False,
                response_metadata=redact_mapping(dict(token_data)),
            )

        send_url = (
            "https://oapi.dingtalk.com/topapi/message/corpconversation/asyncsend_v2?"
            + urllib.parse.urlencode({"access_token": access_token})
        )
        payload = {
            "agent_id": config.setting("agent_id"),
            "userid_list": config.setting("userid_list"),
            "msg": {"msgtype": "text", "text": {"content": message.full_text()}},
        }
        data = self._post_json(http, send_url, payload)
        self._biz_ok(data, retryable_codes=(-1,))
        provider_message_id = str(
            data.get("process_instance_id") or data.get("task_id") or ""
        ) or None
        return SendResult(
            ok=True,
            provider_message_id=provider_message_id,
            request_metadata=self._base_request_meta(config, message),
            response_metadata=redact_mapping({
                "errcode": data.get("errcode"),
                "errmsg": data.get("errmsg"),
                "token_url": safe_url(token_url),
                "send_url": safe_url(send_url),
            }),
        )
