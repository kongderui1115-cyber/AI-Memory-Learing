"""渠道基类：统一凭据校验、HTTP 响应解析、请求元数据脱敏。

send() 第一步强制 validate_config()：缺凭据立即抛 ConfigMissingError，
在发起任何 I/O 之前终止，绝不「假推送成功」。
"""

from __future__ import annotations

import json
from typing import Any

from ..config import ChannelConfig
from ..errors import (
    ChannelDeliveryError,
    ChannelDisabledError,
    ConfigMissingError,
)
from ..ports import NotificationChannel, RenderedMessage, SendResult
from ..retry import is_retryable_status
from ..transports import (
    HttpResult,
    HttpTransport,
    SmtpTransport,
    redact_mapping,
    safe_url,
)


class BaseChannel(NotificationChannel):
    """所有内置渠道的公共基类。"""

    #: (logical_name, default_env_var) —— 秘密，仅从环境变量读取
    credential_spec: tuple[tuple[str, str], ...] = ()
    #: 必需的非秘密 settings 键
    settings_spec: tuple[str, ...] = ()
    request_timeout: float = 10.0

    def validate_config(self, config: ChannelConfig) -> None:
        missing: list[str] = []
        for logical, env in self.credential_spec:
            if not config.credential(logical, env):
                missing.append(env)
        for key in self.settings_spec:
            if config.setting(key) in (None, ""):
                missing.append(f"settings.{key}")
        if missing:
            raise ConfigMissingError(self.channel_type, missing)
        if not config.is_enabled:
            raise ChannelDisabledError(self.channel_type)
        self._validate_extra(config, missing)
        if missing:
            raise ConfigMissingError(self.channel_type, missing)

    def _validate_extra(self, config: ChannelConfig, missing: list[str]) -> None:
        """子类可追加校验（把缺项 append 进 missing）。"""

    def creds(self, config: ChannelConfig) -> dict[str, str]:
        return config.credential_map(self.credential_spec)

    def send(
        self,
        message: RenderedMessage,
        config: ChannelConfig,
        http: HttpTransport,
        smtp: SmtpTransport,
    ) -> SendResult:
        self.validate_config(config)  # 关键：缺凭据先抛，绝不发请求
        return self._send(message, config, http, smtp)

    def _send(
        self,
        message: RenderedMessage,
        config: ChannelConfig,
        http: HttpTransport,
        smtp: SmtpTransport,
    ) -> SendResult:
        raise NotImplementedError

    # ---- 公共辅助 ----
    def _base_request_meta(
        self, config: ChannelConfig, message: RenderedMessage
    ) -> dict[str, Any]:
        return redact_mapping({
            "channel_type": self.channel_type,
            "credential_ref": config.credential_ref,
            "channel_config_id": config.id,
            "channel_name": config.name,
            "title_length": len(message.title),
            "body_length": len(message.body),
            "part": f"{message.part_index}/{message.part_total}",
        })

    def _get_json(self, http: HttpTransport, url: str) -> dict[str, Any]:
        result = http.request("GET", url, headers={}, body=None, timeout=self.request_timeout)
        return self._http_ok(result, url)

    def _post_json(
        self,
        http: HttpTransport,
        url: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        result = http.request(
            "POST",
            url,
            headers={"Content-Type": "application/json", **(headers or {})},
            body=json.dumps(payload, ensure_ascii=False),
            timeout=self.request_timeout,
        )
        return self._http_ok(result, url)

    @staticmethod
    def _http_ok(result: HttpResult, url: str) -> dict[str, Any]:
        if result.status_code is None or not (200 <= result.status_code < 300):
            raise ChannelDeliveryError(
                f"渠道 HTTP 状态异常: {result.status_code}",
                error_code="EXTERNAL_SERVICE_ERROR",
                retryable=is_retryable_status(result.status_code),
                response_metadata=redact_mapping({
                    "status_code": result.status_code,
                    "url": safe_url(url),
                    "body_excerpt": result.body[:200],
                }),
                status_code=result.status_code,
            )
        return result.json()

    @staticmethod
    def _biz_ok(
        data: dict[str, Any],
        *,
        ok_field: str = "errcode",
        ok_values: tuple[Any, ...] = (0,),
        retryable_codes: tuple[Any, ...] = (),
    ) -> dict[str, Any]:
        code = data.get(ok_field)
        if code is not None and code not in ok_values:
            raise ChannelDeliveryError(
                f"渠道返回业务错误: {ok_field}={code} "
                f"errmsg={data.get('errmsg') or data.get('msg') or data.get('message')}",
                error_code="EXTERNAL_SERVICE_ERROR",
                retryable=code in retryable_codes,
                response_metadata=redact_mapping(dict(data)),
            )
        return data
