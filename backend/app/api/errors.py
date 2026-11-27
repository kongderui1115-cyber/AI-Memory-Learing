"""统一错误响应与请求上下文（BE-01）。

严格使用 ``app/contracts/models.py`` 中的 ``ErrorResponse / ErrorBody / ErrorDetail``
构造错误体，错误码与 HTTP 状态映射严格对齐 ``API_CONTRACTS.md`` §1。

依赖 FastAPI / pydantic；本机依赖尚未安装，标注"依赖未安装，未执行运行时验证"，
但文件可用 ``python -m py_compile`` 做真实语法校验。
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping
from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import ConfigMissingError
from app.contracts.models import ErrorBody, ErrorDetail, ErrorResponse

# ---- 契约错误码（API_CONTRACTS.md §1） ----
VALIDATION_ERROR = "VALIDATION_ERROR"
INVALID_STATE = "INVALID_STATE"
UNSUPPORTED_STRATEGY = "UNSUPPORTED_STRATEGY"
AUTH_REQUIRED = "AUTH_REQUIRED"
AUTH_INVALID = "AUTH_INVALID"
FORBIDDEN = "FORBIDDEN"
RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
CONFLICT = "CONFLICT"
DUPLICATE_RESOURCE = "DUPLICATE_RESOURCE"
IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
VERSION_CONFLICT = "VERSION_CONFLICT"
TASK_ALREADY_COMPLETED = "TASK_ALREADY_COMPLETED"
SEMANTIC_VALIDATION_ERROR = "SEMANTIC_VALIDATION_ERROR"
RATE_LIMITED = "RATE_LIMITED"
INTERNAL_ERROR = "INTERNAL_ERROR"
EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE_ERROR"
CONFIG_MISSING = "CONFIG_MISSING"
SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
EXTERNAL_TIMEOUT = "EXTERNAL_TIMEOUT"

HTTP_STATUS_BY_CODE: dict[str, int] = {
    VALIDATION_ERROR: 400,
    INVALID_STATE: 400,
    UNSUPPORTED_STRATEGY: 400,
    AUTH_REQUIRED: 401,
    AUTH_INVALID: 401,
    FORBIDDEN: 403,
    RESOURCE_NOT_FOUND: 404,
    CONFLICT: 409,
    DUPLICATE_RESOURCE: 409,
    IDEMPOTENCY_CONFLICT: 409,
    VERSION_CONFLICT: 409,
    TASK_ALREADY_COMPLETED: 409,
    SEMANTIC_VALIDATION_ERROR: 422,
    RATE_LIMITED: 429,
    INTERNAL_ERROR: 500,
    EXTERNAL_SERVICE_ERROR: 502,
    CONFIG_MISSING: 503,
    SERVICE_UNAVAILABLE: 503,
    EXTERNAL_TIMEOUT: 504,
}

RETRYABLE_CODES: frozenset[str] = frozenset(
    {
        INTERNAL_ERROR,
        EXTERNAL_SERVICE_ERROR,
        CONFIG_MISSING,
        SERVICE_UNAVAILABLE,
        EXTERNAL_TIMEOUT,
        RATE_LIMITED,
    }
)

_STATUS_TO_CODE: dict[int, str] = {
    400: VALIDATION_ERROR,
    401: AUTH_REQUIRED,
    403: FORBIDDEN,
    404: RESOURCE_NOT_FOUND,
    405: VALIDATION_ERROR,
    409: CONFLICT,
    422: SEMANTIC_VALIDATION_ERROR,
    429: RATE_LIMITED,
}


class ApiError(Exception):
    """业务异常：携带契约错误码，由统一异常处理器转换为 ErrorResponse。"""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status: int | None = None,
        details: Iterable[Mapping[str, Any]] | None = None,
        retryable: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status or HTTP_STATUS_BY_CODE.get(code, 500)
        self.details = [dict(item) for item in (details or [])]
        self.retryable = retryable if retryable is not None else (code in RETRYABLE_CODES)


# 便捷构造器（供其它模块 / 后续端点复用）
def config_missing(message: str, *, details: Iterable[Mapping[str, Any]] | None = None) -> ApiError:
    return ApiError(CONFIG_MISSING, message, details=details)


def not_found(message: str = "资源不存在") -> ApiError:
    return ApiError(RESOURCE_NOT_FOUND, message)


def validation_error(
    message: str, *, details: Iterable[Mapping[str, Any]] | None = None
) -> ApiError:
    return ApiError(VALIDATION_ERROR, message, details=details)


def unsupported_strategy(message: str) -> ApiError:
    return ApiError(UNSUPPORTED_STRATEGY, message)


def get_request_id(request: Request) -> str:
    value = getattr(request.state, "request_id", None)
    return value or str(uuid4())


def error_response(
    code: str,
    message: str,
    *,
    request_id: str | UUID,
    details: Iterable[Mapping[str, Any]] | None = None,
    retryable: bool = False,
) -> ErrorResponse:
    """严格用契约错误模型构造可序列化错误响应。"""
    rid = request_id if isinstance(request_id, UUID) else UUID(str(request_id))
    parsed_details = [
        item
        if isinstance(item, ErrorDetail)
        else ErrorDetail(field=item.get("field"), reason=str(item.get("reason", "invalid")))
        for item in (details or [])
    ]
    return ErrorResponse(
        error=ErrorBody(
            code=code,
            message=message,
            details=parsed_details,
            request_id=rid,
            retryable=retryable,
        )
    )


def _json_error(
    request: Request,
    code: str,
    message: str,
    *,
    status: int,
    details: Iterable[Mapping[str, Any]] | None = None,
    retryable: bool = False,
) -> JSONResponse:
    rid = get_request_id(request)
    body = error_response(code, message, request_id=rid, details=details, retryable=retryable)
    return JSONResponse(
        status_code=status,
        content=body.model_dump(mode="json"),
        headers={"X-Request-ID": rid},
    )


def install_request_context(app: FastAPI) -> None:
    """注册 X-Request-ID 中间件与全部统一异常处理器。"""

    @app.middleware("http")
    async def _request_id_middleware(request: Request, call_next: Callable[..., Any]) -> Any:
        try:
            rid = str(UUID(request.headers.get("X-Request-ID", "")))
        except ValueError:
            rid = str(uuid4())
        request.state.request_id = rid
        origin = request.headers.get("Origin")
        config = request.app.state.settings
        allowed = set(config.cors_origins if config else ()) | {str(request.base_url).rstrip("/")}
        if request.method not in {"GET", "HEAD", "OPTIONS"} and origin and origin.rstrip("/") not in allowed:
            return _json_error(request, FORBIDDEN, "请求来源校验失败", status=403)
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
        return _json_error(
            request,
            exc.code,
            exc.message,
            status=exc.status,
            details=exc.details,
            retryable=exc.retryable,
        )

    @app.exception_handler(ConfigMissingError)
    async def _config_missing(request: Request, exc: ConfigMissingError) -> JSONResponse:
        details = [{"field": name, "reason": "未配置或仍为占位符"} for name in exc.missing]
        return _json_error(
            request,
            CONFIG_MISSING,
            str(exc),
            status=HTTP_STATUS_BY_CODE[CONFIG_MISSING],
            details=details,
            retryable=True,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {
                "field": ".".join(str(part) for part in err.get("loc", ())),
                "reason": str(err.get("msg", "invalid")),
            }
            for err in exc.errors()
        ]
        return _json_error(
            request,
            VALIDATION_ERROR,
            "请求参数校验失败",
            status=HTTP_STATUS_BY_CODE[VALIDATION_ERROR],
            details=details,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _STATUS_TO_CODE.get(exc.status_code, INTERNAL_ERROR)
        status = (
            exc.status_code
            if exc.status_code in HTTP_STATUS_BY_CODE.values()
            else HTTP_STATUS_BY_CODE.get(code, 500)
        )
        return _json_error(
            request,
            code,
            str(exc.detail) or "请求失败",
            status=status,
            retryable=code in RETRYABLE_CODES,
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # 不泄露内部异常细节；由结构化日志另行记录（此处不写外部服务）。
        return _json_error(
            request,
            INTERNAL_ERROR,
            "服务内部错误",
            status=HTTP_STATUS_BY_CODE[INTERNAL_ERROR],
            retryable=True,
        )


__all__ = [
    "ApiError",
    "config_missing",
    "not_found",
    "validation_error",
    "unsupported_strategy",
    "error_response",
    "get_request_id",
    "install_request_context",
    "HTTP_STATUS_BY_CODE",
    "RETRYABLE_CODES",
    "CONFIG_MISSING",
    "VALIDATION_ERROR",
    "INTERNAL_ERROR",
    "RESOURCE_NOT_FOUND",
    "UNSUPPORTED_STRATEGY",
]
