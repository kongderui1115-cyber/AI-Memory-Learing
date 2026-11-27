"""Resolve database and authenticated user from the application context."""

from uuid import UUID
from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import ConfigMissingError
from app.services import accounts
from app.services.common import ServiceError

bearer = HTTPBearer(auto_error=False)


def database(request: Request):
    value = request.app.state.database
    if value is None:
        raise ConfigMissingError(["DATABASE_URL", "SECRET_KEY"])
    return value


def request_info(request):
    return (request.client.host if request.client else "unknown", UUID(request.state.request_id))


async def current_user(
    request: Request,
    db=Depends(database),
    credential: HTTPAuthorizationCredentials | None = Depends(bearer),
):
    token = credential.credentials if credential and credential.scheme.lower() == "bearer" else request.cookies.get("memory_session")
    if not token:
        raise ServiceError("AUTH_REQUIRED", "请先登录")
    if credential is None and request.method not in {"GET", "HEAD", "OPTIONS"} and request.headers.get("X-Memory-Client") != "web":
        raise ServiceError("FORBIDDEN", "请求来源校验失败，请刷新页面")
    return await accounts.principal(db, request.app.state.settings, token)


async def administrator(request: Request, actor=Depends(current_user), db=Depends(database)):
    return await accounts.require_admin(db, actor, *request_info(request))


def idempotency_key(value: str = Header(alias="Idempotency-Key", min_length=1, max_length=128)):
    if not value.strip():
        raise ServiceError("VALIDATION_ERROR", "幂等键不能为空")
    return value


def expected_version(value: str = Header(alias="If-Match")):
    try:
        version = int(value.strip('"'))
        if version < 1:
            raise ValueError()
        return version
    except ValueError:
        raise ServiceError("VALIDATION_ERROR", "If-Match应为资源版本") from None
