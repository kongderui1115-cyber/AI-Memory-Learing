"""调度、任务与历史模型（DATABASE_SCHEMA.md §2「调度、任务与历史」）。"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric,
    String, Text, UniqueConstraint, Uuid, text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import (
    Base, CreatedAtMixin, JSONB_OBJECT_DEFAULT, TimestampMixin,
    UserFkMixin, UUIDPkMixin, VersionMixin,
)


class ScheduleState(UUIDPkMixin, UserFkMixin, TimestampMixin, Base):
    __tablename__ = "schedule_states"

    @property
    def version(self):
        return self.state_version

    knowledge_point_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("knowledge_points.id", ondelete="RESTRICT"),
        nullable=False, unique=True,
    )
    strategy: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'ebbinghaus'"))
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    lapse_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    interval_index: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    interval_days: Mapped[float | None] = mapped_column(Numeric(10, 3), nullable=True)
    stability: Mapped[float | None] = mapped_column(Numeric(12, 6), nullable=True)
    difficulty: Mapped[float | None] = mapped_column(Numeric(8, 6), nullable=True)
    retrievability: Mapped[float | None] = mapped_column(Numeric(8, 6), nullable=True)
    target_retention: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    algorithm_version: Mapped[str] = mapped_column(String(40), nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=JSONB_OBJECT_DEFAULT,
    )
    last_calculation: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=JSONB_OBJECT_DEFAULT,
    )
    strategy_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"),
    )

    __table_args__ = (
        CheckConstraint("strategy IN ('ebbinghaus','fsrs')", name="ck_schedule_states_strategy"),
        Index("ix_schedule_states_user_due", "user_id", "due_at"),
        Index("ix_schedule_states_strategy_due", "strategy", "due_at"),
    )


class DailyReviewBatch(UUIDPkMixin, UserFkMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "daily_review_batches"

    local_date: Mapped[date] = mapped_column(Date, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    daily_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'pending'"))
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"),
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','ready','completed','cancelled')",
            name="ck_daily_review_batches_status",
        ),
        UniqueConstraint("user_id", "idempotency_key", name="uq_daily_review_batches_user_id_idempotency_key"),
        # NULLS NOT DISTINCT：subject_id 为 NULL（全部学科）时也参与唯一性
        Index(
            "uq_daily_review_batches_user_date_subject", "user_id", "local_date", "subject_id",
            unique=True, postgresql_nulls_not_distinct=True,
        ),
    )


class DailyReviewTask(UUIDPkMixin, UserFkMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "daily_review_tasks"

    skip_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    batch_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("daily_review_batches.id", ondelete="RESTRICT"), nullable=False,
    )
    knowledge_point_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("knowledge_points.id", ondelete="RESTRICT"), nullable=False,
    )
    review_item_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("review_items.id", ondelete="RESTRICT"), nullable=True,
    )
    scheduled_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'pending'"))
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','in_progress','completed','skipped','cancelled')",
            name="ck_daily_review_tasks_status",
        ),
        UniqueConstraint("batch_id", "knowledge_point_id", name="uq_daily_review_tasks_batch_kp"),
        Index("ix_daily_review_tasks_user_status_due", "user_id", "status", "scheduled_due_at"),
        Index("ix_daily_review_tasks_batch_position", "batch_id", "position"),
    )


class ReviewHistory(UUIDPkMixin, UserFkMixin, CreatedAtMixin, Base):
    __tablename__ = "review_history"

    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("daily_review_tasks.id", ondelete="RESTRICT"),
        nullable=False, unique=True,
    )
    knowledge_point_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("knowledge_points.id", ondelete="RESTRICT"), nullable=False,
    )
    review_item_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("review_items.id", ondelete="RESTRICT"), nullable=True,
    )
    strategy: Mapped[str] = mapped_column(String(20), nullable=False)
    rating: Mapped[str] = mapped_column(String(16), nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    answer_self_assessment: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    previous_schedule: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=JSONB_OBJECT_DEFAULT,
    )
    result_schedule: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=JSONB_OBJECT_DEFAULT,
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)

    __table_args__ = (
        CheckConstraint("strategy IN ('ebbinghaus','fsrs')", name="ck_review_history_strategy"),
        CheckConstraint("rating IN ('again','hard','good','easy')", name="ck_review_history_rating"),
        CheckConstraint("duration_seconds >= 0", name="ck_review_history_duration_seconds"),
        UniqueConstraint("user_id", "idempotency_key", name="uq_review_history_user_id_idempotency_key"),
        Index("ix_review_history_user_reviewed", "user_id", text("reviewed_at DESC")),
        Index("ix_review_history_kp_reviewed", "knowledge_point_id", text("reviewed_at DESC")),
    )


__all__ = ["ScheduleState", "DailyReviewBatch", "DailyReviewTask", "ReviewHistory"]
