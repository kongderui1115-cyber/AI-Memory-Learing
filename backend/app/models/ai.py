"""AI 配置与审计模型（DATABASE_SCHEMA.md §2「AI 配置与审计」）。"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric,
    String, Text, UniqueConstraint, Uuid, text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import (
    Base, CreatedAtMixin, JSONB_OBJECT_DEFAULT, TimestampMixin,
    UserFkMixin, UUIDPkMixin, VersionMixin,
)


class AIProviderConfig(UUIDPkMixin, UserFkMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "ai_provider_configs"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model_name: Mapped[str] = mapped_column(String(120), nullable=False)
    base_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    credential_ref: Mapped[str] = mapped_column(String(160), nullable=False)
    temperature: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False, server_default=text("0.2"))
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("60"))
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("3"))
    rate_limit_per_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    __table_args__ = (
        CheckConstraint(
            "provider IN ('openai','deepseek','openai_compatible')", name="ck_ai_provider_configs_provider",
        ),
        CheckConstraint("temperature BETWEEN 0 AND 2", name="ck_ai_provider_configs_temperature"),
        CheckConstraint("timeout_seconds > 0", name="ck_ai_provider_configs_timeout"),
        CheckConstraint("max_retries >= 0", name="ck_ai_provider_configs_max_retries"),
        UniqueConstraint("user_id", "name", name="uq_ai_provider_configs_user_id_name"),
        Index(
            "uq_ai_provider_configs_default", "user_id",
            unique=True, postgresql_where=text("is_default"),
        ),
    )


class AICallLog(UUIDPkMixin, UserFkMixin, CreatedAtMixin, Base):
    __tablename__ = "ai_call_logs"

    provider_config_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("ai_provider_configs.id", ondelete="RESTRICT"), nullable=False,
    )
    operation: Mapped[str] = mapped_column(String(40), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model_name: Mapped[str] = mapped_column(String(120), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(40), nullable=False)
    request_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'pending'"))
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # 属性名不能叫 metadata（DeclarativeBase 保留），显式映射到列名 "metadata"。
    call_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default=JSONB_OBJECT_DEFAULT,
    )

    __table_args__ = (
        CheckConstraint(
            "provider IN ('openai','deepseek','openai_compatible')", name="ck_ai_call_logs_provider",
        ),
        CheckConstraint(
            "status IN ('pending','running','succeeded','failed','cancelled')",
            name="ck_ai_call_logs_status",
        ),
        Index("ix_ai_call_logs_user_created", "user_id", text("created_at DESC")),
        Index("ix_ai_call_logs_status_created", "status", "created_at"),
        Index("ix_ai_call_logs_request_id", "request_id"),
    )


__all__ = ["AIProviderConfig", "AICallLog"]
