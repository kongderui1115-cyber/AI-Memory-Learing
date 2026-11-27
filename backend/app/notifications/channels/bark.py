"""Bark provider for the existing third-party push channel."""

import json

from ..contract_values import ChannelType
from ..errors import ChannelDeliveryError, NotificationError
from ..links import is_http_link
from ..ports import SendResult
from ..retry import is_retryable_status
from ..template import byte_sizer, truncate
from .base import BaseChannel

BARK_ENDPOINT = "https://api.day.app/push"


class BarkChannel(BaseChannel):
    channel_type = ChannelType.THIRD_PARTY_PUSH
    def _validate_extra(self, config, missing):
        if config.setting("endpoint", BARK_ENDPOINT) != BARK_ENDPOINT:
            raise NotificationError("Bark 仅支持官方 HTTPS 推送端点", code="VALIDATION_ERROR")
        if not config.credential("device_key"):
            missing.append(f"{config.credential_ref}_DEVICE_KEY")

    def _send(self, message, config, http, smtp):
        target = message.review_url or ""
        if target and not is_http_link(target):
            raise NotificationError("Bark 复习入口必须为有效的 HTTP(S) 地址", code="VALIDATION_ERROR")
        if len(target.encode("utf-8")) > 1000:
            raise NotificationError("Bark 复习入口过长", code="VALIDATION_ERROR")
        # Keep compact iOS notifications readable and leave the whole note behind the deep link.
        if not target and byte_sizer(message.body) > 1024:
            raise NotificationError("长 Bark 通知需要完整内容入口", code="VALIDATION_ERROR")
        payload = {
            "device_key": config.credential("device_key"),
            "title": truncate(message.title, 160, byte_sizer),
            "body": truncate(message.body, 1024, byte_sizer),
        }
        if target:
            payload["url"] = target
        response = http.request(
            "POST",
            BARK_ENDPOINT,
            headers={"Content-Type": "application/json"},
            body=json.dumps(payload, ensure_ascii=False),
            timeout=self.request_timeout,
        )
        status = response.status_code
        if status is None or not 200 <= status < 300:
            raise ChannelDeliveryError(
                "Bark 未接受推送请求",
                retryable=is_retryable_status(status),
                response_metadata={"http_status": status},
                status_code=status,
            )
        code = response.json().get("code")
        if type(code) is not int or code != 200:
            raise ChannelDeliveryError(
                "Bark 返回失败或响应状态缺失",
                retryable=is_retryable_status(code) if type(code) is int else True,
                response_metadata={"http_status": status},
            )
        return SendResult(
            ok=True,
            request_metadata=self._base_request_meta(config, message),
            response_metadata={
                "provider": "bark",
                "http_status": status,
                "provider_accepted": True,
                "final_delivery": "unconfirmed",
            },
        )
