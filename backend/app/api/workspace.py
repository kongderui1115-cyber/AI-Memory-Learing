"""Same-origin website configuration and initial-use APIs."""

from datetime import date

from fastapi import APIRouter, Depends, Query, Request, Response

from app.api.dependencies import (
    current_user,
    database,
    expected_version,
    idempotency_key,
    request_info,
)
from app.contracts.insights import ReviewWorkload, WorkspaceInsights
from app.contracts.models import TokenResponse
from app.contracts.processing import ProcessingProgress
from app.contracts.workspace import (
    EmailWrite,
    MemoryPreferencesWrite,
    ModelConnect,
    NotionConnect,
    NotionSecretWrite,
    ProfileWrite,
    RegisterRequest,
)
from app.services import accounts, insights, mail, review_workload, workspace
from app.services.common import ServiceError

router = APIRouter(tags=["workspace"])
actor_dependency = Depends(current_user)
db_dependency = Depends(database)
version_dependency = Depends(expected_version)
key_dependency = Depends(idempotency_key)


def _session_cookie_secure(request):
    return request.app.state.settings.app_env == "production" or request.url.scheme == "https"


def set_session_cookie(response, request, token):
    response.set_cookie(
        "memory_session",
        token,
        httponly=True,
        samesite="lax",
        path="/",
        secure=_session_cookie_secure(request),
        max_age=request.app.state.settings.access_token_expire_minutes * 60,
    )


def clear_session_cookie(response, request):
    # Browsers match Secure/HttpOnly/SameSite/path when deleting a cookie.
    response.delete_cookie(
        "memory_session",
        path="/",
        httponly=True,
        samesite="lax",
        secure=_session_cookie_secure(request),
    )


@router.post("/auth/register", response_model=TokenResponse, status_code=201)
async def register(body: RegisterRequest, request: Request, response: Response, db=db_dependency):
    ip, request_id = request_info(request)
    _user_id, error = await workspace.register(db, body, ip, request_id)
    if error:
        raise ServiceError(
            error,
            "注册请求过于频繁，请稍后重试" if error == "RATE_LIMITED" else "该邮箱已注册，请登录",
        )
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
        raise ServiceError(error, "账户已创建，请重新登录")
    set_session_cookie(response, request, token)
    return TokenResponse(
        access_token=token,
        expires_in_seconds=request.app.state.settings.access_token_expire_minutes * 60,
    )


@router.get("/workspace")
async def overview(actor=actor_dependency, db=db_dependency):
    return await workspace.overview(db, actor.user_id)


@router.get("/workspace/settings")
async def settings(actor=actor_dependency, db=db_dependency):
    return await workspace.settings_read(db, actor.user_id)


@router.get("/workspace/processing", response_model=ProcessingProgress)
async def processing(request: Request, actor=actor_dependency, db=db_dependency):
    return await workspace.processing(db, request.app.state.settings, actor.user_id)


@router.get("/workspace/insights", response_model=WorkspaceInsights)
async def learning_insights(
    days: int = Query(default=14, ge=1, le=90),
    from_date: date | None = None,
    to_date: date | None = None,
    actor=actor_dependency,
    db=db_dependency,
):
    return await insights.overview(db, actor.user_id, days, from_date, to_date)


@router.get("/workspace/review-workload", response_model=ReviewWorkload)
async def workload(request: Request, actor=actor_dependency, db=db_dependency):
    return await review_workload.read(db, request.app.state.settings, actor.user)


@router.put("/workspace/profile")
async def profile(
    body: ProfileWrite, actor=actor_dependency, db=db_dependency, version=version_dependency
):
    return await workspace.save_profile(db, actor.user_id, body, version)


@router.put("/workspace/memory-preferences")
async def memory_preferences(
    body: MemoryPreferencesWrite, actor=actor_dependency, db=db_dependency, version=version_dependency
):
    return await workspace.save_memory_preferences(db, actor.user_id, body, version)


@router.put("/workspace/email")
async def email(
    body: EmailWrite,
    request: Request,
    actor=actor_dependency,
    db=db_dependency,
    version=version_dependency,
):
    return await workspace.save_email(db, request.app.state.settings, actor.user_id, body, version)


@router.post("/workspace/email/test", status_code=202)
async def email_test(
    request: Request, actor=actor_dependency, db=db_dependency, key=key_dependency
):
    return await mail.queue_test(db, request.app.state.settings, actor.user_id, key)


@router.put("/workspace/notion/token")
async def notion_token(
    body: NotionSecretWrite, request: Request, actor=actor_dependency, db=db_dependency
):
    row = await workspace.save_notion_token(
        db, request.app.state.settings, actor.user_id, body.token
    )
    return {"saved": True, "integration_id": row.id, "connection_tested": False}


@router.get("/workspace/notion/discover")
async def discover(
    request: Request,
    q: str = Query(default="", max_length=100),
    actor=actor_dependency,
    db=db_dependency,
):
    return await workspace.discover_sources(db, request.app.state.settings, actor.user_id, q)


@router.post("/workspace/notion/connect", status_code=202)
async def connect(body: NotionConnect, request: Request, actor=actor_dependency, db=db_dependency):
    return await workspace.connect_notion(db, request.app.state.settings, actor.user_id, body)


@router.put("/workspace/model")
async def model(body: ModelConnect, request: Request, actor=actor_dependency, db=db_dependency):
    return await workspace.save_model(db, request.app.state.settings, actor.user_id, body)


@router.post("/workspace/onboarding/complete")
async def finish(actor=actor_dependency, db=db_dependency):
    await workspace.finish(db, actor.user_id)
    return {"completed": True}
