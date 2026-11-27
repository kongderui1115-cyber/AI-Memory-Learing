"""Read-only review workload based on the same due rules as batch generation."""

from datetime import timedelta
from math import ceil
from zoneinfo import ZoneInfo

from sqlalchemy import exists, func, select

from app.models import (
    DailyReviewBatch,
    DailyReviewTask,
    KnowledgePoint,
    ReviewHistory,
    ScheduleState,
)
from app.services.common import utcnow

OPEN_TASK_STATUSES = ("pending", "in_progress")


def eligible_due_points(user_id, now):
    open_task = exists(
        select(DailyReviewTask.id).where(
            DailyReviewTask.user_id == user_id,
            DailyReviewTask.knowledge_point_id == KnowledgePoint.id,
            DailyReviewTask.status.in_(OPEN_TASK_STATUSES),
        )
    )
    return (
        KnowledgePoint.user_id == user_id,
        KnowledgePoint.status == "active",
        ScheduleState.user_id == user_id,
        ScheduleState.due_at <= now,
        ~open_task,
    )


def assigned_today(user_id, local_date):
    return (
        select(DailyReviewTask.knowledge_point_id)
        .join(DailyReviewBatch, DailyReviewBatch.id == DailyReviewTask.batch_id)
        .where(DailyReviewBatch.user_id == user_id, DailyReviewBatch.local_date == local_date)
    )


async def read(db, settings, user):
    now = utcnow()
    today = now.astimezone(ZoneInfo(user.timezone)).date()
    async with db.transaction() as session:
        batch = await session.scalar(
            select(DailyReviewBatch).where(
                DailyReviewBatch.user_id == user.id,
                DailyReviewBatch.local_date == today,
                DailyReviewBatch.subject_id.is_(None),
            )
        )
        daily_limit = min(batch.daily_limit, settings.daily_review_limit) if batch else settings.daily_review_limit
        queued = await session.scalar(
            select(func.count())
            .select_from(DailyReviewTask)
            .where(
                DailyReviewTask.user_id == user.id,
                DailyReviewTask.status.in_(OPEN_TASK_STATUSES),
            )
        )
        due = (
            select(KnowledgePoint.id)
            .join(ScheduleState, ScheduleState.knowledge_point_id == KnowledgePoint.id)
            .where(*eligible_due_points(user.id, now))
            .subquery()
        )
        used_points = assigned_today(user.id, today)
        used = await session.scalar(select(func.count()).select_from(used_points.subquery()))
        available, not_assigned_today = (
            await session.execute(
                select(func.count(), func.count().filter(due.c.id.not_in(used_points)))
            )
        ).one()
        can_enqueue = (
            0 if batch and batch.status == "cancelled"
            else min(max(0, daily_limit - used), not_assigned_today)
        )
        samples, typical = (
            await session.execute(
                select(
                    func.count(),
                    func.percentile_cont(0.5).within_group(ReviewHistory.duration_seconds),
                ).where(
                    ReviewHistory.user_id == user.id,
                    ReviewHistory.reviewed_at >= now - timedelta(days=30),
                    ReviewHistory.reviewed_at <= now,
                    ReviewHistory.duration_seconds.between(1, 3600),
                )
            )
        ).one()
        return {
            "local_date": today,
            "timezone": user.timezone,
            "queued": queued,
            "due_unqueued": available,
            "can_enqueue": can_enqueue,
            "daily_limit": daily_limit,
            "estimated_seconds": ceil(typical * queued) if samples >= 5 else None,
            "sample_size": samples,
            "automatic_processing_enabled": settings.background_tasks_enabled,
        }
