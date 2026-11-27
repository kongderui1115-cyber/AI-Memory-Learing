"""AI-02 Notion 增量同步纯逻辑测试：水位 / 幂等 / 原文留存 / 失败重试。

全部为真实纯逻辑测试：不联网、不连数据库、不使用任何 mock。
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_TESTS = Path(__file__).resolve().parent
for _path in (str(_BACKEND), str(_TESTS)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from app.ai.errors import ConfigMissingError, InvalidStateError  # noqa: E402
from app.ai.validation import (  # noqa: E402
    RAW_NOTE_READ_FIELDS,
    SYNC_RUN_READ_FIELDS,
)
from app.integrations.notion.models import (  # noqa: E402
    DataSourceCursor,
    NotionPage,
    SyncRun,
    compute_next_retry_at,
    compute_next_sync_at,
    parse_utc,
)
from app.integrations.notion.sync import (  # noqa: E402
    IdempotencyIndex,
    advance_watermark,
    assert_sync_ready,
    build_raw_notes,
    compute_sync_idempotency_key,
    idempotency_key,
    plan_sync,
    record_sync_failure,
    select_incremental_pages,
)

NOW = datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc)
T1 = "2026-01-01T00:00:00+00:00"
T2 = "2026-01-02T00:00:00+00:00"
T3 = "2026-01-03T00:00:00+00:00"
DS = "44444444-4444-4444-4444-444444444444"


def _page(pid: str, edited: str, *, title: str = "标题", content: str = "原文") -> NotionPage:
    return NotionPage(
        external_page_id=pid,
        external_version=edited,
        last_edited_time=edited,
        title=title,
        content_markdown=content,
        source_url=f"https://www.notion.so/{pid}",
        metadata={"created_time": edited},
    )


def _cursor(**overrides) -> DataSourceCursor:
    data = {
        "data_source_id": DS,
        "external_source_id": "db-1",
        "source_type": "database",
        "is_enabled": True,
        "sync_interval_minutes": 60,
        "last_edited_watermark": None,
        "last_cursor": None,
        "next_sync_at": None,
    }
    data.update(overrides)
    return DataSourceCursor(**data)


class IdempotencyKeyTests(unittest.TestCase):
    def test_stable_and_distinct(self):
        first = idempotency_key(DS, "p1", T1)
        self.assertEqual(len(first), 64)
        self.assertEqual(first, idempotency_key(DS, "p1", T1))
        self.assertNotEqual(first, idempotency_key(DS, "p1", T2))
        self.assertNotEqual(first, idempotency_key(DS, "p2", T1))

    def test_empty_component_rejected(self):
        for args in (("", "p", "v"), (DS, "", "v"), (DS, "p", "")):
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    idempotency_key(*args)

    def test_index(self):
        index = IdempotencyIndex([idempotency_key(DS, "p1", T1)])
        self.assertTrue(index.is_duplicate(idempotency_key(DS, "p1", T1)))
        self.assertFalse(index.is_duplicate(idempotency_key(DS, "p2", T1)))
        index.add(idempotency_key(DS, "p2", T1))
        self.assertEqual(len(index), 2)

    def test_sync_run_idempotency_key(self):
        key = compute_sync_idempotency_key("u1", DS, "client-key-1")
        self.assertEqual(len(key), 64)
        self.assertEqual(key, compute_sync_idempotency_key("u1", DS, "client-key-1"))
        self.assertNotEqual(key, compute_sync_idempotency_key("u2", DS, "client-key-1"))
        with self.assertRaises(ConfigMissingError):
            compute_sync_idempotency_key("u1", DS, "   ")


class WatermarkTests(unittest.TestCase):
    def test_select_incremental_filters_and_sorts(self):
        pages = [_page("p3", T3), _page("p1", T1), _page("p2", T2)]
        selected = select_incremental_pages(pages, T1)
        self.assertEqual([p.external_page_id for p in selected], ["p2", "p3"])

    def test_select_incremental_without_watermark_is_full(self):
        pages = [_page("p3", T3), _page("p1", T1)]
        self.assertEqual([p.external_page_id for p in select_incremental_pages(pages, None)],
                         ["p1", "p3"])

    def test_advance_watermark_takes_max_of_success_pages(self):
        self.assertEqual(
            advance_watermark(None, [_page("p1", T1), _page("p3", T3)]), T3
        )

    def test_advance_watermark_never_regresses(self):
        self.assertEqual(advance_watermark(T3, [_page("p1", T1)]), T3)

    def test_advance_watermark_with_no_pages_keeps_current(self):
        self.assertEqual(advance_watermark(T2, []), T2)

    def test_failed_page_excluded_from_watermark(self):
        """水位只基于成功导入的页面推进，不能越过失败页。"""
        outcome = plan_sync(
            cursor=_cursor(),
            pages=[_page("p1", T1), _page("p2", T2), _page("p3", T3)],
            known_keys=[], user_id="u1", trigger_type="manual",
            client_idempotency_key="k1", failed_page_ids={"p3"}, now=NOW,
        )
        self.assertEqual(outcome.watermark_to, T2)
        self.assertEqual(outcome.run.status, "partial")
        self.assertEqual(outcome.run.items_failed, 1)
        self.assertIsNotNone(outcome.run.next_retry_at)
        self.assertIn("EXTERNAL_SERVICE_ERROR", outcome.run.error_code)


class PlanSyncTests(unittest.TestCase):
    def test_known_triplets_are_skipped(self):
        pages = [_page("p1", T1), _page("p2", T2), _page("p3", T3)]
        known = [idempotency_key(DS, "p1", T1), idempotency_key(DS, "p2", T2)]
        outcome = plan_sync(
            cursor=_cursor(), pages=pages, known_keys=known, user_id="u1",
            trigger_type="scheduled", client_idempotency_key="k1", now=NOW,
        )
        self.assertEqual(len(outcome.raw_notes), 1)
        self.assertEqual(outcome.raw_notes[0].external_page_id, "p3")
        self.assertEqual(len(outcome.duplicate_keys), 2)
        self.assertEqual(outcome.run.status, "succeeded")
        self.assertEqual(outcome.run.items_seen, 3)
        self.assertEqual(outcome.run.items_imported, 1)

    def test_repeat_same_batch_produces_no_duplicate_raw_notes(self):
        pages = [_page("p1", T1), _page("p2", T2)]
        first = plan_sync(
            cursor=_cursor(), pages=pages, known_keys=[], user_id="u1",
            trigger_type="manual", client_idempotency_key="k1", now=NOW,
        )
        keys = [idempotency_key(DS, p.external_page_id, p.external_version) for p in pages]
        second = plan_sync(
            cursor=_cursor(), pages=pages, known_keys=keys, user_id="u1",
            trigger_type="manual", client_idempotency_key="k2", now=NOW,
        )
        self.assertEqual(second.raw_notes, [])
        self.assertEqual(len(second.duplicate_keys), 2)
        self.assertEqual(second.run.items_imported, 0)

    def test_watermark_and_next_sync_at(self):
        outcome = plan_sync(
            cursor=_cursor(), pages=[_page("p1", T1)], known_keys=[],
            user_id="u1", trigger_type="manual", client_idempotency_key="k1",
            now=NOW,
        )
        self.assertEqual(outcome.watermark_to, T1)
        self.assertEqual(outcome.updated_cursor.last_edited_watermark, T1)
        self.assertEqual(
            parse_utc(outcome.next_sync_at), NOW + timedelta(minutes=60)
        )

    def test_pending_page_cursor_schedules_immediate_continuation(self):
        outcome = plan_sync(
            cursor=_cursor(), pages=[_page("p1", T1)], known_keys=[],
            user_id="u1", trigger_type="manual", client_idempotency_key="k1",
            next_cursor="cursor-abc", now=NOW,
        )
        self.assertEqual(outcome.cursor_to, "cursor-abc")
        self.assertEqual(parse_utc(outcome.next_sync_at), NOW)

    def test_invalid_trigger_type_rejected(self):
        with self.assertRaises(ConfigMissingError):
            plan_sync(
                cursor=_cursor(), pages=[], known_keys=[], user_id="u1",
                trigger_type="cron", client_idempotency_key="k1", now=NOW,
            )

    def test_build_raw_notes_content_hash_and_fields(self):
        notes = build_raw_notes(
            [_page("p1", T1, title="Заголовок", content="Текст")],
            data_source_id=DS, sync_run_id="run-1", user_id="u1",
            synced_at=T2,
        )
        note = notes[0]
        self.assertEqual(len(note.content_hash), 64)
        self.assertEqual(note.content_markdown, "Текст")
        self.assertEqual(note.title, "Заголовок")
        self.assertEqual(set(note.to_contract_dict()), set(RAW_NOTE_READ_FIELDS))
        self.assertEqual(note.to_row_dict()["sync_run_id"], "run-1")


class FailureRecordingTests(unittest.TestCase):
    def test_failure_keeps_watermark_and_sets_retry(self):
        run = SyncRun(
            data_source_id=DS, trigger_type="manual",
            idempotency_key="k", user_id="u1", clock=lambda: NOW,
        )
        run.start()
        cursor = _cursor(last_edited_watermark=T2)
        outcome = record_sync_failure(
            run=run, cursor=cursor,
            error=ConfigMissingError("Token 失效"), now=NOW,
        )
        self.assertEqual(run.status, "failed")
        self.assertEqual(run.error_code, "CONFIG_MISSING")
        self.assertEqual(outcome.watermark_to, T2)
        self.assertEqual(outcome.updated_cursor.last_edited_watermark, T2)
        self.assertIsNotNone(outcome.next_sync_at)

    def test_next_retry_exponential_backoff(self):
        first = compute_next_retry_at(NOW, 1)
        second = compute_next_retry_at(NOW, 2)
        self.assertEqual(parse_utc(first), NOW + timedelta(seconds=60))
        self.assertEqual(parse_utc(second), NOW + timedelta(seconds=120))

    def test_next_sync_interval_validation(self):
        self.assertEqual(parse_utc(compute_next_sync_at(NOW, 30)), NOW + timedelta(minutes=30))
        with self.assertRaises(ValueError):
            compute_next_sync_at(NOW, 4)


class StateMachineAndReadinessTests(unittest.TestCase):
    def test_sync_run_state_machine(self):
        run = SyncRun(
            data_source_id=DS, trigger_type="manual", idempotency_key="k",
            user_id="u1", clock=lambda: NOW,
        )
        self.assertEqual(run.status, "pending")
        run.start()
        run.succeed(watermark_to=T2, cursor_to=None, items_seen=2, items_imported=2)
        self.assertEqual(run.status, "succeeded")
        self.assertEqual(set(run.to_contract_dict()), set(SYNC_RUN_READ_FIELDS))
        with self.assertRaises(InvalidStateError):
            run.fail(error_code="X", error_message="y")

    def test_sync_run_partial_and_cancel(self):
        run = SyncRun(
            data_source_id=DS, trigger_type="manual", idempotency_key="k",
            user_id="u1", clock=lambda: NOW,
        )
        run.start()
        run.partial(
            watermark_to=T1, cursor_to=None, items_seen=2, items_imported=1,
            items_failed=1, error_code="EXTERNAL_SERVICE_ERROR",
            error_message="one failed",
        )
        self.assertEqual(run.status, "partial")
        self.assertEqual(run.items_failed, 1)
        other = SyncRun(
            data_source_id=DS, trigger_type="manual", idempotency_key="k2",
            user_id="u1", clock=lambda: NOW,
        )
        other.cancel("stop")
        self.assertEqual(other.status, "cancelled")

    def test_assert_sync_ready_requires_token(self):
        with self.assertRaises(ConfigMissingError) as ctx:
            assert_sync_ready(_cursor(), None)
        self.assertEqual(ctx.exception.code, "CONFIG_MISSING")
        self.assertIn("BLK-01", ctx.exception.message)

    def test_assert_sync_ready_requires_enabled_and_source_id(self):
        with self.assertRaises(ConfigMissingError):
            assert_sync_ready(_cursor(is_enabled=False), "token")
        with self.assertRaises(ConfigMissingError):
            assert_sync_ready(_cursor(external_source_id=""), "token")
        self.assertEqual(assert_sync_ready(_cursor(), "secret-token"), "secret-token")


if __name__ == "__main__":
    unittest.main()
