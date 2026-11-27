"""Notion 同步领域数据结构（对齐 DATABASE_SCHEMA.md 与契约 Read 模型）。

- ``RawNote`` 对齐 ``raw_notes`` 表 / ``RawNoteRead``；
- ``SyncRun`` 对齐 ``sync_runs`` 表 / ``SyncRunRead``，含状态机；
- ``DataSourceCursor`` 对齐 ``notion_data_sources`` 的水位/游标/调度字段。

全部时间为 UTC 带时区 RFC3339 字符串；``clock`` 可注入以便真实单测。
本模块只使用标准库，且状态机为追加写语义（终态不可改写）。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from uuid import uuid4

from app.ai.errors import ErrorDetail, InvalidStateError
from app.ai.validation import RAW_NOTE_READ_FIELDS, SYNC_RUN_READ_FIELDS

RUN_TERMINAL_STATUSES = frozenset({"succeeded", "partial", "failed", "cancelled"})


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat()


def parse_utc(value: str) -> datetime:
    """解析 UTC RFC3339 字符串；无时区时按 UTC 处理。"""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class NotionPage:
    """一次查询得到的外部页面（解析后、落库前），Unicode 原文原样保留。"""

    external_page_id: str
    external_version: str
    last_edited_time: str
    title: str
    content_markdown: str = ""
    source_url: str = ""
    properties: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    has_children: bool = False
    is_archived: bool = False


@dataclass(frozen=True)
class RawNote:
    """对齐 ``raw_notes`` / ``RawNoteRead``；``content_hash`` 为 sha256(64)。"""

    data_source_id: str
    sync_run_id: str
    external_page_id: str
    external_version: str
    last_edited_time: str
    title: str
    content_markdown: str
    content_hash: str
    source_url: str
    metadata: dict[str, Any] = field(default_factory=dict)
    synced_at: str = ""
    id: str = field(default_factory=lambda: str(uuid4()))
    user_id: str = ""

    def to_contract_dict(self) -> dict[str, Any]:
        """只输出 ``RawNoteRead`` 契约字段。"""
        row = self.to_row_dict()
        return {name: row[name] for name in RAW_NOTE_READ_FIELDS}

    def to_row_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "data_source_id": self.data_source_id,
            "sync_run_id": self.sync_run_id,
            "external_page_id": self.external_page_id,
            "external_version": self.external_version,
            "last_edited_time": self.last_edited_time,
            "title": self.title,
            "content_markdown": self.content_markdown,
            "content_hash": self.content_hash,
            "source_url": self.source_url,
            "metadata": dict(self.metadata),
            "synced_at": self.synced_at,
        }


@dataclass
class SyncRun:
    """对齐 ``sync_runs`` / ``SyncRunRead``，状态机 pending→running→终态。"""

    data_source_id: str
    trigger_type: str
    idempotency_key: str
    user_id: str
    watermark_from: str | None = None
    cursor_from: str | None = None
    id: str = field(default_factory=lambda: str(uuid4()))
    status: str = "pending"
    watermark_to: str | None = None
    cursor_to: str | None = None
    items_seen: int = 0
    items_imported: int = 0
    items_failed: int = 0
    attempt: int = 1
    started_at: str | None = None
    finished_at: str | None = None
    next_retry_at: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: str = ""
    clock: Callable[[], datetime] = field(default=_utc_now, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = _iso(self.clock())

    def _assert_mutable(self) -> None:
        if self.status in RUN_TERMINAL_STATUSES:
            raise InvalidStateError(
                f"同步运行已处于终态 {self.status!r}，追加写不允许改写",
                details=[ErrorDetail("status", "terminal state is immutable")],
            )

    def start(self) -> None:
        if self.status != "pending":
            raise InvalidStateError(f"只能从 pending 进入 running，当前为 {self.status!r}")
        self.status = "running"
        self.started_at = _iso(self.clock())

    def _finish(self, status: str) -> None:
        self._assert_mutable()
        if self.status != "running":
            raise InvalidStateError(f"只能从 running 进入 {status}，当前为 {self.status!r}")
        self.status = status
        self.finished_at = _iso(self.clock())

    def succeed(
        self,
        *,
        watermark_to: str | None,
        cursor_to: str | None,
        items_seen: int,
        items_imported: int,
    ) -> None:
        self._finish("succeeded")
        self.watermark_to = watermark_to
        self.cursor_to = cursor_to
        self.items_seen = items_seen
        self.items_imported = items_imported
        self.items_failed = 0
        self.error_code = None
        self.error_message = None
        self.next_retry_at = None

    def partial(
        self,
        *,
        watermark_to: str | None,
        cursor_to: str | None,
        items_seen: int,
        items_imported: int,
        items_failed: int,
        error_code: str,
        error_message: str,
        next_retry_at: str | None = None,
    ) -> None:
        """部分成功：水位只推进到成功导入的批次，失败页保留重试时间。"""
        self._finish("partial")
        self.watermark_to = watermark_to
        self.cursor_to = cursor_to
        self.items_seen = items_seen
        self.items_imported = items_imported
        self.items_failed = items_failed
        self.error_code = error_code
        self.error_message = error_message
        self.next_retry_at = next_retry_at

    def fail(
        self,
        *,
        error_code: str,
        error_message: str,
        next_retry_at: str | None = None,
    ) -> None:
        self._finish("failed")
        self.error_code = error_code
        self.error_message = error_message
        self.next_retry_at = next_retry_at

    def cancel(self, reason: str = "") -> None:
        self._assert_mutable()
        self.status = "cancelled"
        self.error_code = "INVALID_STATE"
        self.error_message = reason or "同步被取消"
        self.finished_at = _iso(self.clock())

    def to_contract_dict(self) -> dict[str, Any]:
        row = self.to_row_dict()
        return {name: row[name] for name in SYNC_RUN_READ_FIELDS}

    def to_row_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "data_source_id": self.data_source_id,
            "trigger_type": self.trigger_type,
            "status": self.status,
            "idempotency_key": self.idempotency_key,
            "watermark_from": self.watermark_from,
            "watermark_to": self.watermark_to,
            "cursor_from": self.cursor_from,
            "cursor_to": self.cursor_to,
            "items_seen": self.items_seen,
            "items_imported": self.items_imported,
            "items_failed": self.items_failed,
            "attempt": self.attempt,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "next_retry_at": self.next_retry_at,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class DataSourceCursor:
    """对齐 ``notion_data_sources`` 的同步状态字段。"""

    data_source_id: str
    external_source_id: str
    source_type: str = "database"
    name: str = ""
    is_enabled: bool = True
    sync_interval_minutes: int = 60
    last_edited_watermark: str | None = None
    last_cursor: str | None = None
    next_sync_at: str | None = None

    def with_watermark(
        self, watermark: str | None, cursor: str | None, next_sync_at: str | None
    ) -> "DataSourceCursor":
        """返回推进后的新游标（不可变对象，避免误改历史）。"""
        return replace(
            self,
            last_edited_watermark=watermark,
            last_cursor=cursor,
            next_sync_at=next_sync_at,
        )


@dataclass(frozen=True)
class SyncOutcome:
    """一次增量同步编排的纯逻辑结果。"""

    run: SyncRun
    raw_notes: list[RawNote]
    watermark_to: str | None
    cursor_to: str | None
    next_sync_at: str | None
    duplicate_keys: list[str]
    failed_keys: list[str]
    updated_cursor: DataSourceCursor


def compute_next_sync_at(now: datetime, interval_minutes: int) -> str:
    """按可配置间隔计算下次同步时间（UTC）。"""
    if interval_minutes < 5:
        raise ValueError("sync_interval_minutes 必须 >= 5（契约 CK）")
    return _iso(now + timedelta(minutes=interval_minutes))


def compute_next_retry_at(
    now: datetime,
    attempt: int,
    *,
    base_backoff_seconds: float = 60.0,
    multiplier: float = 2.0,
    max_backoff_seconds: float = 3600.0,
) -> str:
    """失败重试的指数退避时间（UTC），对齐 FR-01「失败与重试记录」。"""
    if attempt < 1:
        raise ValueError("attempt 必须 >= 1")
    delay = min(base_backoff_seconds * (multiplier ** (attempt - 1)), max_backoff_seconds)
    return _iso(now + timedelta(seconds=delay))
