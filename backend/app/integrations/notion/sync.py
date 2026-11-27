"""Notion 增量同步核心纯逻辑（AI-02 / FR-01）。

覆盖：
- 基于 ``last_edited_time`` 的增量过滤与游标分页；
- ``(data_source_id, external_page_id, external_version)`` 三元组幂等；
- 水位推进（**仅在该批次成功持久化后推进，且单调不回退**）；
- 原始笔记留存（标题、原文 Markdown、page id、版本、内容哈希、同步时间）；
- 失败与重试记录（部分成功 / 失败 / 退避时间 / 状态机）。

未授权 Token 时 ``assert_sync_ready`` 抛 ``CONFIG_MISSING``，只实现真实
路径，绝不伪造同步结果。本模块不联网、不连数据库。
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Iterable

from app.ai.errors import AIIntegrationError, ConfigMissingError, ErrorDetail
from app.ai.validation import TRIGGER_TYPES, content_hash
from .client import NotionClient, assert_notion_token
from .models import (
    DataSourceCursor,
    NotionPage,
    RawNote,
    SyncOutcome,
    SyncRun,
    compute_next_retry_at,
    compute_next_sync_at,
    parse_utc,
    _iso,
)


def idempotency_key(
    data_source_id: str, external_page_id: str, external_version: str
) -> str:
    """三元组幂等键，对齐 ``raw_notes`` UQ ``(data_source_id, external_page_id, external_version)``。"""
    if not data_source_id or not external_page_id or not external_version:
        raise ValueError("三元组任一字段为空，无法构造幂等键")
    return content_hash(data_source_id, external_page_id, external_version)


def compute_sync_idempotency_key(
    user_id: str, data_source_id: str, client_key: str
) -> str:
    """``sync_runs.idempotency_key``，对齐契约 UQ ``(user_id, idempotency_key)``。"""
    if not client_key.strip():
        raise ConfigMissingError(
            "同步请求缺少 Idempotency-Key（契约 POST /notion/data-sources/{id}/sync）",
            details=[ErrorDetail("Idempotency-Key", "required")],
        )
    return content_hash(user_id, data_source_id, client_key)


class IdempotencyIndex:
    """已落库三元组的内存索引，用于判定重复同步（真实数据由持久层提供）。"""

    def __init__(self, keys: Iterable[str] = ()) -> None:
        self._keys: set[str] = set(keys)

    def is_duplicate(self, key: str) -> bool:
        return key in self._keys

    def add(self, key: str) -> None:
        self._keys.add(key)

    def __len__(self) -> int:
        return len(self._keys)


def assert_sync_ready(cursor: DataSourceCursor, token: str | None) -> str:
    """同步前置校验：Token 授权、数据源启用、外部 ID 存在（纯逻辑）。"""
    validated = assert_notion_token(token)
    if not cursor.is_enabled:
        raise ConfigMissingError(
            "Notion 数据源已禁用，拒绝执行同步",
            details=[ErrorDetail("is_enabled", "false")],
        )
    if not cursor.external_source_id.strip():
        raise ConfigMissingError(
            "Notion 数据源缺少 external_source_id（Database/Page ID）",
            details=[ErrorDetail("external_source_id", "missing")],
        )
    return validated


def select_incremental_pages(
    pages: Iterable[NotionPage], watermark: str | None
) -> list[NotionPage]:
    """按 ``last_edited_time`` 增量过滤；无水位时全量。结果按时间/页面 id 稳定排序。"""
    materialized = [page for page in pages if page.last_edited_time]
    if watermark:
        wm = parse_utc(watermark)
        materialized = [p for p in materialized if parse_utc(p.last_edited_time) > wm]
    return sorted(materialized, key=lambda p: (p.last_edited_time, p.external_page_id))


def advance_watermark(
    current: str | None, pages: Iterable[NotionPage]
) -> str | None:
    """水位推进：取**成功持久化页面**的最大 last_edited_time，且单调不回退。"""
    times = [p.last_edited_time for p in pages if p.last_edited_time]
    if not times:
        return current
    candidate = max(times, key=parse_utc)
    if current is None:
        return candidate
    return candidate if parse_utc(candidate) > parse_utc(current) else current


def build_raw_notes(
    pages: Iterable[NotionPage],
    *,
    data_source_id: str,
    sync_run_id: str,
    user_id: str,
    synced_at: str,
) -> list[RawNote]:
    """构造原始笔记留存记录，计算 ``content_hash``（原文+标题+版本）。"""
    notes: list[RawNote] = []
    for page in pages:
        notes.append(
            RawNote(
                data_source_id=data_source_id,
                sync_run_id=sync_run_id,
                external_page_id=page.external_page_id,
                external_version=page.external_version,
                last_edited_time=page.last_edited_time,
                title=page.title,
                content_markdown=page.content_markdown,
                content_hash=content_hash(
                    page.title, page.content_markdown, page.external_version
                ),
                source_url=page.source_url,
                metadata=dict(page.metadata),
                synced_at=synced_at,
                user_id=user_id,
            )
        )
    return notes


def plan_sync(
    *,
    cursor: DataSourceCursor,
    pages: Iterable[NotionPage],
    known_keys: Iterable[str],
    user_id: str,
    trigger_type: str,
    client_idempotency_key: str,
    failed_page_ids: Iterable[str] = (),
    next_cursor: str | None = None,
    now: datetime | None = None,
) -> SyncOutcome:
    """编排一次增量同步的**纯逻辑结果**（不发起 HTTP、不写库）。

    水位只基于成功导入的页面推进；失败页计入 ``items_failed`` 并保留
    ``next_retry_at``，重复三元组计入 ``duplicate_keys`` 不再产生原文。
    """
    if trigger_type not in TRIGGER_TYPES:
        raise ConfigMissingError(
            f"trigger_type 非法: {trigger_type!r}",
            details=[ErrorDetail("trigger_type", "invalid")],
        )
    moment = now or datetime.now().astimezone()
    synced_at = _iso(moment)
    run = SyncRun(
        data_source_id=cursor.data_source_id,
        trigger_type=trigger_type,
        idempotency_key=compute_sync_idempotency_key(
            user_id, cursor.data_source_id, client_idempotency_key
        ),
        user_id=user_id,
        watermark_from=cursor.last_edited_watermark,
        cursor_from=cursor.last_cursor,
        clock=lambda: moment,
    )
    run.start()

    incremental = select_incremental_pages(pages, cursor.last_edited_watermark)
    index = IdempotencyIndex(known_keys)
    failed_ids = set(failed_page_ids)
    imported: list[NotionPage] = []
    duplicate_keys: list[str] = []
    failed_keys: list[str] = []
    for page in incremental:
        key = idempotency_key(
            cursor.data_source_id, page.external_page_id, page.external_version
        )
        if index.is_duplicate(key):
            duplicate_keys.append(key)
            continue
        if page.external_page_id in failed_ids:
            failed_keys.append(key)
            continue
        index.add(key)
        imported.append(page)

    raw_notes = build_raw_notes(
        imported,
        data_source_id=cursor.data_source_id,
        sync_run_id=run.id,
        user_id=user_id,
        synced_at=synced_at,
    )
    watermark_to = advance_watermark(cursor.last_edited_watermark, imported)
    cursor_to = next_cursor
    # 还有分页游标时立即续跑；否则按可配置间隔安排下次同步。
    next_sync_at = (
        _iso(moment)
        if next_cursor
        else compute_next_sync_at(moment, cursor.sync_interval_minutes)
    )

    if failed_keys:
        retry_at = compute_next_retry_at(moment, run.attempt)
        run.partial(
            watermark_to=watermark_to,
            cursor_to=cursor_to,
            items_seen=len(incremental),
            items_imported=len(raw_notes),
            items_failed=len(failed_keys),
            error_code="EXTERNAL_SERVICE_ERROR",
            error_message=f"{len(failed_keys)} 个页面落库失败，保留重试时间，水位不越过失败页",
            next_retry_at=retry_at,
        )
    else:
        run.succeed(
            watermark_to=watermark_to,
            cursor_to=cursor_to,
            items_seen=len(incremental),
            items_imported=len(raw_notes),
        )

    updated_cursor = cursor.with_watermark(watermark_to, cursor_to, next_sync_at)
    return SyncOutcome(
        run=run,
        raw_notes=raw_notes,
        watermark_to=watermark_to,
        cursor_to=cursor_to,
        next_sync_at=next_sync_at,
        duplicate_keys=duplicate_keys,
        failed_keys=failed_keys,
        updated_cursor=updated_cursor,
    )


def record_sync_failure(
    *,
    run: SyncRun,
    cursor: DataSourceCursor,
    error: AIIntegrationError | BaseException,
    now: datetime,
) -> SyncOutcome:
    """外部调用失败时的真实留痕：run 置 failed，水位**不推进**，记录重试时间。"""
    code = getattr(error, "code", "EXTERNAL_SERVICE_ERROR")
    retry_at = compute_next_retry_at(now, run.attempt)
    run.fail(
        error_code=code,
        error_message=str(error),
        next_retry_at=retry_at,
    )
    return SyncOutcome(
        run=run,
        raw_notes=[],
        watermark_to=cursor.last_edited_watermark,
        cursor_to=cursor.last_cursor,
        next_sync_at=retry_at,
        duplicate_keys=[],
        failed_keys=[],
        updated_cursor=cursor.with_watermark(
            cursor.last_edited_watermark, cursor.last_cursor, retry_at
        ),
    )


class NotionSyncService:
    """把真实 ``NotionClient`` 与纯逻辑编排串起来的用例（AI-02 真实路径）。

    缺 Token 时 ``NotionClient`` 构造即抛 CONFIG_MISSING；本类不捕获、
    不降级、不伪造同步结果。所有外部调用都经由真实 HTTP 传输。
    """

    def __init__(self, client: NotionClient) -> None:
        self._client = client

    def sync(
        self,
        cursor: DataSourceCursor,
        *,
        user_id: str,
        trigger_type: str,
        client_idempotency_key: str,
        known_keys: Iterable[str],
        now: datetime | None = None,
    ) -> SyncOutcome:
        pages: list[NotionPage] = []
        start_cursor: str | None = cursor.last_cursor
        next_cursor: str | None = None
        while True:
            result = self._client.query_database(
                cursor.external_source_id,
                watermark=cursor.last_edited_watermark,
                start_cursor=start_cursor,
            )
            for page in result.pages:
                markdown = self._client.fetch_page_markdown(page.external_page_id)
                pages.append(replace(page, content_markdown=markdown))
            next_cursor = result.next_cursor if result.has_more else None
            if not next_cursor:
                break
            start_cursor = next_cursor
        return plan_sync(
            cursor=cursor,
            pages=pages,
            known_keys=known_keys,
            user_id=user_id,
            trigger_type=trigger_type,
            client_idempotency_key=client_idempotency_key,
            next_cursor=next_cursor,
            now=now,
        )
