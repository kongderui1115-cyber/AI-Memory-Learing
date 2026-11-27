"""Administrator-only cross-user API."""

from datetime import date, datetime
from uuid import UUID
from fastapi import APIRouter, Depends, Query, Request
from app.api.dependencies import (
    administrator,
    current_user,
    database,
    expected_version,
    idempotency_key,
    request_info,
)
from app.contracts.admin_analytics import AdminAnalytics
from app.contracts.core import (
    AuditRead,
    KnowledgeRead,
    SessionRead,
    UserAccount,
    UserCreate,
    UserUpdate,
)
from app.contracts.models import Page, ReviewHistoryRead
from app.services import admin as service, admin_analytics, learning

router = APIRouter(tags=["administration"])
Limit = Query(default=20, ge=1, le=100)


@router.get("/admin/overview")
async def overview(request: Request, actor=Depends(administrator), db=Depends(database)):
    return await service.overview(db, actor, *request_info(request))


@router.get("/admin/analytics", response_model=AdminAnalytics)
async def analytics(
    request: Request,
    days: int = Query(default=30, ge=1, le=90),
    from_date: date | None = None,
    to_date: date | None = None,
    actor=Depends(administrator),
    db=Depends(database),
):
    response = await admin_analytics.analytics(
        db, actor, *request_info(request), days, from_date, to_date
    )
    return response


@router.get("/admin/users", response_model=Page[UserAccount])
async def users(
    request: Request,
    limit: int = Limit,
    cursor: str | None = None,
    q: str | None = Query(default=None, max_length=200),
    actor=Depends(administrator),
    db=Depends(database),
):
    return await service.users(db, actor, *request_info(request), limit, cursor, q)


@router.post("/admin/users", response_model=UserAccount, status_code=201)
async def user_create(
    body: UserCreate,
    request: Request,
    actor=Depends(administrator),
    db=Depends(database),
    key=Depends(idempotency_key),
):
    return await service.create_user(
        db, request.app.state.settings, actor, body, key, *request_info(request)
    )


@router.patch("/admin/users/{user_id}", response_model=UserAccount)
async def user_update(
    user_id: UUID,
    body: UserUpdate,
    request: Request,
    actor=Depends(administrator),
    db=Depends(database),
    version=Depends(expected_version),
):
    return await service.update_user(db, actor, user_id, body, version, *request_info(request))


@router.get("/admin/users/{user_id}/overview")
async def user_overview(
    user_id: UUID, request: Request, actor=Depends(administrator), db=Depends(database)
):
    return await service.user_overview(db, actor, user_id, *request_info(request))


@router.get("/admin/users/{user_id}/knowledge-points", response_model=Page[KnowledgeRead])
async def user_knowledge(
    user_id: UUID,
    request: Request,
    limit: int = Limit,
    cursor: str | None = None,
    actor=Depends(administrator),
    db=Depends(database),
):
    await service.record_access(db, actor, user_id, "knowledge-points", *request_info(request))
    return await learning.list_knowledge(db, user_id, limit=limit, cursor=cursor)


@router.get("/admin/users/{user_id}/review-history", response_model=Page[ReviewHistoryRead])
async def user_history(
    user_id: UUID,
    request: Request,
    limit: int = Limit,
    cursor: str | None = None,
    actor=Depends(administrator),
    db=Depends(database),
):
    await service.record_access(db, actor, user_id, "review-history", *request_info(request))
    return await learning.list_history(db, user_id, limit, cursor, None, None, None, None, None)


@router.get("/admin/sessions", response_model=Page[SessionRead])
async def sessions(
    request: Request,
    limit: int = Limit,
    cursor: str | None = None,
    user_id: UUID | None = None,
    online: bool | None = None,
    from_time: datetime | None = Query(default=None, alias="from"),
    to_time: datetime | None = Query(default=None, alias="to"),
    actor=Depends(administrator),
    db=Depends(database),
):
    return await service.sessions(
        db,
        request.app.state.settings,
        actor,
        *request_info(request),
        limit,
        cursor,
        user_id,
        online,
        from_time,
        to_time,
        True,
    )


@router.get("/auth/sessions", response_model=Page[SessionRead])
async def own_sessions(
    request: Request,
    limit: int = Limit,
    cursor: str | None = None,
    actor=Depends(current_user),
    db=Depends(database),
):
    return await service.sessions(
        db, request.app.state.settings, actor, *request_info(request), limit, cursor
    )


@router.get("/admin/audit-events", response_model=Page[AuditRead])
async def audit_events(
    request: Request,
    limit: int = Limit,
    cursor: str | None = None,
    user_id: UUID | None = None,
    severity: str | None = Query(default=None, pattern="^(info|warning|high)$"),
    action: str | None = Query(default=None, max_length=64),
    from_time: datetime | None = Query(default=None, alias="from"),
    to_time: datetime | None = Query(default=None, alias="to"),
    actor=Depends(administrator),
    db=Depends(database),
):
    return await service.logs(
        db,
        actor,
        *request_info(request),
        limit,
        cursor,
        user_id,
        severity,
        action,
        from_time,
        to_time,
    )
