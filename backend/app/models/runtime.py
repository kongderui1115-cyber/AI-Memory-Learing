"""Persistent accounts, sessions, audit, chapters and study records."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, CreatedAtMixin, TimestampMixin, UserFkMixin, UUIDPkMixin, VersionMixin


class UserSession(UUIDPkMixin, UserFkMixin, Base):
    __tablename__ = "user_sessions"
    token_digest: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    logged_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip_address: Mapped[str] = mapped_column(String(64), nullable=False)
    user_agent: Mapped[str] = mapped_column(String(500), nullable=False)
    __table_args__ = (
        Index("ix_sessions_user_created", "user_id", "created_at"),
        Index(
            "ix_sessions_online",
            "last_seen_at",
            "expires_at",
            postgresql_where=text("logged_out_at IS NULL"),
        ),
        CheckConstraint("expires_at > created_at", name="session_expiry"),
    )


class LoginThrottle(Base):
    __tablename__ = "login_throttles"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    failures: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint("failures >= 0", name="throttle_failures"),)


class AuditEvent(UUIDPkMixin, CreatedAtMixin, Base):
    __tablename__ = "audit_events"
    actor_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"))
    target_user_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT")
    )
    actor_label: Mapped[str] = mapped_column(String(254), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'info'"))
    resource: Mapped[str] = mapped_column(String(300), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    ip_address: Mapped[str] = mapped_column(String(64), nullable=False)
    request_id: Mapped[UUID | None] = mapped_column(Uuid)
    __table_args__ = (
        Index("ix_audit_created", "created_at", "id"),
        Index("ix_audit_actor_created", "actor_id", "created_at"),
        CheckConstraint("severity IN ('info','warning','high')", name="audit_severity"),
    )


class IdempotencyRecord(UUIDPkMixin, UserFkMixin, CreatedAtMixin, Base):
    __tablename__ = "idempotency_records"
    operation: Mapped[str] = mapped_column(String(160), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    __table_args__ = (UniqueConstraint("user_id", "operation", "key", name="uq_idempotency_scope"),)


class Chapter(UUIDPkMixin, UserFkMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "chapters"
    subject_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'not_started'")
    )
    source_url: Mapped[str | None] = mapped_column(Text)
    external_page_id: Mapped[str | None] = mapped_column(String(128))
    notion_archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint(
            "status IN ('not_started','in_progress','completed')", name="chapter_status"
        ),
        UniqueConstraint("user_id", "external_page_id", name="uq_chapter_external_page"),
        Index("ix_chapters_user_subject_status", "user_id", "subject_id", "status"),
    )


class StudySession(UUIDPkMixin, UserFkMixin, CreatedAtMixin, Base):
    __tablename__ = "study_sessions"
    chapter_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("chapters.id", ondelete="RESTRICT"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    __table_args__ = (
        CheckConstraint(
            "ended_at >= started_at AND duration_seconds >= 0", name="study_session_time"
        ),
        Index("ix_study_user_chapter", "user_id", "chapter_id"),
    )


class ChapterJob(UUIDPkMixin, UserFkMixin, TimestampMixin, Base):
    __tablename__ = "chapter_jobs"
    chapter_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("chapters.id", ondelete="RESTRICT"), nullable=False
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'pending'")
    )
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    error_code: Mapped[str | None] = mapped_column(String(80))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    __table_args__ = (
        UniqueConstraint("chapter_id", "content_hash", name="uq_chapter_job_revision"),
        CheckConstraint(
            "status IN ('pending','running','blocked','succeeded','failed','cancelled')",
            name="chapter_job_status",
        ),
        Index("ix_chapter_jobs_retry", "status", "next_attempt_at"),
    )
