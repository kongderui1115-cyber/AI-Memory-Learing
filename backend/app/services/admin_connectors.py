"""Staff-only projections over durable connector and background records."""

import hashlib
import re

from sqlalchemy import Boolean, DateTime, Integer, String, and_, case, cast, exists, func, literal, null, select, true, union_all
from sqlalchemy.orm import Bundle

from app.models import (
    Chapter,
    ChapterJob,
    DailyReviewBatch,
    NotificationChannelConfig,
    NotificationDelivery,
    NotificationJob,
    NotionDataSource,
    NotionIntegration,
    SyncRun,
    User,
    UserSecret,
)
from app.services import notion
from app.services.accounts import audit
from app.services.admin import staff
from app.services.common import ServiceError, page

_ERROR_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,47}")


def clean_error_code(value):
    return value if isinstance(value, str) and _ERROR_CODE.fullmatch(value) else None


def credential_exists(user_column, ref_column):
    return exists().where(UserSecret.user_id == user_column, UserSecret.name == ref_column)


async def page_result(session, selection, limit, cursor, *, settings=None):
    """Reuse the stable timestamp/UUID cursor without returning ORM models or JSON payloads."""
    rows = selection.subquery()
    query = select(Bundle("admin_row", *rows.c)).select_from(rows)
    values, next_cursor, has_more = await page(session, query, rows.c, limit, cursor)
    items = []
    for row in values:
        data = dict(row._mapping)
        ref = data.pop("_credential_ref", None)
        if ref and settings and ref.startswith("MEMORY_USER_" + data["user_id"].hex.upper() + "_"):
            data["credential_configured"] = data["credential_configured"] or settings.is_set(ref)
        if "error_code" in data:
            data["error_code"] = clean_error_code(data["error_code"])
        items.append(data)
    return {"items": items, "next_cursor": next_cursor, "has_more": has_more}


async def sources(db, settings, actor, info, limit, cursor, user_id):
    source, integration, run = NotionDataSource, NotionIntegration, SyncRun
    run_owner = (run.data_source_id == source.id, run.user_id == source.user_id)
    latest_run = (
        select(run.status, run.items_imported, run.items_failed)
        .where(*run_owner)
        .order_by(run.created_at.desc(), run.id.desc())
        .limit(1)
        .correlate(source)
        .lateral()
    )
    last_synced = (
        select(func.max(run.finished_at))
        .where(*run_owner, run.status.in_(("succeeded", "partial")))
        .correlate(source)
        .scalar_subquery()
    )
    query = (
        select(
            source.id, source.created_at, source.user_id, User.display_name.label("owner_name"),
            source.name, source.source_type, source.external_source_id,
            integration.name.label("integration_name"), source.is_enabled,
            integration.is_enabled.label("integration_enabled"), source.sync_interval_minutes,
            source.next_sync_at, last_synced.label("last_synced_at"),
            latest_run.c.status.label("last_status"),
            func.coalesce(latest_run.c.items_imported, 0).label("items_imported"),
            func.coalesce(latest_run.c.items_failed, 0).label("items_failed"),
            credential_exists(source.user_id, integration.credential_ref).label("credential_configured"),
            integration.credential_ref.label("_credential_ref"),
        )
        .select_from(source)
        .join(User, User.id == source.user_id)
        .join(integration, and_(integration.id == source.integration_id, integration.user_id == source.user_id))
        .outerjoin(latest_run, true())
    )
    if user_id:
        query = query.where(source.user_id == user_id)
    async with db.transaction() as session:
        await staff(session, actor)
        response = await page_result(session, query, limit, cursor, settings=settings)
        audit(session, actor.user, "admin_sources_read", "notion_sources", "allowed", *info)
        return response


def run_row(run):
    return {
        "id": run.id, "source_id": run.data_source_id, "user_id": run.user_id,
        "trigger_type": run.trigger_type, "status": run.status,
        "items_seen": run.items_seen, "items_imported": run.items_imported, "items_failed": run.items_failed,
        "attempt": run.attempt, "created_at": run.created_at, "started_at": run.started_at,
        "finished_at": run.finished_at, "next_retry_at": run.next_retry_at,
        "error_code": clean_error_code(run.error_code),
    }


async def _source(session, source_id):
    row = await session.get(NotionDataSource, source_id)
    if row is None:
        raise ServiceError("RESOURCE_NOT_FOUND", "Notion 数据源不存在")
    return row


async def source_runs(db, actor, info, source_id, limit, cursor):
    run = SyncRun
    query = select(
        run.id, run.data_source_id.label("source_id"), run.user_id, run.trigger_type, run.status,
        run.items_seen, run.items_imported, run.items_failed, run.attempt, run.created_at,
        run.started_at, run.finished_at, run.next_retry_at, run.error_code,
    )
    async with db.transaction() as session:
        await staff(session, actor)
        source = await _source(session, source_id)
        query = query.where(run.data_source_id == source.id, run.user_id == source.user_id)
        response = await page_result(session, query, limit, cursor)
        audit(session, actor.user, "admin_source_runs_read", str(source_id), "allowed", *info, source.user_id)
        return response


async def queue_source(db, settings, actor, info, source_id, key):
    scoped_key = hashlib.sha256(f"admin-notion:{actor.user_id}:{key}".encode()).hexdigest()
    async with db.transaction() as session:
        await staff(session, actor)
        source = await _source(session, source_id)
        run = await notion.enqueue_sync_in_transaction(
            session, settings, source.user_id, source.id, scoped_key, reuse_active=True
        )
        audit(session, actor.user, "admin_source_sync_queued", str(source_id), "allowed", *info, source.user_id)
        return run_row(run)


async def channels(db, settings, actor, info, limit, cursor, user_id):
    channel, job, delivery = NotificationChannelConfig, NotificationJob, NotificationDelivery
    latest_delivery = (
        select(delivery.status, delivery.attempted_at)
        .select_from(job)
        .join(delivery, and_(delivery.job_id == job.id, delivery.user_id == job.user_id))
        .where(job.channel_config_id == channel.id, job.user_id == channel.user_id)
        .order_by(delivery.attempted_at.desc(), delivery.id.desc())
        .limit(1)
        .correlate(channel)
        .lateral()
    )
    query = (
        select(
            channel.id, channel.created_at, channel.user_id, User.display_name.label("owner_name"),
            channel.name, channel.channel_type, channel.is_enabled, channel.is_default,
            credential_exists(channel.user_id, channel.credential_ref).label("credential_configured"),
            channel.credential_ref.label("_credential_ref"),
            latest_delivery.c.status.label("last_status"),
            latest_delivery.c.attempted_at.label("last_attempted_at"),
        )
        .select_from(channel)
        .join(User, User.id == channel.user_id)
        .outerjoin(latest_delivery, true())
    )
    if user_id:
        query = query.where(channel.user_id == user_id)
    async with db.transaction() as session:
        await staff(session, actor)
        response = await page_result(session, query, limit, cursor, settings=settings)
        audit(session, actor.user, "admin_notification_channels_read", "notification_channels", "allowed", *info)
        return response


async def deliveries(db, actor, info, limit, cursor, user_id, channel_id, status):
    delivery, job, channel = NotificationDelivery, NotificationJob, NotificationChannelConfig
    accepted = delivery.response_metadata["provider_accepted"]
    final = delivery.response_metadata["final_delivery"].astext
    query = (
        select(
            delivery.id, delivery.attempted_at.label("created_at"), delivery.attempted_at,
            delivery.job_id, channel.id.label("channel_id"), channel.name.label("channel_name"),
            channel.channel_type, delivery.user_id, User.display_name.label("owner_name"),
            job.purpose, delivery.status, delivery.attempt_no, delivery.duration_ms, delivery.error_code,
            case((func.jsonb_typeof(accepted) == "boolean", cast(accepted.astext, Boolean))).label("provider_accepted"),
            case((final.in_(("unconfirmed", "confirmed", "delivered", "bounced", "failed")), final)).label(
                "final_delivery"
            ),
        )
        .select_from(delivery)
        .join(job, and_(job.id == delivery.job_id, job.user_id == delivery.user_id))
        .join(channel, and_(channel.id == job.channel_config_id, channel.user_id == job.user_id))
        .join(User, User.id == delivery.user_id)
    )
    if user_id:
        query = query.where(delivery.user_id == user_id)
    if channel_id:
        query = query.where(channel.id == channel_id)
    if status:
        query = query.where(delivery.status == status)
    async with db.transaction() as session:
        await staff(session, actor)
        response = await page_result(session, query, limit, cursor)
        audit(session, actor.user, "admin_notification_deliveries_read", "notification_deliveries", "allowed", *info)
        return response


def _job_selection(kind, model, name, finished_at, attempt, error_code, next_attempt_at):
    return (
        select(
            model.id, model.user_id, User.display_name.label("owner_name"), literal(kind).label("kind"),
            name.label("name"), model.status, model.created_at, finished_at.label("finished_at"),
            attempt.label("attempt"), error_code.label("error_code"), next_attempt_at.label("next_attempt_at"),
        )
        .select_from(model)
        .join(User, User.id == model.user_id)
    )


async def jobs(db, actor, info, limit, cursor, user_id, kind, status):
    missing_time = cast(null(), DateTime(timezone=True))
    missing_error = cast(null(), String)
    chapter, batch, notification = ChapterJob, DailyReviewBatch, NotificationJob
    selections = {
        "notion": _job_selection(
            "notion", SyncRun, NotionDataSource.name, SyncRun.finished_at,
            SyncRun.attempt, SyncRun.error_code, SyncRun.next_retry_at,
        ).join(NotionDataSource, and_(
            NotionDataSource.id == SyncRun.data_source_id, NotionDataSource.user_id == SyncRun.user_id
        )),
        "chapter": _job_selection(
            "chapter", chapter, Chapter.title,
            case((chapter.status.in_(("succeeded", "failed", "cancelled")), chapter.updated_at)),
            chapter.attempt, chapter.error_code, chapter.next_attempt_at,
        ).join(Chapter, and_(Chapter.id == chapter.chapter_id, Chapter.user_id == chapter.user_id)),
        "review_batch": _job_selection(
            "review_batch", batch, literal("每日复习批次"),
            case((batch.status.in_(("ready", "completed")), batch.generated_at)),
            cast(null(), Integer), missing_error, missing_time,
        ),
        "notification": _job_selection(
            "notification", notification, NotificationChannelConfig.name,
            case(
                (notification.status == "sent", notification.sent_at),
                (notification.status.in_(("failed", "cancelled")), notification.updated_at),
            ),
            notification.attempt_count, notification.last_error_code, notification.next_attempt_at,
        ).join(NotificationChannelConfig, and_(
            NotificationChannelConfig.id == notification.channel_config_id,
            NotificationChannelConfig.user_id == notification.user_id,
        )),
    }
    if kind:
        records = selections[kind].subquery()
    else:
        records = union_all(*selections.values()).subquery()
    query = select(*records.c)
    if user_id:
        query = query.where(records.c.user_id == user_id)
    if status:
        query = query.where(records.c.status == status)
    async with db.transaction() as session:
        await staff(session, actor)
        response = await page_result(session, query, limit, cursor)
        audit(session, actor.user, "admin_jobs_read", kind or "all_jobs", "allowed", *info)
        return response
