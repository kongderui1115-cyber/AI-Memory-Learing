"""Notion 同步与原文模型（DATABASE_SCHEMA.md §2「Notion 同步与原文」）。"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CHAR, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer,
    String, Text, UniqueConstraint, Uuid, text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import (
    Base, CreatedAtMixin, JSONB_OBJECT_DEFAULT, TimestampMixin,
    UserFkMixin, UUIDPkMixin, VersionMixin,
)


class NotionIntegration(UUIDPkMixin, UserFkMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "notion_integrations"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    credential_ref: Mapped[str] = mapped_column(String(160), nullable=False)
    api_version: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'2022-06-28'"))
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_notion_integrations_user_id_name"),
    )


class NotionDataSource(UUIDPkMixin, UserFkMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "notion_data_sources"

    integration_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("notion_integrations.id", ondelete="RESTRICT"), nullable=False,
    )
    subject_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=True,
    )
    status_property: Mapped[str] = mapped_column(String(120), nullable=False, server_default=text("'状态'"))
    status_mapping: Mapped[dict[str, str]] = mapped_column(
        JSONB, nullable=False, default=lambda: {"未开始": "not_started", "进行中": "in_progress", "已完成": "completed"},
        server_default=text("'{\"未开始\":\"not_started\",\"进行中\":\"in_progress\",\"已完成\":\"completed\"}'::jsonb"),
    )
    pending_watermark: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    external_source_id: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    sync_interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("60"))
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    last_edited_watermark: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_cursor: Mapped[str | None] = mapped_column(Text, nullable=True)
    lifecycle_cursor: Mapped[str | None] = mapped_column(String(128), nullable=True)
    next_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("source_type IN ('database','data_source','page_tree')", name="ck_notion_data_sources_source_type"),
        CheckConstraint("sync_interval_minutes >= 5", name="ck_notion_data_sources_sync_interval"),
        UniqueConstraint(
            "integration_id", "external_source_id",
            name="uq_notion_data_sources_integration_external",
        ),
        Index("ix_notion_data_sources_enabled_next_sync", "is_enabled", "next_sync_at"),
    )


class SyncRun(UUIDPkMixin, UserFkMixin, CreatedAtMixin, Base):
    __tablename__ = "sync_runs"

    data_source_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("notion_data_sources.id", ondelete="RESTRICT"), nullable=False,
    )
    trigger_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'pending'"))
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    watermark_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    watermark_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cursor_from: Mapped[str | None] = mapped_column(Text, nullable=True)
    cursor_to: Mapped[str | None] = mapped_column(Text, nullable=True)
    items_seen: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    items_imported: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    items_failed: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("trigger_type IN ('manual','scheduled')", name="ck_sync_runs_trigger_type"),
        CheckConstraint(
            "status IN ('pending','running','succeeded','failed','partial','cancelled')",
            name="ck_sync_runs_status",
        ),
        UniqueConstraint("user_id", "idempotency_key", name="uq_sync_runs_user_id_idempotency_key"),
        Index("ix_sync_runs_source_created", "data_source_id", text("created_at DESC")),
        Index("ix_sync_runs_status_next_retry", "status", "next_retry_at"),
    )


class RawNote(UUIDPkMixin, UserFkMixin, CreatedAtMixin, Base):
    __tablename__ = "raw_notes"

    data_source_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("notion_data_sources.id", ondelete="RESTRICT"), nullable=False,
    )
    sync_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sync_runs.id", ondelete="RESTRICT"), nullable=False,
    )
    external_page_id: Mapped[str] = mapped_column(String(128), nullable=False)
    external_version: Mapped[str] = mapped_column(String(128), nullable=False)
    last_edited_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 属性名不能叫 metadata（DeclarativeBase 保留），显式映射到列名 "metadata"。
    note_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default=JSONB_OBJECT_DEFAULT,
    )
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"),
    )

    __table_args__ = (
        UniqueConstraint(
            "data_source_id", "external_page_id", "external_version",
            name="uq_raw_notes_source_page_version",
        ),
        Index("ix_raw_notes_user_last_edited", "user_id", "last_edited_time"),
        Index("ix_raw_notes_content_hash", "content_hash"),
    )


__all__ = ["NotionIntegration", "NotionDataSource", "SyncRun", "RawNote"]
