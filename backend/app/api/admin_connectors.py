"""Administrative views of sources, delivery attempts and persisted jobs."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from app.api.dependencies import administrator, database, idempotency_key, request_info
from app.contracts.models import Page
from app.services import admin_connectors as service

router = APIRouter(tags=["administration"])
Limit = Query(default=20, ge=1, le=100)
Cursor = Query(default=None, max_length=256)
JobKind = Literal["notion", "chapter", "review_batch", "notification"]


class SourceRow(BaseModel):
    id: UUID
    user_id: UUID
    owner_name: str
    name: str
    source_type: str
    external_source_id: str
    integration_name: str
    is_enabled: bool
    integration_enabled: bool
    credential_configured: bool
    sync_interval_minutes: int
    next_sync_at: datetime | None
    last_synced_at: datetime | None
    last_status: str | None
    items_imported: int
    items_failed: int


class RunRow(BaseModel):
    id: UUID
    source_id: UUID
    user_id: UUID
    trigger_type: str
    status: str
    items_seen: int
    items_imported: int
    items_failed: int
    attempt: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    next_retry_at: datetime | None
    error_code: str | None


class ChannelRow(BaseModel):
    id: UUID
    user_id: UUID
    owner_name: str
    name: str
    channel_type: str
    is_enabled: bool
    is_default: bool
    credential_configured: bool
    last_status: str | None
    last_attempted_at: datetime | None


class DeliveryRow(BaseModel):
    id: UUID
    job_id: UUID
    channel_id: UUID
    channel_name: str
    channel_type: str
    user_id: UUID
    owner_name: str
    purpose: str
    status: str
    attempt_no: int
    attempted_at: datetime
    duration_ms: int | None
    error_code: str | None
    provider_accepted: bool | None
    final_delivery: str | None


class JobRow(BaseModel):
    id: UUID
    user_id: UUID
    owner_name: str
    kind: JobKind
    name: str
    status: str
    created_at: datetime
    finished_at: datetime | None
    attempt: int | None
    error_code: str | None
    next_attempt_at: datetime | None


@router.get("/admin/sources", response_model=Page[SourceRow])
async def sources(
    request: Request, limit: int = Limit, cursor: str | None = Cursor,
    user_id: UUID | None = None, actor=Depends(administrator), db=Depends(database),
):
    return await service.sources(
        db, request.app.state.settings, actor, request_info(request), limit, cursor, user_id,
    )


@router.get("/admin/sources/{source_id}/runs", response_model=Page[RunRow])
async def source_runs(
    source_id: UUID, request: Request, limit: int = Limit, cursor: str | None = Cursor,
    actor=Depends(administrator), db=Depends(database),
):
    return await service.source_runs(db, actor, request_info(request), source_id, limit, cursor)


@router.post("/admin/sources/{source_id}/sync", response_model=RunRow, status_code=202)
async def source_sync(
    source_id: UUID, request: Request, actor=Depends(administrator), db=Depends(database),
    key=Depends(idempotency_key),
):
    return await service.queue_source(db, request.app.state.settings, actor, request_info(request), source_id, key)


@router.get("/admin/notification-channels", response_model=Page[ChannelRow])
async def channels(
    request: Request, limit: int = Limit, cursor: str | None = Cursor,
    user_id: UUID | None = None, actor=Depends(administrator), db=Depends(database),
):
    return await service.channels(
        db, request.app.state.settings, actor, request_info(request), limit, cursor, user_id,
    )


@router.get("/admin/notification-deliveries", response_model=Page[DeliveryRow])
async def deliveries(
    request: Request, limit: int = Limit, cursor: str | None = Cursor,
    user_id: UUID | None = None, channel_id: UUID | None = None,
    status: Literal["sending", "sent", "failed"] | None = None,
    actor=Depends(administrator), db=Depends(database),
):
    return await service.deliveries(
        db, actor, request_info(request), limit, cursor, user_id, channel_id, status,
    )


@router.get("/admin/jobs", response_model=Page[JobRow])
async def jobs(
    request: Request, limit: int = Limit, cursor: str | None = Cursor,
    user_id: UUID | None = None, kind: JobKind | None = None,
    status: str | None = Query(default=None, pattern=r"^[a-z][a-z_]{0,31}$"),
    actor=Depends(administrator), db=Depends(database),
):
    return await service.jobs(db, actor, request_info(request), limit, cursor, user_id, kind, status)
