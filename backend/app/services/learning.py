"""User-owned learning records and durable review workflows."""

import hashlib
import json
from dataclasses import asdict
from datetime import datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select

from app.contracts.core import ChapterRead, StudySessionRead
from app.contracts.models import (
    DailyBatchRead,
    DailyTaskRead,
    KnowledgePointRead,
    ReviewItemRead,
    ScheduleStateRead,
    SubjectRead,
)
from app.domain import daily_tasks, memory, scheduling
from app.models import (
    Chapter,
    ChapterJob,
    DailyReviewBatch,
    DailyReviewTask,
    KnowledgePoint,
    ReviewHistory,
    ReviewItem,
    ScheduleState,
    StudySession,
    Subject,
    SubjectStrategy,
    User,
    WorkspaceProfile,
)
from app.services.common import (
    ServiceError,
    check_version,
    lock_owner,
    owned,
    page,
    remember,
    replay,
    utcnow,
)
from app.services.review_workload import OPEN_TASK_STATUSES, assigned_today, eligible_due_points


async def refreshed(session, value, schema):
    await session.flush()
    await session.refresh(value)
    return schema.model_validate(value)


async def chapter_ready(session, point):
    if point.chapter_id:
        chapter = await owned(session, Chapter, point.chapter_id, point.user_id)
        if chapter.status != "completed":
            raise ServiceError("INVALID_STATE", "整章完成后才能生成卡片和复习计划")
        return chapter
    return None


def chapter_content_hash(chapter):
    content = json.dumps(
        [chapter.title, chapter.content, str(chapter.subject_id), chapter.source_url],
        ensure_ascii=False,
    )
    return hashlib.sha256(content.encode()).hexdigest()


def chapter_job_cancellation(chapter, content_hash):
    if chapter.notion_archived_at is not None:
        return "SOURCE_ARCHIVED"
    if chapter.status != "completed":
        return "CHAPTER_REOPENED"
    if chapter_content_hash(chapter) != content_hash:
        return "CHAPTER_CHANGED"
    return None


def knowledge_hash(subject_id, title, body):
    content = json.dumps([str(subject_id), title.strip(), body.strip()], ensure_ascii=False)
    return hashlib.sha256(content.encode()).hexdigest()


async def queue_chapter(session, chapter):
    if chapter.status != "completed" or chapter.notion_archived_at is not None:
        return
    if not chapter.completed_at:
        chapter.completed_at = utcnow()
    digest = chapter_content_hash(chapter)
    existing = await session.scalar(
        select(ChapterJob).where(
            ChapterJob.user_id == chapter.user_id,
            ChapterJob.chapter_id == chapter.id,
            ChapterJob.content_hash == digest,
        )
    )
    if existing is None:
        session.add(ChapterJob(user_id=chapter.user_id, chapter_id=chapter.id, content_hash=digest))
    elif existing.status == "cancelled" and existing.error_code in {
        None, "CHAPTER_REOPENED", "CHAPTER_CHANGED", "SOURCE_ARCHIVED",
    }:
        # The exact revision is current again. Reuse its identity and attempt history.
        existing.status = "pending"
        existing.error_code = None
        existing.next_attempt_at = None
        existing.locked_until = None


async def list_resources(db, user_id, model, schema, *, limit=20, cursor=None, filters=()):
    async with db.transaction() as session:
        query = select(model).where(model.user_id == user_id, *filters)
        rows, cursor, more = await page(session, query, model, limit, cursor)
        return {
            "items": [schema.model_validate(row) for row in rows],
            "next_cursor": cursor,
            "has_more": more,
        }


async def get_resource(db, user_id, model, resource_id, schema):
    async with db.transaction() as session:
        return schema.model_validate(await owned(session, model, resource_id, user_id))


async def create_subject(db, settings, user_id, body, key):
    operation = "subjects:create"
    async with db.transaction() as session:
        await lock_owner(session, user_id)
        previous, digest = await replay(
            session, user_id, operation, key, body.model_dump(mode="json"), settings.secret_key
        )
        if previous:
            return SubjectRead.model_validate(
                await owned(session, Subject, previous.resource_id, user_id)
            )
        if body.parent_id:
            await owned(session, Subject, body.parent_id, user_id)
        row = Subject(user_id=user_id, **body.model_dump())
        session.add(row)
        await session.flush()
        remember(session, user_id, operation, key, digest, row.id)
        return SubjectRead.model_validate(row)


async def update_subject(db, user_id, resource_id, body, version):
    async with db.transaction() as session:
        await lock_owner(session, user_id)
        row = await owned(session, Subject, resource_id, user_id, lock=True)
        check_version(row, version)
        values = body.model_dump(exclude_unset=True)
        if any(
            value is None and name not in ("parent_id", "description")
            for name, value in values.items()
        ):
            raise ServiceError("VALIDATION_ERROR", "学科字段不能设置为空")
        parent_id = values.get("parent_id")
        visited = {row.id}
        while parent_id:
            if parent_id in visited:
                raise ServiceError("INVALID_STATE", "学科层级不能形成循环")
            visited.add(parent_id)
            parent_id = (await owned(session, Subject, parent_id, user_id)).parent_id
        for name, value in values.items():
            setattr(row, name, value)
        row.version += 1
        return await refreshed(session, row, SubjectRead)


async def create_chapter(db, settings, user_id, body, key):
    operation = "chapters:create"
    async with db.transaction() as session:
        await lock_owner(session, user_id)
        previous, digest = await replay(
            session, user_id, operation, key, body.model_dump(mode="json"), settings.secret_key
        )
        if previous:
            return ChapterRead.model_validate(
                await owned(session, Chapter, previous.resource_id, user_id)
            )
        await owned(session, Subject, body.subject_id, user_id)
        values = body.model_dump()
        values["source_url"] = str(body.source_url) if body.source_url else None
        row = Chapter(user_id=user_id, **values)
        session.add(row)
        await session.flush()
        await queue_chapter(session, row)
        remember(session, user_id, operation, key, digest, row.id)
        return await refreshed(session, row, ChapterRead)


async def update_chapter(db, user_id, chapter_id, body, version):
    async with db.transaction() as session:
        await lock_owner(session, user_id)
        row = await owned(session, Chapter, chapter_id, user_id, lock=True)
        check_version(row, version)
        for name, value in body.model_dump(exclude_unset=True).items():
            if value is None:
                raise ServiceError("VALIDATION_ERROR", "章节字段不能设置为空")
            setattr(row, name, value)
        if row.status != "completed":
            row.completed_at = None
        await queue_chapter(session, row)
        row.version += 1
        return await refreshed(session, row, ChapterRead)


async def complete_chapter(db, settings, user_id, chapter_id, key):
    operation = f"chapters:{chapter_id}:complete"
    async with db.transaction() as session:
        await lock_owner(session, user_id)
        row = await owned(session, Chapter, chapter_id, user_id, lock=True)
        previous, digest = await replay(session, user_id, operation, key, {}, settings.secret_key)
        if not previous:
            if row.status != "completed":
                row.status = "completed"
                row.version += 1
            await queue_chapter(session, row)
            remember(session, user_id, operation, key, digest, row.id)
        return await refreshed(session, row, ChapterRead)


async def add_study_session(db, settings, user_id, chapter_id, body, key):
    operation = f"chapters:{chapter_id}:study"
    async with db.transaction() as session:
        await lock_owner(session, user_id)
        chapter = await owned(session, Chapter, chapter_id, user_id, lock=True)
        previous, digest = await replay(
            session, user_id, operation, key, body.model_dump(mode="json"), settings.secret_key
        )
        if previous:
            return StudySessionRead.model_validate(
                await owned(session, StudySession, previous.resource_id, user_id)
            )
        if body.ended_at > utcnow() + timedelta(minutes=5):
            raise ServiceError("VALIDATION_ERROR", "学习记录结束时间超过当前时间")
        row = StudySession(
            user_id=user_id,
            chapter_id=chapter_id,
            **body.model_dump(),
            duration_seconds=int((body.ended_at - body.started_at).total_seconds()),
        )
        session.add(row)
        if chapter.status == "not_started":
            chapter.status = "in_progress"
            chapter.version += 1
        await session.flush()
        remember(session, user_id, operation, key, digest, row.id)
        return StudySessionRead.model_validate(row)


async def initialize_schedule(session, settings, point):
    chapter = await chapter_ready(session, point)
    existing = await session.scalar(
        select(ScheduleState).where(ScheduleState.knowledge_point_id == point.id)
    )
    if existing is None:
        preferences = await session.scalar(
            select(WorkspaceProfile.review_preferences).where(WorkspaceProfile.user_id == point.user_id)
        ) or {}
        strategy_row = await session.scalar(
            select(SubjectStrategy).where(
                SubjectStrategy.subject_id == point.subject_id, SubjectStrategy.is_active.is_(True)
            )
        )
        overrides = dict(strategy_row.scheduler_overrides) if strategy_row else {}
        strategy = overrides.pop("strategy", preferences.get("strategy", settings.scheduler_strategy))
        parameters = (
            {"intervals_days": preferences.get("intervals_days", list(settings.ebbinghaus_intervals_days))}
            if strategy == "ebbinghaus"
            else {"target_retention": settings.fsrs_target_retention}
        )
        parameters.update(overrides)
        anchor = chapter.completed_at if chapter and chapter.completed_at else utcnow()
        state = memory.initial_state(strategy, anchor, parameters, card_id=point.id.int)
        session.add(
            ScheduleState(user_id=point.user_id, knowledge_point_id=point.id, **asdict(state))
        )


async def create_knowledge(db, settings, user_id, body, key):
    operation = "knowledge:create"
    async with db.transaction() as session:
        await lock_owner(session, user_id)
        previous, digest = await replay(
            session, user_id, operation, key, body.model_dump(mode="json"), settings.secret_key
        )
        if previous:
            return await knowledge_read(
                session, await owned(session, KnowledgePoint, previous.resource_id, user_id)
            )
        await owned(session, Subject, body.subject_id, user_id)
        if body.chapter_id:
            chapter = await owned(session, Chapter, body.chapter_id, user_id)
            if chapter.subject_id != body.subject_id:
                raise ServiceError("VALIDATION_ERROR", "章节与知识点的学科不一致")
        row = KnowledgePoint(
            user_id=user_id,
            manual_revision=True,
            canonical_hash=knowledge_hash(body.subject_id, body.title, body.body),
            **body.model_dump(),
        )
        if row.status not in ("draft", "active"):
            raise ServiceError("INVALID_STATE", "新知识点应为草稿或激活状态")
        session.add(row)
        await session.flush()
        if row.status == "active":
            await initialize_schedule(session, settings, row)
        remember(session, user_id, operation, key, digest, row.id)
        return await knowledge_read(session, row)


async def knowledge_read(session, row):
    value = KnowledgePointRead.model_validate(row).model_dump(mode="json")
    value["chapter_id"] = row.chapter_id
    chapter = await owned(session, Chapter, row.chapter_id, row.user_id) if row.chapter_id else None
    value["source_url"] = chapter.source_url if chapter else None
    return value


async def get_knowledge(db, user_id, resource_id):
    async with db.transaction() as session:
        return await knowledge_read(
            session, await owned(session, KnowledgePoint, resource_id, user_id)
        )


async def list_knowledge(db, user_id, *, limit=20, cursor=None, filters=()):
    async with db.transaction() as session:
        rows, cursor, more = await page(
            session,
            select(KnowledgePoint).where(KnowledgePoint.user_id == user_id, *filters),
            KnowledgePoint,
            limit,
            cursor,
        )
        return {
            "items": [await knowledge_read(session, row) for row in rows],
            "next_cursor": cursor,
            "has_more": more,
        }


async def activate_knowledge(db, settings, user_id, resource_id, key, *, archive=False):
    operation = f"knowledge:{resource_id}:{'archive' if archive else 'activate'}"
    async with db.transaction() as session:
        await lock_owner(session, user_id)
        row = await owned(session, KnowledgePoint, resource_id, user_id, lock=True)
        previous, digest = await replay(session, user_id, operation, key, {}, settings.secret_key)
        if not previous:
            if row.status == "merged":
                raise ServiceError("INVALID_STATE", "已合并的知识点不能激活")
            if archive:
                row.status = "archived"
                row.archived_at = utcnow()
                tasks = await session.scalars(
                    select(DailyReviewTask).where(
                        DailyReviewTask.knowledge_point_id == row.id,
                        DailyReviewTask.status.in_(["pending", "in_progress"]),
                    )
                )
                for task in tasks:
                    task.status = "cancelled"
                    task.version += 1
            else:
                await initialize_schedule(session, settings, row)
                row.status = "active"
                row.archived_at = None
            row.version += 1
            remember(session, user_id, operation, key, digest, row.id)
            await session.flush()
            await session.refresh(row)
        return await knowledge_read(session, row)


async def create_review_item(db, settings, user_id, point_id, body, key):
    operation = f"knowledge:{point_id}:review-item"
    async with db.transaction() as session:
        await lock_owner(session, user_id)
        point = await owned(session, KnowledgePoint, point_id, user_id, lock=True)
        previous, digest = await replay(
            session, user_id, operation, key, body.model_dump(mode="json"), settings.secret_key
        )
        if previous:
            return ReviewItemRead.model_validate(
                await owned(session, ReviewItem, previous.resource_id, user_id)
            )
        await chapter_ready(session, point)
        current = await session.scalar(
            select(ReviewItem).where(
                ReviewItem.knowledge_point_id == point_id, ReviewItem.is_current
            )
        )
        version = (
            await session.scalar(
                select(func.max(ReviewItem.item_version)).where(
                    ReviewItem.knowledge_point_id == point_id
                )
            )
            or 0
        )
        if current:
            current.is_current = False
            await session.flush()
        row = ReviewItem(
            user_id=user_id,
            knowledge_point_id=point_id,
            manual_revision=True,
            item_version=version + 1,
            **body.model_dump(),
        )
        session.add(row)
        await session.flush()
        remember(session, user_id, operation, key, digest, row.id)
        return ReviewItemRead.model_validate(row)


async def batch_read(session, batch):
    await session.flush()
    await session.refresh(batch)
    rows = await session.scalars(
        select(DailyReviewTask)
        .where(DailyReviewTask.batch_id == batch.id)
        .order_by(DailyReviewTask.position)
    )
    return DailyBatchRead.model_validate(batch).model_copy(
        update={"tasks": [DailyTaskRead.model_validate(row) for row in rows]}
    )


async def generate_batch(db, settings, user_id, body, key, *, refresh=False):
    operation = "review-batch:generate"
    now = utcnow()
    try:
        ZoneInfo(body.timezone)
    except (ValueError, KeyError):
        raise ServiceError("VALIDATION_ERROR", "未知时区") from None
    async with db.transaction() as session:
        user = await lock_owner(session, user_id)
        if body.local_date != now.astimezone(ZoneInfo(user.timezone)).date():
            raise ServiceError("INVALID_STATE", "每日任务应按账号时区的当前日期生成")
        previous, digest = await replay(
            session, user_id, operation, key, body.model_dump(mode="json"), settings.secret_key
        )
        if previous and not refresh:
            return await batch_read(
                session, await owned(session, DailyReviewBatch, previous.resource_id, user_id)
            )
        if body.subject_id:
            await owned(session, Subject, body.subject_id, user_id)
        batch = await session.scalar(
            select(DailyReviewBatch).where(
                DailyReviewBatch.user_id == user_id,
                DailyReviewBatch.local_date == body.local_date,
                DailyReviewBatch.subject_id == body.subject_id,
            )
        )
        if batch is None:
            batch = DailyReviewBatch(
                user_id=user_id,
                local_date=body.local_date,
                timezone=user.timezone,
                subject_id=body.subject_id,
                daily_limit=body.daily_limit,
                status="ready",
                idempotency_key=key,
            )
            session.add(batch)
            await session.flush()
        existing_ids = list(
            (
                await session.scalars(
                    select(DailyReviewTask.knowledge_point_id).where(
                        DailyReviewTask.batch_id == batch.id
                    )
                )
            ).all()
        )
        overall_limit = settings.daily_review_limit
        overall_batch_limit = batch.daily_limit if body.subject_id is None else await session.scalar(
            select(DailyReviewBatch.daily_limit).where(
                DailyReviewBatch.user_id == user_id,
                DailyReviewBatch.local_date == body.local_date,
                DailyReviewBatch.subject_id.is_(None),
            )
        )
        if overall_batch_limit is not None:
            overall_limit = min(overall_limit, overall_batch_limit)
        assigned = assigned_today(user_id, body.local_date)
        total_assigned = await session.scalar(select(func.count()).select_from(assigned.subquery()))
        remaining = min(batch.daily_limit - len(existing_ids), overall_limit - total_assigned)
        if remaining <= 0 or batch.status == "cancelled":
            if not previous:
                remember(session, user_id, operation, key, digest, batch.id)
            return await batch_read(session, batch)
        query = (
            select(KnowledgePoint, ScheduleState, ReviewItem.id)
            .join(ScheduleState, ScheduleState.knowledge_point_id == KnowledgePoint.id)
            .outerjoin(
                ReviewItem,
                (ReviewItem.knowledge_point_id == KnowledgePoint.id) & ReviewItem.is_current,
            )
            .where(
                *eligible_due_points(user_id, now),
                KnowledgePoint.id.not_in(assigned),
            )
        )
        if body.subject_id:
            query = query.where(KnowledgePoint.subject_id == body.subject_id)
        candidates = [
            daily_tasks.DueCandidate(
                str(point.id),
                schedule.due_at,
                str(point.subject_id),
                point.difficulty,
                schedule.lapse_count,
                float(schedule.retrievability) if schedule.retrievability is not None else None,
                str(item_id) if item_id else None,
            )
            for point, schedule, item_id in (await session.execute(query)).all()
        ]
        plan = daily_tasks.generate_daily_batch(
            user_id=str(user_id),
            local_date=body.local_date,
            timezone_name=user.timezone,
            daily_limit=remaining,
            candidates=candidates,
            as_of=now,
            subject_id=str(body.subject_id) if body.subject_id else None,
        )
        for task in plan.tasks:
            session.add(
                DailyReviewTask(
                    user_id=user_id,
                    batch_id=batch.id,
                    knowledge_point_id=UUID(task.knowledge_point_id),
                    review_item_id=UUID(task.review_item_id) if task.review_item_id else None,
                    scheduled_due_at=task.scheduled_due_at,
                    priority=task.priority,
                    position=task.position + len(existing_ids),
                )
            )
        await session.flush()
        if plan.tasks:
            batch.status = "ready"
            batch.version += 1
        if not previous:
            remember(session, user_id, operation, key, digest, batch.id)
        return await batch_read(session, batch)


async def get_batch(db, user_id, resource_id):
    async with db.transaction() as session:
        return await batch_read(
            session, await owned(session, DailyReviewBatch, resource_id, user_id)
        )


async def task_action(db, settings, user_id, resource_id, key, action, reason=None, *, days=None):
    operation = f"task:{resource_id}:{action}"
    payload = {"reason": reason} if action == "skip" else {"days": days} if action == "defer" else {}
    async with db.transaction() as session:
        user = await lock_owner(session, user_id)
        row = await owned(session, DailyReviewTask, resource_id, user_id, lock=True)
        previous, digest = await replay(
            session,
            user_id,
            operation,
            key,
            payload,
            settings.secret_key,
        )
        if previous:
            return DailyTaskRead.model_validate(row)
        if row.status not in ("pending", "in_progress"):
            raise ServiceError("INVALID_STATE", "当前任务状态不支持此操作")
        if action == "defer":
            schedule = await session.scalar(
                select(ScheduleState).where(
                    ScheduleState.knowledge_point_id == row.knowledge_point_id,
                    ScheduleState.user_id == user_id,
                ).with_for_update()
            )
            if schedule is None:
                raise ServiceError("INVALID_STATE", "知识点没有复习计划")
            plan_date = utcnow().astimezone(ZoneInfo(user.timezone)).date() + timedelta(days=days)
            due = datetime.combine(plan_date, time.min, ZoneInfo(user.timezone))
            schedule.due_at = max(schedule.due_at, due)
            schedule.state_version += 1
            row.skip_reason = "deferred:" + schedule.due_at.isoformat()
        if action == "skip":
            row.skip_reason = reason
        if action == "start" and row.started_at is None:
            row.started_at = utcnow()
        row.status = "in_progress" if action == "start" else "skipped"
        row.version += 1
        remember(session, user_id, operation, key, digest, row.id)
        await session.flush()
        if action in {"skip", "defer"}:
            pending = await session.scalar(
                select(func.count())
                .select_from(DailyReviewTask)
                .where(
                    DailyReviewTask.batch_id == row.batch_id,
                    DailyReviewTask.status.in_(["pending", "in_progress"]),
                )
            )
            if pending == 0:
                batch = await session.get(DailyReviewBatch, row.batch_id)
                batch.status = "completed"
                batch.version += 1
        return await refreshed(session, row, DailyTaskRead)


async def task_content(db, user_id, resource_id):
    async with db.transaction() as session:
        task = await owned(session, DailyReviewTask, resource_id, user_id)
        point = await owned(session, KnowledgePoint, task.knowledge_point_id, user_id)
        item = (
            await owned(session, ReviewItem, task.review_item_id, user_id)
            if task.review_item_id
            else None
        )
        state = await session.scalar(
            select(ScheduleState).where(ScheduleState.knowledge_point_id == point.id)
        )
        return {
            "task": DailyTaskRead.model_validate(task),
            "knowledge": await knowledge_read(session, point),
            "review_item": ReviewItemRead.model_validate(item) if item else None,
            "schedule": ScheduleStateRead.model_validate(state) if state else None,
        }


async def update_knowledge(db, settings, user_id, resource_id, body, version):
    async with db.transaction() as session:
        await lock_owner(session, user_id)
        row = await owned(session, KnowledgePoint, resource_id, user_id, lock=True)
        check_version(row, version)
        for name, value in body.model_dump(exclude_unset=True).items():
            if value is None:
                raise ServiceError("VALIDATION_ERROR", "知识字段不能设置为空")
            setattr(row, name, value)
        canonical = json.dumps(
            [str(row.subject_id), row.title.strip(), row.body.strip()], ensure_ascii=False
        )
        row.canonical_hash = hashlib.sha256(canonical.encode()).hexdigest()
        row.manual_revision = True
        row.version += 1
        await session.flush()
        await session.refresh(row)
        return await knowledge_read(session, row)


async def get_schedule(db, user_id, point_id):
    async with db.transaction() as session:
        await owned(session, KnowledgePoint, point_id, user_id)
        row = await session.scalar(
            select(ScheduleState).where(
                ScheduleState.user_id == user_id, ScheduleState.knowledge_point_id == point_id
            )
        )
        if row is None:
            raise ServiceError("RESOURCE_NOT_FOUND", "知识点尚未激活调度")
        return ScheduleStateRead.model_validate(row)


async def list_batches(db, user_id, limit, cursor, local_date, status, subject_id):
    async with db.transaction() as session:
        query = select(DailyReviewBatch).where(DailyReviewBatch.user_id == user_id)
        if local_date:
            query = query.where(DailyReviewBatch.local_date == local_date)
        if status:
            query = query.where(DailyReviewBatch.status == status)
        if subject_id:
            query = query.where(DailyReviewBatch.subject_id == subject_id)
        rows, cursor, more = await page(session, query, DailyReviewBatch, limit, cursor)
        return {
            "items": [await batch_read(session, row) for row in rows],
            "next_cursor": cursor,
            "has_more": more,
        }


async def display_records(session, user_id, rows, schema):
    ids = [row.knowledge_point_id for row in rows]
    points = {
        point.id: point for point in (await session.scalars(
            select(KnowledgePoint).where(KnowledgePoint.user_id == user_id, KnowledgePoint.id.in_(ids))
        )).all()
    } if ids else {}
    result = []
    for row in rows:
        item = schema.model_validate(row).model_dump()
        point = points.get(row.knowledge_point_id)
        item.update(knowledge_title=point.title if point else "", subject_id=point.subject_id if point else None)
        result.append(item)
    return result


async def list_tasks(db, user_id, limit, cursor, status, local_date, subject_id, overdue, q=None):
    query = (
        select(DailyReviewTask)
        .join(DailyReviewBatch, DailyReviewBatch.id == DailyReviewTask.batch_id)
        .join(KnowledgePoint, KnowledgePoint.id == DailyReviewTask.knowledge_point_id)
        .where(DailyReviewTask.user_id == user_id)
    )
    if status == "open":
        query = query.where(DailyReviewTask.status.in_(OPEN_TASK_STATUSES))
    elif status:
        query = query.where(DailyReviewTask.status == status)
    if local_date:
        query = query.where(
            or_(
                DailyReviewBatch.local_date == local_date,
                (DailyReviewBatch.local_date < local_date)
                & DailyReviewTask.status.in_(["pending", "in_progress"]),
            )
        )
    if subject_id:
        query = query.where(KnowledgePoint.subject_id == subject_id)
    if q:
        query = query.where(KnowledgePoint.title.ilike(f"%{q}%"))
    if overdue is not None:
        condition = (DailyReviewTask.scheduled_due_at < utcnow()) & DailyReviewTask.status.in_(
            ["pending", "in_progress"]
        )
        query = query.where(condition if overdue else ~condition)
    async with db.transaction() as session:
        rows, cursor, more = await page(session, query, DailyReviewTask, limit, cursor)
        return {
            "items": await display_records(session, user_id, rows, DailyTaskRead),
            "next_cursor": cursor,
            "has_more": more,
        }


def validate_time_range(start, end):
    if any(value is not None and value.utcoffset() is None for value in (start, end)):
        raise ServiceError("VALIDATION_ERROR", "筛选时间需要包含时区")
    if start and end and start > end:
        raise ServiceError("VALIDATION_ERROR", "开始时间应早于结束时间")


async def list_history(db, user_id, limit, cursor, point_id, subject_id, start, end, rating, q=None):
    validate_time_range(start, end)
    query = (
        select(ReviewHistory)
        .join(KnowledgePoint, KnowledgePoint.id == ReviewHistory.knowledge_point_id)
        .where(ReviewHistory.user_id == user_id)
    )
    if point_id:
        query = query.where(ReviewHistory.knowledge_point_id == point_id)
    if q:
        query = query.where(KnowledgePoint.title.ilike(f"%{q}%"))
    if subject_id:
        query = query.where(KnowledgePoint.subject_id == subject_id)
    if start:
        query = query.where(ReviewHistory.reviewed_at >= start)
    if end:
        query = query.where(ReviewHistory.reviewed_at <= end)
    if rating:
        query = query.where(ReviewHistory.rating == rating)
    from app.contracts.models import ReviewHistoryRead

    async with db.transaction() as session:
        rows, cursor, more = await page(session, query, ReviewHistory, limit, cursor)
        return {
            "items": await display_records(session, user_id, rows, ReviewHistoryRead),
            "next_cursor": cursor,
            "has_more": more,
        }


async def statistics(db, user_id, from_date, to_date, subject_id=None):
    if from_date > to_date or (to_date - from_date).days + 1 > 366:
        raise ServiceError("VALIDATION_ERROR", "统计范围应为连续且不超过366天")
    async with db.transaction() as session:
        batches = select(DailyReviewBatch.id).where(
            DailyReviewBatch.user_id == user_id,
            DailyReviewBatch.local_date.between(from_date, to_date),
        )
        query = (
            select(func.count(), func.count().filter(DailyReviewTask.status == "completed"))
            .select_from(DailyReviewTask)
            .join(KnowledgePoint, KnowledgePoint.id == DailyReviewTask.knowledge_point_id)
            .where(DailyReviewTask.user_id == user_id, DailyReviewTask.batch_id.in_(batches))
        )
        if subject_id:
            query = query.where(KnowledgePoint.subject_id == subject_id)
        total, done = (await session.execute(query)).one()
        user = await session.get(User, user_id)
        zone = ZoneInfo(user.timezone)
        start = datetime.combine(from_date, time.min, zone)
        end = datetime.combine(to_date + timedelta(days=1), time.min, zone)
        day = func.date(func.timezone(user.timezone, ReviewHistory.reviewed_at))
        history_query = (
            select(
                day, func.count(), func.count().filter(ReviewHistory.rating.in_(["good", "easy"]))
            )
            .select_from(ReviewHistory)
            .join(KnowledgePoint, KnowledgePoint.id == ReviewHistory.knowledge_point_id)
            .where(
                ReviewHistory.user_id == user_id,
                ReviewHistory.reviewed_at >= start,
                ReviewHistory.reviewed_at < end,
            )
        )
        if subject_id:
            history_query = history_query.where(KnowledgePoint.subject_id == subject_id)
        rows = (await session.execute(history_query.group_by(day).order_by(day))).all()
        return {
            "from_date": from_date,
            "to_date": to_date,
            "total_tasks": total,
            "completed_tasks": done,
            "completion_rate": done / total if total else 0,
            "heatmap": [{"date": date, "count": count} for date, count, recalled in rows],
            "retention_trend": [
                {"date": date, "value": recalled / count} for date, count, recalled in rows
            ],
        }


async def switch_schedule(db, user_id, point_id, body, version):
    async with db.transaction() as session:
        await lock_owner(session, user_id)
        point = await owned(session, KnowledgePoint, point_id, user_id, lock=True)
        await chapter_ready(session, point)
        row = await session.scalar(
            select(ScheduleState)
            .where(ScheduleState.knowledge_point_id == point.id)
            .with_for_update()
        )
        if row is None:
            raise ServiceError("RESOURCE_NOT_FOUND", "知识点尚未激活")
        if row.state_version != version:
            raise ServiceError("VERSION_CONFLICT", "调度版本已更新")
        state = scheduling.from_mapping(
            {name: getattr(row, name) for name in scheduling.ScheduleState.__dataclass_fields__}
        )
        try:
            updated = memory.switch(
                state, body.strategy.value, utcnow(), body.parameters, card_id=point.id.int
            )
        except (ValueError, TypeError, OverflowError):
            raise ServiceError("VALIDATION_ERROR", "记忆策略参数无效") from None
        for name, value in asdict(updated).items():
            setattr(row, name, value)
        row.state_version += 1
        return await refreshed(session, row, ScheduleStateRead)
