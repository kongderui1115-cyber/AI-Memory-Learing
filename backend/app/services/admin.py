"""Administrative queries with explicit target user and audit trails."""

import asyncio
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import exists, func, select, text

from app.contracts.core import AuditRead, SessionRead, UserAccount
from app.models import (
    AuditEvent,
    Chapter,
    ChapterJob,
    DailyReviewTask,
    KnowledgePoint,
    ReviewHistory,
    Subject,
    User,
    UserSession,
)
from app.security import hash_password
from app.services.accounts import audit
from app.services.common import (
    ServiceError,
    check_version,
    lock_owner,
    page,
    remember,
    replay,
    utcnow,
)
from app.services import learning


async def staff(session, actor):
    user = await session.get(User, actor.user_id)
    if user is None or not user.is_active or user.role != "admin":
        raise ServiceError("FORBIDDEN", "需要管理员权限")
    return user


async def target_user(session, user_id):
    user = await session.get(User, user_id)
    if user is None:
        raise ServiceError("RESOURCE_NOT_FOUND", "用户不存在")
    return user


async def users(db, actor, ip, request_id, limit, cursor, q=None):
    async with db.transaction() as session:
        await staff(session, actor)
        query = select(User)
        if q:
            query = query.where(User.email.ilike(f"%{q}%") | User.display_name.ilike(f"%{q}%"))
        rows, cursor, more = await page(session, query, User, limit, cursor)
        audit(session, actor.user, "admin_users_read", "users", "allowed", ip, request_id)
        return {
            "items": [UserAccount.model_validate(row) for row in rows],
            "next_cursor": cursor,
            "has_more": more,
        }


async def create_user(db, settings, actor, body, key, ip, request_id):
    operation = "admin:users:create"
    async with db.transaction() as session:
        user = await lock_owner(session, actor.user_id)
        if user.role != "admin":
            raise ServiceError("FORBIDDEN", "需要管理员权限")
        previous, digest = await replay(
            session,
            actor.user_id,
            operation,
            key,
            body.model_dump(mode="json"),
            settings.secret_key,
        )
        if previous:
            return UserAccount.model_validate(await target_user(session, previous.resource_id))
        values = body.model_dump(exclude={"password"})
        values["email"] = str(body.email).casefold()
        row = User(password_hash=await asyncio.to_thread(hash_password, body.password), **values)
        session.add(row)
        await session.flush()
        remember(session, actor.user_id, operation, key, digest, row.id)
        audit(session, actor.user, "user_created", str(row.id), "allowed", ip, request_id, row.id)
        return UserAccount.model_validate(row)


async def update_user(db, actor, user_id, body, version, ip, request_id):
    async with db.transaction() as session:
        await session.execute(text("SELECT pg_advisory_xact_lock(7310116)"))
        await staff(session, actor)
        row = await session.scalar(select(User).where(User.id == user_id).with_for_update())
        if row is None:
            raise ServiceError("RESOURCE_NOT_FOUND", "用户不存在")
        check_version(row, version)
        values = body.model_dump(exclude_unset=True)
        if any(value is None for value in values.values()):
            raise ServiceError("VALIDATION_ERROR", "账号字段不能设置为空")
        losing_admin = (
            row.is_active
            and row.role == "admin"
            and (values.get("is_active") is False or values.get("role") == "user")
        )
        if losing_admin:
            count = await session.scalar(
                select(func.count()).select_from(User).where(User.is_active, User.role == "admin")
            )
            if count <= 1:
                raise ServiceError("INVALID_STATE", "至少保留一个启用的管理员")
        revoke = values.get("is_active") is False or (
            "role" in values and values["role"] != row.role
        )
        for name, value in values.items():
            setattr(row, name, value)
        row.version += 1
        if revoke:
            for active in await session.scalars(
                select(UserSession).where(
                    UserSession.user_id == row.id, UserSession.logged_out_at.is_(None)
                )
            ):
                active.logged_out_at = utcnow()
        audit(session, actor.user, "user_updated", str(row.id), "allowed", ip, request_id, row.id)
        return await learning.refreshed(session, row, UserAccount)


async def record_access(db, actor, target_id, resource, ip, request_id):
    async with db.transaction() as session:
        await staff(session, actor)
        user = await target_user(session, target_id)
        audit(
            session, actor.user, "admin_user_read", resource, "allowed", ip, request_id, target_id
        )
        return UserAccount.model_validate(user)


async def sessions(
    db,
    settings,
    actor,
    ip,
    request_id,
    limit,
    cursor,
    user_id=None,
    online=None,
    start=None,
    end=None,
    admin=False,
):
    learning.validate_time_range(start, end)
    now = utcnow()
    cutoff = now - timedelta(seconds=settings.online_window_seconds)
    async with db.transaction() as session:
        if admin:
            await staff(session, actor)
            audit(
                session,
                actor.user,
                "admin_sessions_read",
                "sessions",
                "allowed",
                ip,
                request_id,
                user_id,
            )
        else:
            user_id = actor.user_id
        query = select(UserSession)
        if user_id:
            query = query.where(UserSession.user_id == user_id)
        if start:
            query = query.where(UserSession.created_at >= start)
        if end:
            query = query.where(UserSession.created_at <= end)
        online_condition = (
            UserSession.logged_out_at.is_(None)
            & (UserSession.last_seen_at >= cutoff)
            & (UserSession.expires_at > now)
        )
        online_condition = online_condition & exists(
            select(User.id).where(User.id == UserSession.user_id, User.is_active)
        )
        if online is not None:
            query = query.where(online_condition if online else ~online_condition)
        rows, cursor, more = await page(session, query, UserSession, limit, cursor)
        owners = {
            user.id: user
            for user in await session.scalars(
                select(User).where(User.id.in_({row.user_id for row in rows}))
            )
        }
        items = []
        for row in rows:
            user = owners[row.user_id]
            values = {
                name: getattr(row, name)
                for name in (
                    "id",
                    "user_id",
                    "created_at",
                    "last_seen_at",
                    "expires_at",
                    "logged_out_at",
                    "ip_address",
                    "user_agent",
                )
            }
            values.update(
                email=user.email,
                display_name=user.display_name,
                online=user.is_active
                and row.logged_out_at is None
                and row.expires_at > now
                and row.last_seen_at >= cutoff,
            )
            items.append(SessionRead(**values))
        return {"items": items, "next_cursor": cursor, "has_more": more}


async def logs(
    db,
    actor,
    ip,
    request_id,
    limit,
    cursor,
    user_id=None,
    severity=None,
    action=None,
    start=None,
    end=None,
):
    learning.validate_time_range(start, end)
    async with db.transaction() as session:
        await staff(session, actor)
        query = select(AuditEvent)
        if user_id:
            query = query.where(
                (AuditEvent.actor_id == user_id) | (AuditEvent.target_user_id == user_id)
            )
        if severity:
            query = query.where(AuditEvent.severity == severity)
        if action:
            query = query.where(AuditEvent.action == action)
        if start:
            query = query.where(AuditEvent.created_at >= start)
        if end:
            query = query.where(AuditEvent.created_at <= end)
        rows, cursor, more = await page(session, query, AuditEvent, limit, cursor)
        audit(session, actor.user, "audit_read", "audit-events", "allowed", ip, request_id)
        return {
            "items": [AuditRead.model_validate(row) for row in rows],
            "next_cursor": cursor,
            "has_more": more,
        }


async def user_overview(db, actor, user_id, ip, request_id):
    user = await record_access(db, actor, user_id, "learning-overview", ip, request_id)
    now = utcnow()
    zone = ZoneInfo(user.timezone)
    today = now.astimezone(zone).date()
    start, end = (
        datetime.combine(today, time.min, zone),
        datetime.combine(today + timedelta(days=1), time.min, zone),
    )
    async with db.transaction() as session:
        knowledge_count = await session.scalar(
            select(func.count())
            .select_from(KnowledgePoint)
            .where(KnowledgePoint.user_id == user_id)
        )
        chapter_count = await session.scalar(
            select(func.count()).select_from(Chapter).where(Chapter.user_id == user_id)
        )
        completed = await session.scalar(
            select(func.count())
            .select_from(ReviewHistory)
            .where(
                ReviewHistory.user_id == user_id,
                ReviewHistory.reviewed_at >= start,
                ReviewHistory.reviewed_at < end,
            )
        )
        due = await session.scalar(
            select(func.count())
            .select_from(DailyReviewTask)
            .where(
                DailyReviewTask.user_id == user_id,
                DailyReviewTask.status.in_(["pending", "in_progress"]),
                DailyReviewTask.scheduled_due_at < end,
            )
        )
        overdue = await session.scalar(
            select(func.count())
            .select_from(DailyReviewTask)
            .where(
                DailyReviewTask.user_id == user_id,
                DailyReviewTask.status.in_(["pending", "in_progress"]),
                DailyReviewTask.scheduled_due_at < start,
            )
        )
        return {
            "user": user,
            "local_date": today,
            "knowledge_count": knowledge_count,
            "chapter_count": chapter_count,
            "today_completed": completed,
            "today_remaining": due,
            "overdue": overdue,
        }


async def overview(db, actor, ip, request_id):
    now = utcnow()
    zone = ZoneInfo(actor.user.timezone)
    start = datetime.combine(now.astimezone(zone).date(), time.min, zone)
    async with db.transaction() as session:
        await staff(session, actor)
        counts = {}
        for name, model in [
            ("users", User),
            ("subjects", Subject),
            ("knowledge_points", KnowledgePoint),
            ("chapters", Chapter),
        ]:
            counts[name] = await session.scalar(select(func.count()).select_from(model))
        counts["today_knowledge_created"] = await session.scalar(
            select(func.count())
            .select_from(KnowledgePoint)
            .where(KnowledgePoint.created_at >= start)
        )
        counts["today_reviews_completed"] = await session.scalar(
            select(func.count())
            .select_from(ReviewHistory)
            .where(ReviewHistory.reviewed_at >= start)
        )
        jobs = (
            await session.execute(
                select(ChapterJob.status, func.count()).group_by(ChapterJob.status)
            )
        ).all()
        audit(
            session, actor.user, "admin_overview_read", "system-overview", "allowed", ip, request_id
        )
        return {
            "as_of": now,
            "timezone": actor.user.timezone,
            "counts": counts,
            "chapter_jobs": dict(jobs),
        }
