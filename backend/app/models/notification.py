"""通知模型（DATABASE_SCHEMA.md §2「通知」）。"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer,
    String, Text, UniqueConstraint, Uuid, text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import (
    Base, JSONB_ARRAY_DEFAULT, JSONB_OBJECT_DEFAULT, TimestampMixin,
    UserFkMixin, UUIDPkMixin, VersionMixin,
)

_CHANNEL_TYPES = (
    "'wecom_app','wechat_official_account','third_party_push','wecom_webhook',"
    "'dingtalk_webhook','dingtalk_app','smtp'"
)


class NotificationChannelConfig(UUIDPkMixin, UserFkMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "notification_channel_configs"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    channel_type: Mapped[str] = mapped_column(String(40), nullable=False)
    credential_ref: Mapped[str] = mapped_column(String(160), nullable=False)
    settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=JSONB_OBJECT_DEFAULT,
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    __table_args__ = (
        CheckConstraint(f"channel_type IN ({_CHANNEL_TYPES})", name="ck_channel_configs_channel_type"),
        UniqueConstraint("user_id", "name", name="uq_channel_configs_user_id_name"),
        Index(
            "uq_channel_configs_default", "user_id",
            unique=True, postgresql_where=text("is_default"),
        ),
        Index("ix_channel_configs_user_type_enabled", "user_id", "channel_type", "is_enabled"),
    )


class NotificationTemplate(UUIDPkMixin, UserFkMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "notification_templates"

    subject_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=True,
    )
    channel_type: Mapped[str] = mapped_column(String(40), nullable=False)
    template_key: Mapped[str] = mapped_column(String(80), nullable=False)
    title_template: Mapped[str] = mapped_column(Text, nullable=False)
    body_template: Mapped[str] = mapped_column(Text, nullable=False)
    schema_variables: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSONB_ARRAY_DEFAULT,
    )
    max_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    __table_args__ = (
        CheckConstraint(f"channel_type IN ({_CHANNEL_TYPES})", name="ck_templates_channel_type"),
        UniqueConstraint(
            "user_id", "subject_id", "channel_type", "template_key", "version",
            name="uq_templates_user_subject_type_key_version",
        ),
        Index(
            "ix_templates_active_lookup", "user_id", "channel_type", "template_key",
            postgresql_where=text("is_active"),
        ),
    )


class NotificationJob(UUIDPkMixin, UserFkMixin, TimestampMixin, Base):
    __tablename__ = "notification_jobs"

    task_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("daily_review_tasks.id", ondelete="RESTRICT"), nullable=True,
    )
    channel_config_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("notification_channel_configs.id", ondelete="RESTRICT"), nullable=False,
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("notification_templates.id", ondelete="RESTRICT"), nullable=False,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'pending'"))
    purpose: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'review'"))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    rendered_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    rendered_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','processing','sent','failed','cancelled')",
            name="ck_notification_jobs_status",
        ),
        UniqueConstraint("user_id", "idempotency_key", name="uq_notification_jobs_user_id_idempotency_key"),
        Index("ix_notification_jobs_status_next_attempt", "status", "next_attempt_at"),
        Index("ix_notification_jobs_task_id", "task_id"),
    )


class NotificationDelivery(UUIDPkMixin, UserFkMixin, Base):
    __tablename__ = "notification_deliveries"

    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("notification_jobs.id", ondelete="RESTRICT"), nullable=False,
    )
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    request_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=JSONB_OBJECT_DEFAULT,
    )
    response_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=JSONB_OBJECT_DEFAULT,
    )
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"),
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('sending','sent','failed')", name="ck_notification_deliveries_status",
        ),
        UniqueConstraint("job_id", "attempt_no", name="uq_notification_deliveries_job_attempt"),
        Index("ix_notification_deliveries_user_attempted", "user_id", text("attempted_at DESC")),
    )


__all__ = [
    "NotificationChannelConfig", "NotificationTemplate", "NotificationJob", "NotificationDelivery",
]
