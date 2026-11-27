"""API 层：路由、鉴权、HTTP 映射（BE-01）。

不直接写 SQL / 调用外部 API；错误响应统一经 :mod:`app.api.errors` 使用契约模型。
"""
from .errors import ApiError, install_request_context
from .health import build_health_router

__all__ = ["ApiError", "install_request_context", "build_health_router"]
