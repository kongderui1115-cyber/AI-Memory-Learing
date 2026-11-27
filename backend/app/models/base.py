"""ORM 基础（BE-02）：DeclarativeBase 与公共列 mixin。

严格对应 DATABASE_SCHEMA.md §1 通用约定：
- 主键 ``uuid``，默认 ``gen_random_uuid()``；
- 业务表均含 ``user_id uuid NOT NULL → users.id``（外键默认 RESTRICT）；
- 时间 ``timestamptz``（UTC）、非空、默认 ``now()``；
- 可编辑资源带 ``version int NOT NULL DEFAULT 1`` 乐观锁；
- jsonb 默认 ``'{}'`` / ``'[]'``。

仅使用 SQLAlchemy 2 / PostgreSQL 类型；本机依赖未安装，未执行运行时验证。
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, MetaData, Uuid, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

JSONB_OBJECT_DEFAULT = text("'{}'::jsonb")
JSONB_ARRAY_DEFAULT = text("'[]'::jsonb")


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UUIDPkMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid(),
    )


class UserFkMixin:
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False,
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )


class CreatedAtMixin:
    """仅追加写表（sync_runs / raw_notes / review_history / ...）只需 created_at。"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )


class VersionMixin:
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))


__all__ = [
    "Base", "NAMING_CONVENTION", "JSONB_OBJECT_DEFAULT", "JSONB_ARRAY_DEFAULT",
    "UUIDPkMixin", "UserFkMixin", "TimestampMixin", "CreatedAtMixin", "VersionMixin",
]
