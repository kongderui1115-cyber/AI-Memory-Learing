"""User-owned AI models, safe readiness checks and recoverable chapter jobs."""

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request

from app.api.dependencies import current_user, database, expected_version, idempotency_key
from app.api.notion import merged_update
from app.contracts.ai_runtime import ProviderUpdate, ProviderWrite
from app.contracts.core import ChapterJobRead
from app.contracts.models import (
    AICallLogRead,
    AIProviderConfigRead,
    Page,
    SubjectStrategyRead,
    SubjectStrategyWrite,
)
from app.models import AICallLog, AIProviderConfig, Chapter, ChapterJob, SubjectStrategy
from app.services import ai_runtime, learning
from app.services.common import ServiceError, lock_owner, owned, remember, replay
from app.services.credentials import load_user_settings

router = APIRouter(tags=["ai"])
authenticated_user = Depends(current_user)
database_dependency = Depends(database)
version_dependency = Depends(expected_version)
idempotency_dependency = Depends(idempotency_key)
Limit = Query(default=20, ge=1, le=100)


@router.get("/ai/providers", response_model=Page[AIProviderConfigRead])
async def providers(
    limit: int = Limit, cursor: str | None = None, actor=authenticated_user, db=database_dependency
):
    return await learning.list_resources(
        db, actor.user_id, AIProviderConfig, AIProviderConfigRead, limit=limit, cursor=cursor
    )


@router.post("/ai/providers", response_model=AIProviderConfigRead, status_code=201)
async def provider_create(
    body: ProviderWrite,
    request: Request,
    actor=authenticated_user,
    db=database_dependency,
    key=idempotency_dependency,
):
    return await ai_runtime.save_provider(db, request.app.state.settings, actor.user_id, body, key)


@router.get("/ai/providers/{resource_id}", response_model=AIProviderConfigRead)
async def provider_get(resource_id: UUID, actor=authenticated_user, db=database_dependency):
    return await learning.get_resource(
        db, actor.user_id, AIProviderConfig, resource_id, AIProviderConfigRead
    )


@router.patch("/ai/providers/{resource_id}", response_model=AIProviderConfigRead)
async def provider_update(
    resource_id: UUID,
    body: ProviderUpdate,
    request: Request,
    actor=authenticated_user,
    db=database_dependency,
    version=version_dependency,
):
    current = await learning.get_resource(
        db, actor.user_id, AIProviderConfig, resource_id, AIProviderConfigRead
    )
    return await ai_runtime.save_provider(
        db,
        request.app.state.settings,
        actor.user_id,
        merged_update(current, body, ProviderWrite),
        resource_id=resource_id,
        version=version,
    )


@router.get("/ai/providers/{resource_id}/readiness")
async def provider_readiness(
    resource_id: UUID, request: Request, actor=authenticated_user, db=database_dependency
):
    async with db.transaction() as session:
        provider = await owned(session, AIProviderConfig, resource_id, actor.user_id)
        config = ai_runtime.provider_settings(provider, request.app.state.settings)
        await ai_runtime.check_destination_binding(session, actor.user_id, config)
        credential_ref, enabled = provider.credential_ref, provider.is_enabled
        settings = await load_user_settings(
            session, request.app.state.settings, actor.user_id, credential_ref=credential_ref
        )
    return {
        "key_configured": settings.is_set(credential_ref),
        "billing_approved": settings.ai_billing_approved,
        "enabled": enabled,
        "connection_tested": False,
    }


@router.get("/ai/calls", response_model=Page[AICallLogRead])
async def calls(
    limit: int = Limit,
    cursor: str | None = None,
    provider_config_id: UUID | None = None,
    status: str | None = None,
    actor=authenticated_user,
    db=database_dependency,
):
    filters = []
    if provider_config_id:
        filters.append(AICallLog.provider_config_id == provider_config_id)
    if status:
        filters.append(AICallLog.status == status)
    return await learning.list_resources(
        db, actor.user_id, AICallLog, AICallLogRead, limit=limit, cursor=cursor, filters=filters
    )


@router.get("/ai/calls/{resource_id}", response_model=AICallLogRead)
async def call_get(resource_id: UUID, actor=authenticated_user, db=database_dependency):
    return await learning.get_resource(db, actor.user_id, AICallLog, resource_id, AICallLogRead)


@router.get("/subjects/{subject_id}/strategy", response_model=SubjectStrategyRead)
async def strategy_get(subject_id: UUID, actor=authenticated_user, db=database_dependency):
    from sqlalchemy import select

    async with db.transaction() as session:
        row = await session.scalar(
            select(SubjectStrategy).where(
                SubjectStrategy.user_id == actor.user_id,
                SubjectStrategy.subject_id == subject_id,
                SubjectStrategy.is_active.is_(True),
            )
        )
        if row is None:
            raise ServiceError("RESOURCE_NOT_FOUND", "当前使用内置通用策略")
        return SubjectStrategyRead.model_validate(row)


@router.put("/subjects/{subject_id}/strategy", response_model=SubjectStrategyRead)
async def strategy_update(
    subject_id: UUID,
    body: SubjectStrategyWrite,
    if_match: str | None = Header(default=None, alias="If-Match"),
    actor=authenticated_user,
    db=database_dependency,
):
    version = expected_version(if_match) if if_match is not None else None
    return await ai_runtime.save_strategy(db, actor.user_id, subject_id, body, version)


@router.get("/chapter-jobs/{resource_id}", response_model=ChapterJobRead)
async def job_get(resource_id: UUID, actor=authenticated_user, db=database_dependency):
    return await learning.get_resource(db, actor.user_id, ChapterJob, resource_id, ChapterJobRead)


@router.post("/chapters/{resource_id}/reanalyze", response_model=ChapterJobRead, status_code=202)
async def chapter_reanalyze(
    resource_id: UUID,
    request: Request,
    actor=authenticated_user,
    db=database_dependency,
    key=idempotency_dependency,
):
    return await ai_runtime.reanalyze_chapter(
        db, request.app.state.settings, actor.user_id, resource_id, key
    )


@router.post("/chapter-jobs/{resource_id}/retry", response_model=ChapterJobRead, status_code=202)
async def job_retry(
    resource_id: UUID,
    request: Request,
    actor=authenticated_user,
    db=database_dependency,
    key=idempotency_dependency,
):
    async with db.transaction() as session:
        await lock_owner(session, actor.user_id)
        job = await owned(session, ChapterJob, resource_id, actor.user_id, lock=True)
        operation = f"ai:job:{resource_id}:retry"
        previous, digest = await replay(
            session, actor.user_id, operation, key, {}, request.app.state.settings.secret_key
        )
        if not previous:
            if job.status not in {"blocked", "failed"}:
                raise ServiceError("INVALID_STATE", "只有失败或等待配置的任务可以重试")
            chapter = await owned(session, Chapter, job.chapter_id, actor.user_id)
            if chapter.notion_archived_at is not None:
                raise ServiceError("INVALID_STATE", "已归档的 Notion 原笔记不能重试")
            job.status, job.error_code, job.next_attempt_at = "pending", None, None
            remember(session, actor.user_id, operation, key, digest, job.id)
        return ChapterJobRead.model_validate(job)
