"""Persistent login and session lifecycle endpoints."""

from fastapi import APIRouter, Depends, Request, Response
from app.api.dependencies import current_user, database, request_info
from app.contracts.core import PasswordChange, UserAccount
from app.contracts.models import TokenRequest, TokenResponse
from app.services import accounts
from app.services.common import ServiceError

router = APIRouter(tags=["auth"])


@router.post("/auth/token", response_model=TokenResponse)
async def login(body: TokenRequest, request: Request, response: Response, db=Depends(database)):
    ip, request_id = request_info(request)
    token, error = await accounts.login(
        db,
        request.app.state.settings,
        str(body.email),
        body.password,
        ip,
        request.headers.get("user-agent", ""),
        request_id,
    )
    if error:
        message = "登录尝试过多，请稍后重试" if error == "RATE_LIMITED" else "邮箱或密码错误"
        raise ServiceError(error, message)
    from app.api.workspace import set_session_cookie
    set_session_cookie(response, request, token)
    return TokenResponse(
        access_token=token,
        expires_in_seconds=request.app.state.settings.access_token_expire_minutes * 60,
    )


@router.get("/me", response_model=UserAccount)
async def me(actor=Depends(current_user)):
    return actor.user


@router.post("/auth/heartbeat")
async def heartbeat(actor=Depends(current_user), db=Depends(database)):
    return {"last_seen_at": await accounts.heartbeat(db, actor)}


@router.post("/auth/logout", status_code=204)
async def logout(request: Request, actor=Depends(current_user), db=Depends(database)):
    await accounts.logout(db, actor, *request_info(request))
    response = Response(status_code=204)
    response.delete_cookie("memory_session", path="/")
    return response


@router.post("/auth/password", status_code=204)
async def password(
    body: PasswordChange, request: Request, actor=Depends(current_user), db=Depends(database)
):
    await accounts.change_password(db, actor, body, *request_info(request))
    response = Response(status_code=204)
    response.delete_cookie("memory_session", path="/")
    return response
