"""通知模块异常层次（错误码与 API_CONTRACTS.md 第 1 节对齐）。

设计要点：
- 未配置任何渠道凭据时抛 `ConfigMissingError`（CONFIG_MISSING），绝不「假推送成功」，
  绝不静默降级为 Mock / 假数据（FR-07；PROJECT_STATUS.md BLK-03、BLK-04）。
- 每个异常携带 `code`（对应 REST 错误码）与 `retryable`，供 worker 决定是否进入退避重试。
"""

from __future__ import annotations

from typing import Any


class NotificationError(Exception):
    """通知模块所有异常的基类。"""

    code: str = "INTERNAL_ERROR"
    retryable: bool = False

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        retryable: bool | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code
        if retryable is not None:
            self.retryable = retryable
        self.details: dict[str, Any] = dict(details or {})

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": str(self),
            "retryable": self.retryable,
            "details": dict(self.details),
        }


class ConfigMissingError(NotificationError):
    """渠道凭据未配置（CONFIG_MISSING）。

    个人微信没有官方主动推送 API；FR-07 的 4 种合规实现均要求用户先选择渠道并授权凭据。
    未配置时 Send 路径必须在此终止，不得发起请求、不得返回 sent。
    """

    code = "CONFIG_MISSING"
    retryable = False

    def __init__(self, channel_type: str, missing: list[str] | tuple[str, ...]) -> None:
        self.channel_type = channel_type
        self.missing = tuple(missing)
        joined = ", ".join(self.missing) if self.missing else "(none)"
        super().__init__(
            f"渠道 {channel_type!r} 缺少必需配置或凭据: {joined}；"
            "未配置凭据时禁止推送（不得假推送），请等待用户授权后重试",
            details={"channel_type": channel_type, "missing": list(self.missing)},
        )


class ChannelNotRegisteredError(NotificationError):
    """注册表按 channel_type 解析不到对应插件。"""

    code = "VALIDATION_ERROR"
    retryable = False

    def __init__(self, channel_type: str, registered: tuple[str, ...] = ()) -> None:
        self.channel_type = channel_type
        super().__init__(
            f"未注册的 channel_type={channel_type!r}；已注册: {list(registered)}",
            details={"channel_type": channel_type, "registered": list(registered)},
        )


class ChannelDisabledError(NotificationError):
    """渠道配置被禁用（is_enabled=false）。"""

    code = "INVALID_STATE"
    retryable = False

    def __init__(self, channel_type: str) -> None:
        super().__init__(f"渠道 {channel_type!r} 已禁用 (is_enabled=false)")


class EmptyContentError(NotificationError):
    """推送正文缺少具体知识点内容（违反 FR-07）。"""

    code = "SEMANTIC_VALIDATION_ERROR"
    retryable = False

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"拒绝生成空通知: {reason}；"
            "FR-07 要求正文必须含标题 + 摘要/问题 + 答案要点 + 复习入口"
        )


class TemplateRenderError(NotificationError):
    """模板变量渲染失败（缺变量或模板非法）。"""

    code = "VALIDATION_ERROR"
    retryable = False


class ChannelDeliveryError(NotificationError):
    """渠道返回失败、网络错误或超时。默认可重试，由 worker 依据 retryable 决定退避。"""

    code = "EXTERNAL_SERVICE_ERROR"
    retryable = True

    def __init__(
        self,
        message: str,
        *,
        error_code: str | None = None,
        retryable: bool = True,
        response_metadata: dict[str, Any] | None = None,
        status_code: int | None = None,
    ) -> None:
        self.error_code = error_code or self.code
        self.response_metadata = dict(response_metadata or {})
        self.status_code = status_code
        super().__init__(
            message,
            code="EXTERNAL_TIMEOUT" if error_code == "EXTERNAL_TIMEOUT" else self.code,
            retryable=retryable,
            details={"status_code": status_code, "error_code": self.error_code},
        )
