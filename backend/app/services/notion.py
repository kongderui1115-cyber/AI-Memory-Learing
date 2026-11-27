"""PostgreSQL-backed source configuration, immutable originals and resumable sync."""

import asyncio
import hashlib
from dataclasses import replace
from datetime import timedelta

from sqlalchemy import func, or_, select, update

from app.ai.errors import AIIntegrationError
from app.contracts.models import SyncRunRead
from app.contracts.notion import IntegrationRead, SourceRead
from app.integrations.notion.client import NotionHTTPError
from app.integrations.notion.models import parse_utc
from app.integrations.notion.runtime import RuntimeNotionClient
from app.models import (
    Chapter,
    ChapterJob,
    NotionDataSource,
    NotionIntegration,
    RawNote,
    Subject,
    SyncRun,
    User,
)
from app.services.common import (
    ServiceError,
    check_version,
    lock_owner,
    owned,
    remember,
    replay,
    utcnow,
)
from app.services.learning import queue_chapter, refreshed

LIFECYCLE_BATCH = 10
SOURCE_ARCHIVED = "SOURCE_ARCHIVED"


def outstanding_runs(source_id):
    return select(SyncRun.id).where(
        SyncRun.data_source_id == source_id,
        or_(
            SyncRun.status.in_(["pending", "running"]),
            (SyncRun.status == "failed") & SyncRun.next_retry_at.is_not(None),
        ),
    )


def check_credential_ref(user_id, reference):
    prefix = "MEMORY_USER_" + user_id.hex.upper() + "_"
    if not reference.startswith(prefix) or reference == prefix:
        raise ServiceError("FORBIDDEN", "凭据变量必须使用当前用户的专用前缀 " + prefix)


async def save_integration(
    db, settings, user_id, body, key=None, *, resource_id=None, version=None
):
    check_credential_ref(user_id, body.credential_ref)
    async with db.transaction() as session:
        await lock_owner(session, user_id)
        if resource_id:
            row = await owned(session, NotionIntegration, resource_id, user_id, lock=True)
            check_version(row, version)
            for name, value in body.model_dump().items():
                setattr(row, name, value)
            row.version += 1
        else:
            previous, digest = await replay(
                session,
                user_id,
                "notion:integration",
                key,
                body.model_dump(mode="json"),
                settings.secret_key,
            )
            if previous:
                return IntegrationRead.model_validate(
                    await owned(session, NotionIntegration, previous.resource_id, user_id)
                )
            row = NotionIntegration(user_id=user_id, **body.model_dump())
            session.add(row)
            await session.flush()
            remember(session, user_id, "notion:integration", key, digest, row.id)
        return await refreshed(session, row, IntegrationRead)


async def save_source(db, settings, user_id, body, key=None, *, resource_id=None, version=None):
    async with db.transaction() as session:
        await lock_owner(session, user_id)
        integration = await owned(session, NotionIntegration, body.integration_id, user_id)
        await owned(session, Subject, body.subject_id, user_id)
        if body.source_type == "data_source" and integration.api_version < "2025-09-03":
            raise ServiceError("VALIDATION_ERROR", "data_source 需要较新的 Notion API 版本")
        values = body.model_dump()
        values["external_source_id"] = str(body.external_source_id)
        if resource_id:
            row = await owned(session, NotionDataSource, resource_id, user_id, lock=True)
            check_version(row, version)
            for name in ("integration_id", "subject_id", "source_type", "external_source_id"):
                if name == "subject_id" and row.subject_id is None:
                    continue
                previous_value = getattr(row, name)
                if name == "external_source_id":
                    from uuid import UUID

                    previous_value = str(UUID(previous_value))
                if previous_value != values[name]:
                    raise ServiceError("INVALID_STATE", "请为新的来源或学科创建独立数据源")
            if (
                row.subject_id is None
                or row.status_property != body.status_property
                or row.status_mapping != body.status_mapping
            ):
                row.last_cursor = None
                row.last_edited_watermark = None
                row.pending_watermark = None
                row.lifecycle_cursor = None
            for name, value in values.items():
                setattr(row, name, value)
            row.next_sync_at = utcnow()
            row.version += 1
        else:
            previous, digest = await replay(
                session,
                user_id,
                "notion:source",
                key,
                body.model_dump(mode="json"),
                settings.secret_key,
            )
            if previous:
                return SourceRead.model_validate(
                    await owned(session, NotionDataSource, previous.resource_id, user_id)
                )
            row = NotionDataSource(user_id=user_id, next_sync_at=utcnow(), **values)
            session.add(row)
            await session.flush()
            remember(session, user_id, "notion:source", key, digest, row.id)
        return await refreshed(session, row, SourceRead)


async def enqueue_sync(db, settings, user_id, source_id, key, *, trigger="manual"):
    async with db.transaction() as session:
        row = await enqueue_sync_in_transaction(
            session, settings, user_id, source_id, key, trigger=trigger
        )
        return SyncRunRead.model_validate(row) if row is not None else None


async def enqueue_sync_in_transaction(
    session, settings, user_id, source_id, key, *, trigger="manual", reuse_active=False
):
    operation = f"notion:{source_id}:sync"
    await lock_owner(session, user_id)
    source = await owned(session, NotionDataSource, source_id, user_id)
    integration = await owned(session, NotionIntegration, source.integration_id, user_id)
    if trigger == "scheduled":
        moment = utcnow()
        if (
            source.subject_id is None
            or (source.next_sync_at is not None and source.next_sync_at > moment)
            or await session.scalar(outstanding_runs(source.id).limit(1)) is not None
        ):
            return None
        key = f"scheduled-{source.version}-{moment:%Y%m%d%H%M}"
    previous, digest = await replay(session, user_id, operation, key, {}, settings.secret_key)
    if previous:
        return await owned(session, SyncRun, previous.resource_id, user_id)
    if not source.is_enabled or not integration.is_enabled:
        raise ServiceError("INVALID_STATE", "数据源或连接已停用")
    row = None
    if reuse_active:
        if source.subject_id is None:
            raise ServiceError("INVALID_STATE", "请先配置数据源的学科")
        row = await session.scalar(
            select(SyncRun)
            .where(
                SyncRun.user_id == user_id,
                SyncRun.data_source_id == source_id,
                SyncRun.status.in_(("pending", "running")),
            )
            .order_by(SyncRun.created_at.desc(), SyncRun.id.desc())
            .limit(1)
        )
    if row is None:
        row = SyncRun(
            user_id=user_id,
            data_source_id=source_id,
            trigger_type=trigger,
            attempt=0,
            idempotency_key=hashlib.sha256(f"{source_id}:{key}".encode()).hexdigest(),
            watermark_from=source.last_edited_watermark,
            cursor_from=source.last_cursor,
        )
        session.add(row)
        await session.flush()
    remember(session, user_id, operation, key, digest, row.id)
    return row


async def retry_sync(db, user_id, run_id):
    async with db.transaction() as session:
        await lock_owner(session, user_id)
        run = await owned(session, SyncRun, run_id, user_id, lock=True)
        if run.status not in {"failed", "partial"}:
            raise ServiceError("INVALID_STATE", "只有失败或部分完成的同步可以重试")
        run.status = "pending"
        run.next_retry_at = None
        run.error_code = None
        run.error_message = None
        return SyncRunRead.model_validate(run)


def fetch_pages(client, source, candidates):
    restarted = False
    reconciled = []
    if source.source_type == "page_tree":
        pages = client.page_tree(source.external_source_id)
        cursor = None
    else:
        # Keep the query lower bound fixed until every pagination cursor has completed.
        watermark = source.last_edited_watermark
        lower_bound = (watermark - timedelta(minutes=1)).isoformat() if watermark else None
        try:
            result = client.query(
                source.source_type, source.external_source_id,
                watermark=lower_bound, cursor=source.last_cursor,
            )
        except NotionHTTPError as error:
            if not source.last_cursor or error.status_code != 400:
                raise
            # Recover a rejected continuation from the last fully committed watermark.
            result = client.query(source.source_type, source.external_source_id, watermark=lower_bound)
            restarted = True
        pages, cursor = result.pages, result.next_cursor
        if cursor and cursor == source.last_cursor and not restarted:
            raise ServiceError("EXTERNAL_SERVICE_ERROR", "Notion 分页游标重复")
    seen_ids = {page.external_page_id for page in pages}
    for page_id in candidates[:LIFECYCLE_BATCH]:
        if page_id in seen_ids:
            continue
        try:
            page = client.retrieve_page(page_id)
        except NotionHTTPError as error:
            if error.status_code in {403, 404}:
                # Visibility failures cannot establish that a source was deleted.
                continue
            raise
        if page.is_archived:
            reconciled.append(page)
    lifecycle_cursor = candidates[LIFECYCLE_BATCH - 1] if len(candidates) > LIFECYCLE_BATCH else None
    pages = [
        page if page.is_archived else replace(
            page, content_markdown=client.markdown(page.external_page_id)
        )
        for page in pages
    ]
    return pages, cursor, restarted, reconciled, lifecycle_cursor


async def lifecycle_candidates(session, source):
    query = select(RawNote.external_page_id).where(
        RawNote.user_id == source.user_id, RawNote.data_source_id == source.id
    )
    if source.lifecycle_cursor:
        query = query.where(RawNote.external_page_id > source.lifecycle_cursor)
    rows = await session.scalars(
        query.distinct().order_by(RawNote.external_page_id).limit(LIFECYCLE_BATCH + 1)
    )
    return rows.all()


def chapter_status(page, source):
    value = page.properties.get(source.status_property, {})
    if not value and source.source_type == "page_tree":
        return None
    option = value.get(value.get("type", "status")) or {}
    label = option.get("name")
    if label not in source.status_mapping:
        raise ServiceError("VALIDATION_ERROR", "Notion 学习状态缺失或没有匹配到状态映射")
    return source.status_mapping[label]


def partition_query_pages(pages, source):
    ready, invalid = [], []
    for page in pages:
        try:
            if not page.is_archived:
                chapter_status(page, source)
        except ServiceError:
            invalid.append(page)
        else:
            ready.append(page)
    return ready, invalid


async def import_pages(session, source, run, pages):
    imported = 0
    watermark = source.pending_watermark or source.last_edited_watermark
    for page in pages:
        if not page.external_version or not page.last_edited_time:
            raise ServiceError("EXTERNAL_SERVICE_ERROR", "Notion 页面缺少版本时间")
        edited = parse_utc(page.last_edited_time)
        status = None if page.is_archived else chapter_status(page, source)
        watermark = max(watermark, edited) if watermark else edited
        latest = await session.scalar(
            select(RawNote)
            .where(RawNote.user_id == source.user_id, RawNote.external_page_id == page.external_page_id)
            .order_by(RawNote.last_edited_time.desc(), RawNote.synced_at.desc(), RawNote.id.desc())
            .limit(1)
        )
        version = page.external_version
        if (
            not page.is_archived and latest and latest.last_edited_time == edited
            and latest.note_metadata.get("source_archived")
        ):
            version += ":restored"
        exists = await session.scalar(
            select(RawNote.id).where(
                RawNote.data_source_id == source.id,
                RawNote.external_page_id == page.external_page_id,
                RawNote.external_version == version,
            )
        )
        if not exists:
            content, title, url = page.content_markdown, page.title, page.source_url
            metadata = dict(page.metadata)
            if page.is_archived and latest:
                content = latest.content_markdown or ""
                title = title or latest.title
                url = url or latest.source_url
                metadata["created_time"] = (
                    metadata.get("created_time") or latest.note_metadata.get("created_time")
                )
            session.add(
                RawNote(
                    user_id=source.user_id,
                    data_source_id=source.id,
                    sync_run_id=run.id,
                    external_page_id=page.external_page_id,
                    external_version=version,
                    last_edited_time=edited,
                    title=title,
                    content_markdown=content,
                    content_hash=hashlib.sha256(content.encode()).hexdigest(),
                    source_url=url,
                    note_metadata={
                        **metadata,
                        "properties": page.properties,
                        "origin": "notion",
                    },
                )
            )
            imported += 1
        if latest and latest.last_edited_time > edited:
            continue
        chapter = await session.scalar(
            select(Chapter).where(
                Chapter.user_id == source.user_id, Chapter.external_page_id == page.external_page_id
            )
        )
        if page.is_archived:
            if (
                chapter is not None and chapter.subject_id == source.subject_id
                and chapter.notion_archived_at is None
            ):
                chapter.notion_archived_at = utcnow()
                chapter.version += 1
                await session.execute(
                    update(ChapterJob)
                    .where(
                        ChapterJob.chapter_id == chapter.id,
                        ChapterJob.user_id == source.user_id,
                        ChapterJob.status.in_(["pending", "blocked", "failed"]),
                    )
                    .values(
                        status="cancelled", error_code=SOURCE_ARCHIVED,
                        next_attempt_at=None, locked_until=None,
                    )
                )
            continue
        if chapter is None:
            chapter = Chapter(
                user_id=source.user_id,
                subject_id=source.subject_id,
                external_page_id=page.external_page_id,
                title=page.title or "Untitled",
            )
            session.add(chapter)
            await session.flush()
        if chapter.subject_id != source.subject_id:
            raise ServiceError("CONFLICT", "同一 Notion 页面已关联其他学科")
        status = status or chapter.status
        values = {
            "title": page.title or "Untitled",
            "content": page.content_markdown,
            "source_url": page.source_url,
            "status": status,
            "notion_archived_at": None,
        }
        if any(getattr(chapter, name) != value for name, value in values.items()):
            previous_status = chapter.status
            for name, value in values.items():
                setattr(chapter, name, value)
            chapter.version += 1
            if status != "completed":
                chapter.completed_at = None
            elif previous_status != "completed" or chapter.completed_at is None:
                chapter.completed_at = edited
        await queue_chapter(session, chapter)
    return imported, watermark


async def read_source(session, settings, source, integration, transport):
    from app.services.credentials import load_user_settings

    if not source.is_enabled or not integration.is_enabled or source.subject_id is None:
        raise ServiceError("INVALID_STATE", "数据源需要启用并配置学科")
    user = await session.get(User, source.user_id)
    if user is None or not user.is_active:
        raise ServiceError("AUTH_INVALID", "账号不可用")
    check_credential_ref(source.user_id, integration.credential_ref)
    settings = await load_user_settings(
        session, settings, source.user_id, credential_ref=integration.credential_ref
    )
    token = settings.get(integration.credential_ref)
    if not token:
        raise ServiceError("CONFIG_MISSING", "请在运行环境中填写该用户的 Notion Token")
    client = RuntimeNotionClient(
        token=token, api_version=integration.api_version, transport=transport
    )
    candidates = await lifecycle_candidates(session, source)
    return await asyncio.to_thread(fetch_pages, client, source, candidates)


async def record_failure(session, run, source, integration, versions, user_id, started, error):
    await session.scalar(select(User.id).where(User.id == user_id).with_for_update())
    await session.refresh(run, with_for_update=True)
    code = error.code if isinstance(error, (ServiceError, AIIntegrationError)) else "INTERNAL_ERROR"
    # Keep upstream payloads and configuration details out of persisted diagnostics.
    message = {
        "CONFIG_MISSING": "请填写运行时 Notion Token 后手动重试",
        "VALIDATION_ERROR": "请检查 Notion 状态属性及映射",
        "VERSION_CONFLICT": "同步期间配置变化，可重试",
        "RATE_LIMITED": "Notion 暂时限流或过载，已按重试间隔等待",
    }.get(code, "同步失败，请检查来源配置、权限和网络后重试")
    retry_after = 0
    if isinstance(error, NotionHTTPError):
        retry_after = error.retry_after_seconds
        message = {
            401: "Notion Token 无效或已撤销，请检查连接凭据",
            403: "Notion 连接缺少读取权限，请检查连接能力与页面共享",
            404: "Notion 来源不可见，请核对来源 ID 与连接共享状态",
        }.get(error.status_code, message)
    run.status = "failed"
    run.attempt += 1
    run.started_at, run.finished_at = started, utcnow()
    run.error_code, run.error_message = code, message
    retryable = (
        error.retryable if isinstance(error, AIIntegrationError)
        else code in {"EXTERNAL_SERVICE_ERROR", "EXTERNAL_TIMEOUT", "RATE_LIMITED", "VERSION_CONFLICT"}
    )
    run.next_retry_at = None
    if retryable and run.attempt < 5:
        delay = max(retry_after, min(3600, 30 * 2 ** min(run.attempt, 7)))
        run.next_retry_at = run.finished_at + timedelta(seconds=delay)
    else:
        await session.refresh(source, with_for_update=True)
        await session.refresh(integration)
        if (source.version, integration.version) == versions:
            later = run.finished_at + timedelta(
                seconds=max(retry_after, source.sync_interval_minutes * 60)
            )
            if source.next_sync_at is None or source.next_sync_at < later:
                source.next_sync_at = later
    return code


async def process_run(db, settings, run_id, *, transport=None):
    async with db.transaction() as session:
        run = await session.get(SyncRun, run_id)
        if run is None:
            raise ServiceError("RESOURCE_NOT_FOUND", "同步记录不存在")
        user_id = run.user_id
        locked = await session.scalar(
            select(
                func.pg_try_advisory_xact_lock(func.hashtextextended(str(run.data_source_id), 731))
            )
        )
        if not locked:
            return {"status": "busy", "run_id": str(run_id)}
        await session.refresh(run)
        if run.status in {"succeeded", "cancelled", "partial"}:
            return {"status": run.status, "run_id": str(run_id)}
        started = utcnow()
        if run.status == "failed" and (
            run.next_retry_at is None or run.next_retry_at > started
        ):
            return {"status": "deferred", "run_id": str(run_id)}
        source = await owned(session, NotionDataSource, run.data_source_id, user_id)
        integration = await owned(session, NotionIntegration, source.integration_id, user_id)
        versions = (source.version, integration.version)
        try:
            # Keep the advisory lock until the resulting success or failure is committed.
            # This savepoint rolls back partial imports while preserving the failure record.
            async with session.begin_nested():
                pages, cursor, restarted, reconciled, lifecycle_cursor = await read_source(
                    session, settings, source, integration, transport
                )
                await lock_owner(session, user_id)
                await session.refresh(source, with_for_update=True)
                await session.refresh(integration)
                if (source.version, integration.version) != versions:
                    raise ServiceError("VERSION_CONFLICT", "同步期间配置已变化，请重试")
                await session.refresh(run, with_for_update=True)
                run.attempt += 1
                run.started_at = started
                run.watermark_from, run.cursor_from = source.last_edited_watermark, source.last_cursor
                ready, invalid = partition_query_pages(pages, source)
                if restarted:
                    source.last_cursor = None
                    source.pending_watermark = None
                imported, watermark = await import_pages(session, source, run, ready)
                # Recovery lookups are not a complete query window and cannot advance its watermark.
                recovered, _ = await import_pages(session, source, run, reconciled)
                source.lifecycle_cursor = lifecycle_cursor
                if not invalid:
                    source.last_cursor = cursor
                    source.pending_watermark = watermark if cursor else None
                    if not cursor:
                        source.last_edited_watermark = watermark
                source.next_sync_at = utcnow() + timedelta(
                    minutes=0 if cursor and not invalid else source.sync_interval_minutes
                )
                source.version += 1
                run.status = "partial" if invalid else "succeeded"
                run.watermark_to = source.pending_watermark or source.last_edited_watermark
                run.cursor_to = source.last_cursor
                run.items_seen = len(pages) + len(reconciled)
                run.items_imported, run.items_failed = imported + recovered, len(invalid)
                run.finished_at, run.next_retry_at = utcnow(), None
                run.error_code = "VALIDATION_ERROR" if invalid else None
                run.error_message = (
                    "部分页面的学习状态没有匹配，修正状态或映射后重试；已入库页面保留"
                    if invalid else None
                )
            return {
                "status": run.status, "run_id": str(run_id), "count": imported + recovered,
                **({"error_code": run.error_code} if invalid else {}),
            }
        except Exception as error:
            code = await record_failure(
                session, run, source, integration, versions, user_id, started, error
            )
            return {"status": "failed", "run_id": str(run_id), "error_code": code}


async def sync_pending(db, settings):
    async with db.transaction() as session:
        sources = list(
            (
                await session.scalars(
                    select(NotionDataSource).join(
                        NotionIntegration, NotionIntegration.id == NotionDataSource.integration_id
                    ).where(
                        NotionDataSource.is_enabled.is_(True),
                        NotionIntegration.is_enabled.is_(True),
                        NotionDataSource.subject_id.is_not(None),
                        ~outstanding_runs(NotionDataSource.id).exists(),
                        or_(
                            NotionDataSource.next_sync_at.is_(None),
                            NotionDataSource.next_sync_at <= utcnow(),
                        ),
                    )
                )
            ).all()
        )
    for source in sources:
        try:
            await enqueue_sync(
                db,
                settings,
                source.user_id,
                source.id,
                f"scheduled-{source.version}-{utcnow().strftime('%Y%m%d%H%M')}",
                trigger="scheduled",
            )
        except ServiceError as error:
            if error.code not in {"INVALID_STATE", "AUTH_INVALID"}:
                raise
    async with db.transaction() as session:
        run_ids = list(
            (
                await session.scalars(
                    select(SyncRun.id)
                    .where(
                        or_(
                            SyncRun.status.in_(["pending", "running"]),
                            (SyncRun.status == "failed") & (SyncRun.next_retry_at <= utcnow()),
                        )
                    )
                    .order_by(SyncRun.created_at)
                    .limit(100)
                )
            ).all()
        )
    outcomes = [await process_run(db, settings, run_id) for run_id in run_ids]
    return {
        "status": "failed" if any(o["status"] in {"failed", "partial"} for o in outcomes) else "succeeded",
        "count": sum(o.get("count", 0) for o in outcomes),
        "runs": outcomes,
    }
