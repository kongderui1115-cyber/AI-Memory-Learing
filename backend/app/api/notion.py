"""Authenticated source configuration and asynchronous synchronization requests."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import ValidationError

from app.api.dependencies import current_user, database, expected_version, idempotency_key
from app.contracts.models import Page, SyncRunRead
from app.contracts.notion import (
    IntegrationRead,
    IntegrationUpdate,
    IntegrationWrite,
    RawNoteView,
    SourceRead,
    SourceUpdate,
    SourceWrite,
)
from app.models import NotionDataSource, NotionIntegration, RawNote, SyncRun
from app.services import learning, notion
from app.services.common import ServiceError

router = APIRouter(tags=["notion"])
Limit = Query(default=20, ge=1, le=100)
authenticated_user = Depends(current_user)
database_dependency = Depends(database)
idempotency_dependency = Depends(idempotency_key)
version_dependency = Depends(expected_version)


@router.get("/notion/integrations", response_model=Page[IntegrationRead])
async def integrations(
    limit: int = Limit, cursor: str | None = None, actor=authenticated_user, db=database_dependency
):
    return await learning.list_resources(
        db, actor.user_id, NotionIntegration, IntegrationRead, limit=limit, cursor=cursor
    )


@router.post("/notion/integrations", response_model=IntegrationRead, status_code=201)
async def integration_create(
    body: IntegrationWrite,
    request: Request,
    actor=authenticated_user,
    db=database_dependency,
    key=idempotency_dependency,
):
    return await notion.save_integration(db, request.app.state.settings, actor.user_id, body, key)


@router.get("/notion/integrations/{resource_id}", response_model=IntegrationRead)
async def integration_get(resource_id: UUID, actor=authenticated_user, db=database_dependency):
    return await learning.get_resource(
        db, actor.user_id, NotionIntegration, resource_id, IntegrationRead
    )


def merged_update(current, update, schema):
    values = update.model_dump(exclude_unset=True)
    if not values or any(value is None for value in values.values()):
        raise ServiceError("VALIDATION_ERROR", "需要提供非空的配置字段")
    combined = {name: getattr(current, name) for name in schema.model_fields}
    combined.update(values)
    try:
        return schema.model_validate(combined)
    except ValidationError:
        raise ServiceError("VALIDATION_ERROR", "配置字段格式不正确") from None


@router.patch("/notion/integrations/{resource_id}", response_model=IntegrationRead)
async def integration_update(
    resource_id: UUID,
    body: IntegrationUpdate,
    request: Request,
    actor=authenticated_user,
    db=database_dependency,
    version=version_dependency,
):
    current = await learning.get_resource(
        db, actor.user_id, NotionIntegration, resource_id, IntegrationRead
    )
    return await notion.save_integration(
        db,
        request.app.state.settings,
        actor.user_id,
        merged_update(current, body, IntegrationWrite),
        resource_id=resource_id,
        version=version,
    )


@router.get("/notion/data-sources", response_model=Page[SourceRead])
async def sources(
    limit: int = Limit,
    cursor: str | None = None,
    integration_id: UUID | None = None,
    actor=authenticated_user,
    db=database_dependency,
):
    filters = [NotionDataSource.integration_id == integration_id] if integration_id else []
    return await learning.list_resources(
        db, actor.user_id, NotionDataSource, SourceRead, limit=limit, cursor=cursor, filters=filters
    )


@router.post("/notion/data-sources", response_model=SourceRead, status_code=201)
async def source_create(
    body: SourceWrite,
    request: Request,
    actor=authenticated_user,
    db=database_dependency,
    key=idempotency_dependency,
):
    return await notion.save_source(db, request.app.state.settings, actor.user_id, body, key)


@router.get("/notion/data-sources/{resource_id}", response_model=SourceRead)
async def source_get(resource_id: UUID, actor=authenticated_user, db=database_dependency):
    return await learning.get_resource(db, actor.user_id, NotionDataSource, resource_id, SourceRead)


@router.patch("/notion/data-sources/{resource_id}", response_model=SourceRead)
async def source_update(
    resource_id: UUID,
    body: SourceUpdate,
    request: Request,
    actor=authenticated_user,
    db=database_dependency,
    version=version_dependency,
):
    current = await learning.get_resource(
        db, actor.user_id, NotionDataSource, resource_id, SourceRead
    )
    return await notion.save_source(
        db,
        request.app.state.settings,
        actor.user_id,
        merged_update(current, body, SourceWrite),
        resource_id=resource_id,
        version=version,
    )


@router.post("/notion/data-sources/{resource_id}/sync", response_model=SyncRunRead, status_code=202)
async def source_sync(
    resource_id: UUID,
    request: Request,
    actor=authenticated_user,
    db=database_dependency,
    key=idempotency_dependency,
):
    return await notion.enqueue_sync(
        db, request.app.state.settings, actor.user_id, resource_id, key
    )


@router.get("/notion/sync-runs", response_model=Page[SyncRunRead])
async def runs(
    limit: int = Limit,
    cursor: str | None = None,
    data_source_id: UUID | None = None,
    status: str | None = None,
    actor=authenticated_user,
    db=database_dependency,
):
    filters = []
    if data_source_id:
        filters.append(SyncRun.data_source_id == data_source_id)
    if status:
        filters.append(SyncRun.status == status)
    return await learning.list_resources(
        db, actor.user_id, SyncRun, SyncRunRead, limit=limit, cursor=cursor, filters=filters
    )


@router.get("/notion/sync-runs/{resource_id}", response_model=SyncRunRead)
async def run_get(resource_id: UUID, actor=authenticated_user, db=database_dependency):
    return await learning.get_resource(db, actor.user_id, SyncRun, resource_id, SyncRunRead)


@router.post("/notion/sync-runs/{resource_id}/retry", response_model=SyncRunRead, status_code=202)
async def run_retry(resource_id: UUID, actor=authenticated_user, db=database_dependency):
    return await notion.retry_sync(db, actor.user_id, resource_id)


@router.get("/raw-notes", response_model=Page[RawNoteView])
async def originals(
    limit: int = Limit,
    cursor: str | None = None,
    data_source_id: UUID | None = None,
    external_page_id: str | None = None,
    actor=authenticated_user,
    db=database_dependency,
):
    filters = []
    if data_source_id:
        filters.append(RawNote.data_source_id == data_source_id)
    if external_page_id:
        filters.append(RawNote.external_page_id == external_page_id)
    return await learning.list_resources(
        db, actor.user_id, RawNote, RawNoteView, limit=limit, cursor=cursor, filters=filters
    )


@router.get("/raw-notes/{resource_id}", response_model=RawNoteView)
async def original_get(resource_id: UUID, actor=authenticated_user, db=database_dependency):
    return await learning.get_resource(db, actor.user_id, RawNote, resource_id, RawNoteView)
