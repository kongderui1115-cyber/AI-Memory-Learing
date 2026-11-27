"""知识与生成内容模型（DATABASE_SCHEMA.md §2「知识与生成内容」）。"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CHAR, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer,
    SmallInteger, String, Text, UniqueConstraint, Uuid, text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import (
    Base, CreatedAtMixin, JSONB_ARRAY_DEFAULT, TimestampMixin,
    UserFkMixin, UUIDPkMixin, VersionMixin,
)


class KnowledgePoint(UUIDPkMixin, UserFkMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "knowledge_points"

    chapter_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("chapters.id", ondelete="RESTRICT"), nullable=True)
    subject_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False,
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    keywords: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSONB_ARRAY_DEFAULT,
    )
    tags: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=JSONB_ARRAY_DEFAULT,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'draft'"))
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("knowledge_points.id", ondelete="RESTRICT"), nullable=True,
    )
    canonical_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    manual_revision: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    source_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("difficulty BETWEEN 1 AND 5", name="ck_knowledge_points_difficulty"),
        CheckConstraint(
            "status IN ('draft','active','archived','merged')", name="ck_knowledge_points_status",
        ),
        # 非 merged 状态下 (user_id, canonical_hash) 唯一
        Index(
            "uq_knowledge_points_user_canonical_hash", "user_id", "canonical_hash",
            unique=True, postgresql_where=text("status <> 'merged'"),
        ),
        Index("ix_knowledge_points_user_subject_status", "user_id", "subject_id", "status"),
        Index("ix_knowledge_points_keywords_gin", "keywords", postgresql_using="gin"),
        Index("ix_knowledge_points_tags_gin", "tags", postgresql_using="gin"),
    )


class KnowledgePointSource(UUIDPkMixin, UserFkMixin, CreatedAtMixin, Base):
    __tablename__ = "knowledge_point_sources"

    knowledge_point_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("knowledge_points.id", ondelete="CASCADE"), nullable=False,
    )
    raw_note_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("raw_notes.id", ondelete="RESTRICT"), nullable=False,
    )
    source_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "knowledge_point_id", "raw_note_id",
            name="uq_knowledge_point_sources_kp_raw_note",
        ),
        Index("ix_knowledge_point_sources_raw_note_id", "raw_note_id"),
    )


class ReviewItem(UUIDPkMixin, UserFkMixin, TimestampMixin, Base):
    __tablename__ = "review_items"

    @property
    def version(self):
        return self.item_version

    knowledge_point_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("knowledge_points.id", ondelete="CASCADE"), nullable=False,
    )
    question_type: Mapped[str] = mapped_column(String(24), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    summary: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    options: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    item_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    manual_revision: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    provider_config_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("ai_provider_configs.id", ondelete="RESTRICT"), nullable=True,
    )
    model_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ai_call_log_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("ai_call_logs.id", ondelete="RESTRICT"), nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "question_type IN ('qa','cloze','multiple_choice','short_explanation')",
            name="ck_review_items_question_type",
        ),
        CheckConstraint("item_version >= 1", name="ck_review_items_item_version"),
        UniqueConstraint(
            "knowledge_point_id", "question_type", "item_version",
            name="uq_review_items_kp_type_version",
        ),
        Index(
            "uq_review_items_current", "knowledge_point_id",
            unique=True, postgresql_where=text("is_current"),
        ),
        Index("ix_review_items_user_id", "user_id"),
    )


__all__ = ["KnowledgePoint", "KnowledgePointSource", "ReviewItem"]
