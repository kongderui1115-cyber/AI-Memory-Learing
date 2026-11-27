"""Atomic, user-scoped review completion on PostgreSQL."""

from dataclasses import fields
from uuid import UUID
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.contracts.models import ReviewCompleteRequest
from app.database import Database
from app.domain import memory, scheduling
from app.models import (
    DailyReviewBatch,
    DailyReviewTask,
    KnowledgePoint,
    ReviewHistory,
    ScheduleState,
    User,
)


class ReviewError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


async def complete_review(
    database: Database,
    user_id: UUID,
    task_id: UUID,
    request: ReviewCompleteRequest,
    idempotency_key: str,
):
    if not idempotency_key or len(idempotency_key) > 128:
        raise ReviewError("VALIDATION_ERROR")
    if request.reviewed_at > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise ReviewError("VALIDATION_ERROR")
    if request.reviewed_at.utcoffset() is None:
        raise ReviewError("VALIDATION_ERROR")
    async with database.transaction() as session:
        # Serialize a user's completions, including competing idempotency keys.
        user = await session.scalar(select(User).where(User.id == user_id).with_for_update())
        if user is None or not user.is_active:
            raise ReviewError("AUTH_INVALID")
        history = await session.scalar(
            select(ReviewHistory).where(
                ReviewHistory.user_id == user_id, ReviewHistory.idempotency_key == idempotency_key
            )
        )
        if history is not None:
            matches = history.task_id == task_id and all(
                getattr(history, name) == getattr(request, name)
                for name in (
                    "rating",
                    "duration_seconds",
                    "answer_self_assessment",
                    "notes",
                    "reviewed_at",
                )
            )
            if not matches:
                raise ReviewError("IDEMPOTENCY_CONFLICT")
            return history
        task = await session.scalar(
            select(DailyReviewTask)
            .where(DailyReviewTask.id == task_id, DailyReviewTask.user_id == user_id)
            .with_for_update()
        )
        if task is None:
            raise ReviewError("RESOURCE_NOT_FOUND")
        point = await session.get(KnowledgePoint, task.knowledge_point_id)
        if point.status != "active":
            raise ReviewError("INVALID_STATE")
        if task.status == "completed":
            raise ReviewError("TASK_ALREADY_COMPLETED")
        if task.status not in ("pending", "in_progress"):
            raise ReviewError("INVALID_STATE")
        schedule = await session.scalar(
            select(ScheduleState)
            .where(
                ScheduleState.knowledge_point_id == task.knowledge_point_id,
                ScheduleState.user_id == user_id,
            )
            .with_for_update()
        )
        if schedule is None:
            raise ReviewError("INVALID_STATE")
        state = scheduling.from_mapping(
            {
                field.name: getattr(schedule, field.name)
                for field in fields(scheduling.ScheduleState)
            }
        )
        if state.last_reviewed_at and request.reviewed_at < state.last_reviewed_at:
            raise ReviewError("INVALID_STATE")
        updated = memory.review(state, request.rating.value, request.reviewed_at)
        history = ReviewHistory(
            user_id=user_id,
            task_id=task.id,
            knowledge_point_id=task.knowledge_point_id,
            review_item_id=task.review_item_id,
            strategy=state.strategy,
            **request.model_dump(),
            previous_schedule=scheduling.to_dict(state),
            result_schedule=scheduling.to_dict(updated),
            idempotency_key=idempotency_key,
        )
        session.add(history)
        for field in fields(updated):
            setattr(schedule, field.name, getattr(updated, field.name))
        schedule.state_version += 1
        task.status = "completed"
        task.completed_at = request.reviewed_at
        task.version += 1
        await session.flush()
        from sqlalchemy import func

        unfinished = await session.scalar(
            select(func.count())
            .select_from(DailyReviewTask)
            .where(
                DailyReviewTask.batch_id == task.batch_id,
                DailyReviewTask.status.in_(["pending", "in_progress"]),
            )
        )
        if unfinished == 0:
            batch = await session.get(DailyReviewBatch, task.batch_id)
            batch.status = "completed"
            batch.version += 1
        return history
