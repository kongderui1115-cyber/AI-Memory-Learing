"""Live administrator system health telemetry and private backup controls."""

import asyncio
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from app.api.dependencies import administrator, database, idempotency_key, request_info
from app.services import admin_backup
from app.telemetry import MAX_MINUTES

router = APIRouter(prefix="/admin", tags=["admin-operations"])


class TelemetryBucket(BaseModel):
    date: datetime
    requests: int
    errors: int
    latency_ms: float


class TelemetryRead(BaseModel):
    sampled_at: datetime
    window_minutes: int
    cpu: float | None
    memory: float | None
    disk: float | None
    latency_ms: float | None
    p95_latency_ms: float | None
    requests: int
    errors: int
    buckets: list[TelemetryBucket]


class SystemInfo(BaseModel):
    version: str
    started_at: datetime
    background_tasks_enabled: bool
    worker: Literal["running", "paused", "unavailable"]
    redis: Literal["not_configured"]
    backups_enabled: bool


class BackupRead(BaseModel):
    id: UUID
    filename: str
    created_at: datetime
    size_bytes: int


class BackupInventory(BaseModel):
    enabled: bool
    items: list[BackupRead]


@router.get("/telemetry", response_model=TelemetryRead)
async def telemetry(
    request: Request, minutes: int = Query(60, ge=1, le=MAX_MINUTES),
    _actor=Depends(administrator),
):
    return await asyncio.to_thread(request.app.state.telemetry.snapshot, minutes)


@router.get("/system/info", response_model=SystemInfo)
async def system_info(request: Request, _actor=Depends(administrator)):
    settings = request.app.state.settings
    worker = request.app.state.background_worker
    return {
        "version": request.app.version,
        "started_at": request.app.state.telemetry.started_at,
        "background_tasks_enabled": settings.background_tasks_enabled,
        "worker": (
            "paused" if not settings.background_tasks_enabled
            else "running" if worker is not None and not worker.done()
            else "unavailable"
        ),
        "redis": "not_configured",
        "backups_enabled": admin_backup.backup_location(settings) is not None,
    }


@router.get("/backups", response_model=BackupInventory)
async def backups(request: Request, _actor=Depends(administrator)):
    return await asyncio.to_thread(admin_backup.inventory, request.app.state.settings)


@router.post("/backups", response_model=BackupRead, status_code=201)
async def backup(
    request: Request, actor=Depends(administrator), db=Depends(database), key=Depends(idempotency_key),
):
    return await admin_backup.create(
        db, request.app.state.settings, actor, key, *request_info(request)
    )
