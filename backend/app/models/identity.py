"""身份与学科模型（DATABASE_SCHEMA.md §2「身份与学科」）。"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import CheckConstraint, Boolean, ForeignKey, Index, String, Text, UniqueConstraint, Uuid, text
from sqlalchemy.dialects.postgresql import CITEXT, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import (
    Base, JSONB_ARRAY_DEFAULT, JSONB_OBJECT_DEFAULT, TimestampMixin,
    UserFkMixin, UUIDPkMixin, VersionMixin,
)


class User(UUIDPkMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(CITEXT(), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("'Asia/Shanghai'"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    role: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'user'"))

    __table_args__ = (Index("ix_users_is_active", "is_active"), CheckConstraint("role IN ('user','admin')", name="user_role"))


class Subject(UUIDPkMixin, UserFkMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "subjects"

    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=True,
    )
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    language_code: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'zh-CN'"))
    tags: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSONB_ARRAY_DEFAULT,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    __table_args__ = (
        UniqueConstraint("user_id", "slug", name="uq_subjects_user_id_slug"),
        Index("ix_subjects_user_id_parent_id", "user_id", "parent_id"),
        Index("ix_subjects_tags_gin", "tags", postgresql_using="gin"),
    )


class SubjectStrategy(UUIDPkMixin, UserFkMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "subject_strategies"

    subject_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False,
    )
    extraction_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    question_type_preferences: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSONB_ARRAY_DEFAULT,
    )
    glossary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=JSONB_OBJECT_DEFAULT,
    )
    scheduler_overrides: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=JSONB_OBJECT_DEFAULT,
    )
    notification_template_overrides: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=JSONB_OBJECT_DEFAULT,
    )
    prompt_version: Mapped[str] = mapped_column(String(40), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    __table_args__ = (
        # 每个学科仅一条 active 策略（部分唯一索引）
        Index(
            "uq_subject_strategies_active_subject", "subject_id",
            unique=True, postgresql_where=text("is_active"),
        ),
        Index("ix_subject_strategies_user_id_subject_id", "user_id", "subject_id"),
    )


__all__ = ["User", "Subject", "SubjectStrategy"]
