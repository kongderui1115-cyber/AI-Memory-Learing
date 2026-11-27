"""Regressions for Notion recovery and background stage isolation."""

import asyncio
import os
import sys
import unittest
from contextlib import asynccontextmanager
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID

import test_core_api as core
import test_notion_runtime as notion_tests
from sqlalchemy import func, select

from app.models import SyncRun
from app.services import background, notion
from app.services.common import utcnow


class BackgroundStageIsolation(unittest.IsolatedAsyncioTestCase):
    async def test_failure_in_each_stage_preserves_order_and_continues(self):
        names = [
            "sync_pending",
            "extract_pending",
            "generate_daily_tasks",
            "digest_lookup",
            "send_pending",
        ]
        own_stages = [name for name in names if name != "digest_lookup"]
        for failure in names:
            with self.subTest(failure=failure):
                attempts = []

                def record(name):
                    attempts.append(name)
                    if name == failure:
                        raise RuntimeError("private connector payload")

                def stage(name):
                    async def run(db, settings):
                        record(name)

                    return AsyncMock(side_effect=run)

                @asynccontextmanager
                async def transaction():
                    record("digest_lookup")
                    yield SimpleNamespace(
                        scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: []))
                    )

                db = SimpleNamespace(transaction=transaction)
                with patch.multiple(background, **{name: stage(name) for name in own_stages}):
                    with self.assertLogs(background.logger, level="WARNING") as logs:
                        await background.run_once(db, object())
                self.assertEqual(attempts, names)
                self.assertEqual(len(logs.records), 1)
                message = logs.records[0].getMessage()
                self.assertIn("RuntimeError", message)
                self.assertIn("stage=", message)
                self.assertNotIn("private connector payload", message)

    async def test_cancellation_stops_the_cycle(self):
        with patch.object(background, "sync_pending", AsyncMock(side_effect=asyncio.CancelledError)):
            with patch.object(background, "extract_pending", AsyncMock()) as extract:
                with self.assertRaises(asyncio.CancelledError):
                    await background.run_once(object(), object())
        extract.assert_not_awaited()


@unittest.skipUnless(os.environ.get("TEST_DATABASE_URL"), "TEST_DATABASE_URL required")
class BackgroundRecovery(unittest.IsolatedAsyncioTestCase):
    sequence = 420
    asyncSetUp = core.CoreAPI.asyncSetUp
    asyncTearDown = core.CoreAPI.asyncTearDown
    login = core.CoreAPI.login
    request = core.CoreAPI.request
    subject = core.CoreAPI.subject
    source = notion_tests.NotionAPI.source
    enqueue = notion_tests.NotionAPI.enqueue

    def _setupAsyncioRunner(self):
        if sys.platform == "win32":
            self._asyncioRunner = asyncio.Runner(loop_factory=asyncio.SelectorEventLoop)
        else:
            super()._setupAsyncioRunner()

    async def count_runs(self, source):
        async with self.owner.transaction() as session:
            return await session.scalar(
                select(func.count())
                .select_from(SyncRun)
                .where(SyncRun.data_source_id == UUID(source["id"]))
            )

    async def test_pending_run_is_reused_without_treating_its_uuid_as_a_model(self):
        source = await self.source()
        await self.enqueue(source)
        with patch.object(notion, "enqueue_sync", new_callable=AsyncMock) as enqueue:
            with patch.object(
                notion,
                "process_run",
                new_callable=AsyncMock,
                return_value={"status": "succeeded", "count": 0},
            ):
                result = await notion.sync_pending(self.app.state.database, self.settings)
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(await self.count_runs(source), 1)
        self.assertFalse(
            any(call.args[3] == UUID(source["id"]) for call in enqueue.await_args_list)
        )

    async def test_future_retry_does_not_enqueue_duplicate_or_process_early(self):
        source = await self.source()
        run = await self.enqueue(source)
        async with self.owner.transaction() as session:
            row = await session.get(SyncRun, UUID(run["id"]))
            row.status, row.next_retry_at = "failed", utcnow() + timedelta(hours=1)
        with patch.object(notion, "enqueue_sync", new_callable=AsyncMock) as enqueue:
            with patch.object(
                notion,
                "process_run",
                new_callable=AsyncMock,
                return_value={"status": "succeeded", "count": 0},
            ) as process:
                await notion.sync_pending(self.app.state.database, self.settings)
        self.assertEqual(await self.count_runs(source), 1)
        self.assertFalse(
            any(call.args[3] == UUID(source["id"]) for call in enqueue.await_args_list)
        )
        self.assertFalse(any(call.args[2] == UUID(run["id"]) for call in process.await_args_list))

    async def test_existing_sync_run_does_not_abort_following_background_stages(self):
        source = await self.source()
        await self.enqueue(source)
        with patch.object(notion, "enqueue_sync", new_callable=AsyncMock):
            with patch.object(
                notion,
                "process_run",
                new_callable=AsyncMock,
                return_value={"status": "succeeded", "count": 0},
            ):
                with patch.object(background, "extract_pending", new_callable=AsyncMock) as extract:
                    with patch.object(
                        background, "generate_daily_tasks", new_callable=AsyncMock
                    ) as generate:
                        with patch.object(background, "queue_digest", new_callable=AsyncMock):
                            with patch.object(
                                background, "send_pending", new_callable=AsyncMock
                            ) as send:
                                await background.run_once(self.app.state.database, self.settings)
        extract.assert_awaited_once()
        generate.assert_awaited_once()
        send.assert_awaited_once()
