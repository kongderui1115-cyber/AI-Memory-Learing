"""AI / Notion 集成层的显式错误类型。

所有外部集成失败都携带 API_CONTRACTS.md 约定的 REST 错误码以及
``retryable`` 标志，确保「缺少凭据」「未授权计费」绝不会被静默降级成
伪造的理解/同步结果。本模块为纯标准库逻辑。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class ErrorDetail:
    """对应契约 ``ErrorDetail``。"""

    field: str | None
    reason: str


class AIIntegrationError(Exception):
    """集成错误基类，携带契约错误码与可重试标记。"""

    code: str = "INTERNAL_ERROR"
    retryable: bool = False

    def __init__(
        self,
        message: str,
        *,
        details: Iterable[ErrorDetail] | None = None,
        error_code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details: list[ErrorDetail] = list(details or [])
        if error_code is not None:
            self.code = error_code

    def to_error_body(self, request_id: str) -> dict[str, Any]:
        """渲染为契约 §1 的统一错误响应（纯逻辑，可直接被 API 层消费）。"""
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": [{"field": d.field, "reason": d.reason} for d in self.details],
                "request_id": request_id,
                "retryable": self.retryable,
            }
        }

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


class ConfigMissingError(AIIntegrationError):
    """未配置密钥 / Token / 计费授权：契约 ``CONFIG_MISSING``。"""

    code = "CONFIG_MISSING"


class BillingNotApprovedError(ConfigMissingError):
    """用户未授权计费调用（``AI_BILLING_APPROVED != true``）。"""


class InvalidStateError(AIIntegrationError):
    """调用日志 / 同步运行的状态机迁移非法：契约 ``INVALID_STATE``。"""

    code = "INVALID_STATE"


class StructuredOutputError(AIIntegrationError):
    """模型结构化输出或学科策略配置未通过契约校验。"""

    code = "VALIDATION_ERROR"


class ProviderAuthError(AIIntegrationError):
    """外部服务 401/403：凭据无效，不可重试。"""

    code = "EXTERNAL_SERVICE_ERROR"
    retryable = False


class ProviderRateLimitedError(AIIntegrationError):
    """外部服务 429：可重试。"""

    code = "RATE_LIMITED"
    retryable = True


class ProviderTimeoutError(AIIntegrationError):
    """连接/读取超时或网关超时：可重试。"""

    code = "EXTERNAL_TIMEOUT"
    retryable = True


class ProviderServiceError(AIIntegrationError):
    """外部 5xx 等可重试服务错误。"""

    code = "EXTERNAL_SERVICE_ERROR"
    retryable = True


class ProviderResponseError(AIIntegrationError):
    """响应不可解析 / 其它 4xx：不可重试。"""

    code = "EXTERNAL_SERVICE_ERROR"
    retryable = False


class NotionAuthError(AIIntegrationError):
    """Notion 返回 401/403：Token 无效或未授权，不可重试。"""

    code = "EXTERNAL_SERVICE_ERROR"
    retryable = False


class NotionSyncError(AIIntegrationError):
    """Notion 同步编排失败。"""

    code = "EXTERNAL_SERVICE_ERROR"


def error_from_http_status(
    status: int, message: str, *, notion: bool = False
) -> AIIntegrationError:
    """把外部 HTTP 状态码映射为可判定 ``retryable`` 的显式错误（纯逻辑）。

    Args:
        status: 外部服务 HTTP 状态码。
        message: 脱敏后的可读错误说明。
        notion: 为 True 时 401/403 使用 ``NotionAuthError``。
    """
    if 200 <= status < 300:
        raise ValueError("2xx 不是错误状态，不应调用 error_from_http_status")
    if status in (401, 403):
        return NotionAuthError(message) if notion else ProviderAuthError(message)
    if status in (408, 504):
        return ProviderTimeoutError(message)
    if status == 429:
        return ProviderRateLimitedError(message)
    if 500 <= status <= 599:
        return ProviderServiceError(message)
    return ProviderResponseError(message)


def is_retryable(error: BaseException) -> bool:
    """判定异常是否可重试（只依据显式标记，不做猜测）。"""
    return bool(getattr(error, "retryable", False))
