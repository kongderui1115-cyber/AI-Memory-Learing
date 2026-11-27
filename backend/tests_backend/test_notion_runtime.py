"""Real PostgreSQL source workflows. Only external Notion HTTP uses fixtures."""

import asyncio
import json
import os
import sys
import threading
import unittest
from dataclasses import replace
from datetime import timedelta
from unittest.mock import patch
from uuid import UUID, uuid4

import test_core_api as core
from sqlalchemy import func, select

from app.ai.ports import HttpResponse
from app.database import Database
from app.integrations.notion.client import NotionTransport
from app.integrations.notion.runtime import RuntimeNotionClient
from app.models import Chapter, ChapterJob, NotionDataSource, RawNote, ScheduleState, SyncRun
from app.services import notion
from app.services.common import utcnow
from app.services.notion import process_run


def notion_page(page_id=None, *, status="进行中", edited="2026-11-14T09:00:00Z"):
    page_id = page_id or str(uuid4())
    return {
        "id": page_id,
        "object": "page",
        "last_edited_time": edited,
        "url": "https://www.notion.so/" + page_id.replace("-", ""),
        "properties": {
            "标题": {"type": "title", "title": [{"plain_text": "章节 · 原始笔记"}]},
            "状态": {"type": "status", "status": {"name": status}},
        },
    }


def paragraph(text, *, block_id=None, children=False):
    return {
        "id": block_id or str(uuid4()),
        "type": "paragraph",
        "has_children": children,
        "paragraph": {"rich_text": [{"plain_text": text}]},
    }


class FixtureTransport(NotionTransport):
    def __init__(self, pages=None, callback=None):
        self.pages = pages or []
        self.callback = callback
        self.requests = []

    def request(self, method, url, headers, body, timeout_seconds):
        payload = json.loads(body) if body else None
        self.requests.append((method, url, payload))
        if self.callback:
            result = self.callback(method, url, payload)
        elif url.endswith("/query"):
            result = {"results": self.pages, "has_more": False, "next_cursor": None}
        elif "/pages/" in url:
            result = next((page for page in self.pages if url.endswith(page["id"])), None)
            if result is None:
                return HttpResponse(status_code=404, body=b"{}", headers={})
        else:
            result = {"results": [paragraph("原文正文及例子。")], "has_more": False}
        if isinstance(result, HttpResponse):
            return result
        return HttpResponse(status_code=200, body=json.dumps(result).encode(), headers={})


@unittest.skipUnless(os.environ.get("TEST_DATABASE_URL"), "TEST_DATABASE_URL required")
class NotionAPI(unittest.IsolatedAsyncioTestCase):
    sequence = 100
    asyncSetUp = core.CoreAPI.asyncSetUp
    asyncTearDown = core.CoreAPI.asyncTearDown
    login = core.CoreAPI.login
    request = core.CoreAPI.request
    subject = core.CoreAPI.subject

    def _setupAsyncioRunner(self):
        if sys.platform == "win32":
            self._asyncioRunner = asyncio.Runner(loop_factory=asyncio.SelectorEventLoop)
        else:
            super()._setupAsyncioRunner()

    async def source(self, *, source_type="data_source"):
        self.reference = "MEMORY_USER_" + self.users[0].id.hex.upper() + "_NOTION_TOKEN"
        response = await self.request(
            "POST",
            "/notion/integrations",
            key=str(uuid4()),
            body={
                "name": "学习笔记",
                "credential_ref": self.reference,
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        self.integration = response.json()
        subject = await self.subject()
        response = await self.request(
            "POST",
            "/notion/data-sources",
            key=str(uuid4()),
            body={
                "integration_id": self.integration["id"],
                "subject_id": subject["id"],
                "external_source_id": str(uuid4()),
                "source_type": source_type,
                "name": "知识库",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        self.settings = replace(
            self.settings, raw={self.reference: "fixture-only-not-a-real-token"}
        )
        self.app.state.settings = self.settings
        return response.json()

    async def enqueue(self, source, key=None):
        response = await self.request(
            "POST", f"/notion/data-sources/{source['id']}/sync", key=key or str(uuid4())
        )
        self.assertEqual(response.status_code, 202, response.text)
        return response.json()

    async def process(self, run, transport):
        return await process_run(
            self.app.state.database, self.settings, UUID(run["id"]), transport=transport
        )

    async def test_configuration_ownership_idempotency_and_versions(self):
        source = await self.source()
        for path in [
            f"/notion/integrations/{self.integration['id']}",
            f"/notion/data-sources/{source['id']}",
        ]:
            response = await self.request("GET", path, user=1)
            self.assertEqual(response.status_code, 404)
        response = await self.request(
            "POST",
            "/notion/integrations",
            user=1,
            key=str(uuid4()),
            body={"name": "bad", "credential_ref": self.reference},
        )
        self.assertEqual(response.status_code, 403)
        response = await self.request(
            "PATCH",
            f"/notion/data-sources/{source['id']}",
            version=source["version"],
            body={"sync_interval_minutes": 15},
        )
        self.assertEqual(response.status_code, 200, response.text)
        response = await self.request(
            "PATCH",
            f"/notion/data-sources/{source['id']}",
            version=source["version"],
            body={"is_enabled": False},
        )
        self.assertEqual(response.status_code, 409)
        first = await self.enqueue(source, "same-key")
        second = await self.enqueue(source, "same-key")
        self.assertEqual(first["id"], second["id"])
        response = await self.request("GET", "/notion/sync-runs", user=1)
        self.assertEqual(response.json()["items"], [])

    async def test_originals_are_deduplicated_and_completed_chapter_is_queued(self):
        source = await self.source()
        page = notion_page()
        transport = FixtureTransport([page])
        result = await self.process(await self.enqueue(source), transport)
        self.assertEqual(result["status"], "succeeded", result)
        result = await self.process(await self.enqueue(source), transport)
        self.assertEqual(result["count"], 0)
        async with self.owner.transaction() as session:
            chapter = await session.scalar(
                select(Chapter).where(Chapter.user_id == self.users[0].id)
            )
            self.assertEqual(chapter.status, "in_progress")
            self.assertEqual(chapter.content.strip(), "原文正文及例子。")
            self.assertIsNone(
                await session.scalar(
                    select(ChapterJob.id).where(ChapterJob.chapter_id == chapter.id)
                )
            )
        page["properties"]["状态"]["status"]["name"] = "已完成"
        page["last_edited_time"] = "2026-11-15T09:00:00Z"
        result = await self.process(await self.enqueue(source), transport)
        self.assertEqual(result["count"], 1, result)
        await self.process(await self.enqueue(source), transport)
        async with self.owner.transaction() as session:
            chapter = await session.scalar(
                select(Chapter).where(Chapter.user_id == self.users[0].id)
            )
            self.assertEqual(chapter.status, "completed")
            self.assertEqual(chapter.completed_at.isoformat(), "2026-11-15T09:00:00+00:00")
            self.assertEqual(
                await session.scalar(
                    select(func.count(ChapterJob.id)).where(ChapterJob.chapter_id == chapter.id)
                ),
                1,
            )
            self.assertEqual(
                await session.scalar(
                    select(func.count(RawNote.id)).where(RawNote.user_id == self.users[0].id)
                ),
                2,
            )
            self.assertEqual(
                await session.scalar(
                    select(func.count(ScheduleState.id)).where(
                        ScheduleState.user_id == self.users[0].id
                    )
                ),
                0,
            )
        response = await self.request("GET", "/raw-notes")
        original = response.json()["items"][0]
        self.assertEqual(original["note_metadata"]["origin"], "notion")
        self.assertTrue(original["source_url"].startswith("https://www.notion.so/"))
        response = await self.request("GET", "/raw-notes/" + original["id"], user=1)
        self.assertEqual(response.status_code, 404)

    async def test_mapping_error_retains_good_pages_and_holds_watermark_until_retry(self):
        source = await self.source()
        transport = FixtureTransport([notion_page(status="已完成"), notion_page(status="未知状态")])
        run = await self.enqueue(source)
        result = await self.process(run, transport)
        self.assertEqual(result["status"], "partial", result)
        self.assertEqual(result["error_code"], "VALIDATION_ERROR", result)
        self.assertEqual(result["count"], 1)
        async with self.owner.transaction() as session:
            stored = await session.get(NotionDataSource, UUID(source["id"]))
            self.assertIsNone(stored.last_edited_watermark)
            self.assertIsNone(stored.last_cursor)
            partial = await session.get(SyncRun, UUID(run["id"]))
            self.assertEqual((partial.items_seen, partial.items_imported, partial.items_failed), (2, 1, 1))
            notes = await session.scalars(select(RawNote).where(RawNote.user_id == self.users[0].id))
            self.assertEqual([note.external_page_id for note in notes], [transport.pages[0]["id"]])
            chapter = await session.scalar(select(Chapter).where(Chapter.user_id == self.users[0].id))
            self.assertEqual(chapter.status, "completed")
        response = await self.request("POST", f"/notion/sync-runs/{run['id']}/retry")
        self.assertEqual(response.status_code, 202, response.text)
        transport.pages[1]["properties"]["状态"]["status"]["name"] = "未开始"
        result = await self.process(run, transport)
        self.assertEqual(result["status"], "succeeded", result)
        self.assertEqual(result["count"], 1)
        async with self.owner.transaction() as session:
            stored = await session.get(NotionDataSource, UUID(source["id"]))
            self.assertIsNotNone(stored.last_edited_watermark)
            self.assertEqual(await session.scalar(
                select(func.count(RawNote.id)).where(RawNote.user_id == self.users[0].id)
            ), 2)

    async def test_missing_token_persists_failure_without_http_then_resumes(self):
        source = await self.source()
        self.settings = replace(self.settings, raw={})
        transport = FixtureTransport([notion_page()])
        run = await self.enqueue(source)
        result = await self.process(run, transport)
        self.assertEqual(result["error_code"], "CONFIG_MISSING")
        self.assertEqual(transport.requests, [])
        self.settings = replace(self.settings, raw={self.reference: "fixture-only"})
        await self.request("POST", f"/notion/sync-runs/{run['id']}/retry")
        # A separate engine reproduces process restart with the queued job stored in PostgreSQL.
        restarted = Database(self.settings)
        try:
            result = await process_run(
                restarted, self.settings, UUID(run["id"]), transport=transport
            )
            self.assertEqual(result["status"], "succeeded", result)
        finally:
            await restarted.close()

    async def test_paginated_query_keeps_lower_bound_and_reconciles_trash_between_pages(self):
        source = await self.source()
        pages = [
            notion_page(edited="2026-11-14T09:00:00Z"),
            notion_page(edited="2026-11-15T09:00:00Z"),
        ]

        def callback(method, url, body):
            if url.endswith("/query"):
                index = 1 if body.get("start_cursor") else 0
                return {
                    "results": [pages[index]],
                    "has_more": index == 0,
                    "next_cursor": "next-page" if index == 0 else None,
                }
            if url.endswith("/pages/" + pages[0]["id"]):
                return {
                    **pages[0], "in_trash": True, "properties": {},
                    "last_edited_time": "2026-11-30T09:00:00Z",
                }
            return {"results": [paragraph("正文")], "has_more": False}

        transport = FixtureTransport(callback=callback)
        for index in range(2):
            result = await self.process(await self.enqueue(source), transport)
            self.assertEqual(result["status"], "succeeded", result)
            async with self.owner.transaction() as session:
                row = await session.get(NotionDataSource, UUID(source["id"]))
                if index == 0:
                    self.assertIsNone(row.last_edited_watermark)
                    self.assertEqual(row.last_cursor, "next-page")
                else:
                    self.assertIsNone(row.last_cursor)
                    self.assertEqual(
                        row.last_edited_watermark.isoformat(), "2026-11-15T09:00:00+00:00"
                    )
                    archived = await session.scalar(select(Chapter).where(
                        Chapter.user_id == self.users[0].id, Chapter.external_page_id == pages[0]["id"]
                    ))
                    self.assertIsNotNone(archived.notion_archived_at)
        queries = [body for method, url, body in transport.requests if url.endswith("/query")]
        self.assertTrue(all("filter" not in body for body in queries))

    async def test_parallel_workers_claim_source_once(self):
        source = await self.source()
        run = await self.enqueue(source)
        entered, release = threading.Event(), threading.Event()

        def callback(method, url, body):
            if url.endswith("/query"):
                entered.set()
                if not release.wait(5):
                    raise RuntimeError("Fixture timed out")
                return {"results": [notion_page()], "has_more": False}
            return {"results": [paragraph("正文")], "has_more": False}

        transport = FixtureTransport(callback=callback)
        first = asyncio.create_task(self.process(run, transport))
        try:
            self.assertTrue(await asyncio.to_thread(entered.wait, 3))
            second = await self.process(run, transport)
            self.assertEqual(second["status"], "busy", second)
        finally:
            release.set()
        self.assertEqual((await first)["status"], "succeeded")
        async with self.owner.transaction() as session:
            self.assertEqual(
                await session.scalar(
                    select(func.count(RawNote.id)).where(RawNote.user_id == self.users[0].id)
                ),
                1,
            )

    async def test_trash_reconciliation_preserves_originals_and_restoration_requeues(self):
        source = await self.source()
        page = notion_page(status="已完成")
        result = await self.process(await self.enqueue(source), FixtureTransport([page]))
        self.assertEqual(result["status"], "succeeded", result)

        def fallback(status, payload=None):
            def callback(method, url, body):
                if url.endswith("/query"):
                    return {"results": [], "has_more": False}
                self.assertTrue(url.endswith("/pages/" + page["id"]), url)
                if payload is not None:
                    return payload
                return HttpResponse(status_code=status, body=b"{}", headers={})
            return FixtureTransport(callback=callback)

        for status in (403, 404):
            result = await self.process(await self.enqueue(source), fallback(status))
            self.assertEqual(result["status"], "succeeded", result)
            async with self.owner.transaction() as session:
                chapter = await session.scalar(select(Chapter).where(
                    Chapter.user_id == self.users[0].id
                ))
                self.assertIsNone(chapter.notion_archived_at)

        trashed = {
            **page, "in_trash": True, "properties": {},
            # A separate archive observation must not advance the incremental watermark.
            "last_edited_time": "2026-11-30T09:00:00Z",
        }
        result = await self.process(await self.enqueue(source), fallback(200, trashed))
        self.assertEqual(result["status"], "succeeded", result)
        self.assertEqual(result["count"], 1)
        async with self.owner.transaction() as session:
            chapter = await session.scalar(select(Chapter).where(Chapter.user_id == self.users[0].id))
            self.assertIsNotNone(chapter.notion_archived_at)
            self.assertEqual(chapter.status, "completed")
            self.assertEqual(chapter.content.strip(), "原文正文及例子。")
            job = await session.scalar(select(ChapterJob).where(ChapterJob.chapter_id == chapter.id))
            self.assertEqual((job.status, job.error_code), ("cancelled", "SOURCE_ARCHIVED"))
            stored = await session.get(NotionDataSource, UUID(source["id"]))
            self.assertEqual(stored.last_edited_watermark.isoformat(), "2026-11-14T09:00:00+00:00")
            original = await session.scalar(select(RawNote).where(
                RawNote.data_source_id == stored.id, RawNote.external_version.endswith(":archived")
            ))
            self.assertTrue(original.note_metadata["in_trash"])
            self.assertEqual(original.content_markdown.strip(), "原文正文及例子。")
            self.assertEqual(original.title, "章节 · 原始笔记")

        again = await self.process(await self.enqueue(source), fallback(200, trashed))
        self.assertEqual(again["count"], 0)
        restored = {**page, "last_edited_time": trashed["last_edited_time"], "in_trash": False}
        result = await self.process(await self.enqueue(source), FixtureTransport([restored]))
        self.assertEqual(result["status"], "succeeded", result)
        async with self.owner.transaction() as session:
            chapter = await session.scalar(select(Chapter).where(Chapter.user_id == self.users[0].id))
            self.assertIsNone(chapter.notion_archived_at)
            job = await session.scalar(select(ChapterJob).where(ChapterJob.chapter_id == chapter.id))
            self.assertEqual((job.status, job.error_code), ("pending", None))

    async def test_rejected_cursor_restarts_from_the_last_committed_watermark(self):
        source = await self.source()
        page = notion_page(edited="2026-11-14T09:00:00Z")
        result = await self.process(await self.enqueue(source), FixtureTransport([page]))
        self.assertEqual(result["status"], "succeeded", result)
        async with self.owner.transaction() as session:
            row = await session.get(NotionDataSource, UUID(source["id"]))
            row.last_cursor = "expired"
            row.pending_watermark = row.last_edited_watermark + timedelta(days=3)

        def callback(method, url, body):
            if not url.endswith("/query"):
                return {"results": [paragraph("恢复分页后的正文")], "has_more": False}
            if body.get("start_cursor"):
                return HttpResponse(status_code=400, body=b"{}", headers={})
            return {"results": [{**page, "last_edited_time": "2026-11-15T09:00:00Z"}]}

        transport = FixtureTransport(callback=callback)
        result = await self.process(await self.enqueue(source), transport)
        self.assertEqual(result["status"], "succeeded", result)
        queries = [body for _, url, body in transport.requests if url.endswith("/query")]
        self.assertEqual([body.get("start_cursor") for body in queries], ["expired", None])
        self.assertEqual(queries[0]["filter"], queries[1]["filter"])
        async with self.owner.transaction() as session:
            row = await session.get(NotionDataSource, UUID(source["id"]))
            self.assertIsNone(row.last_cursor)
            self.assertIsNone(row.pending_watermark)
            self.assertEqual(row.last_edited_watermark.isoformat(), "2026-11-15T09:00:00+00:00")

    async def test_rate_limit_and_terminal_failure_control_scheduled_replay(self):
        source = await self.source()
        source_id = UUID(source["id"])
        db = self.app.state.database
        run = await notion.enqueue_sync(
            db, self.settings, self.users[0].id, source_id, "automatic", trigger="scheduled"
        )
        run = run.model_dump(mode="json")
        current = utcnow()
        transport = FixtureTransport(callback=lambda *_: HttpResponse(
            status_code=529, body=b"fixture-only-opaque-response", headers={"Retry-After": "185"}
        ))
        with patch.object(notion, "utcnow", return_value=current):
            result = await self.process(run, transport)
            self.assertEqual(result["error_code"], "RATE_LIMITED")
            self.assertEqual((await self.process(run, transport))["status"], "deferred")
            self.assertEqual(len(transport.requests), 1)
        async with self.owner.transaction() as session:
            stored = await session.get(SyncRun, UUID(run["id"]))
            self.assertEqual(stored.next_retry_at, current + timedelta(seconds=185))
            self.assertNotIn("fixture-only-opaque-response", stored.error_message)

        terminal_time = current + timedelta(seconds=186)
        denied = FixtureTransport(callback=lambda *_: HttpResponse(
            status_code=401, body=b"fixture-only-opaque-response", headers={}
        ))
        with patch.object(notion, "utcnow", return_value=terminal_time):
            result = await self.process(run, denied)
            self.assertEqual(result["error_code"], "EXTERNAL_SERVICE_ERROR")
            new = await notion.enqueue_sync(
                db, self.settings, self.users[0].id, source_id, "automatic", trigger="scheduled"
            )
            self.assertIsNone(new)
        async with self.owner.transaction() as session:
            row = await session.get(NotionDataSource, source_id)
            stored = await session.get(SyncRun, UUID(run["id"]))
            self.assertEqual(row.next_sync_at, terminal_time + timedelta(minutes=60))
            self.assertIsNone(stored.next_retry_at)
            self.assertIn("已撤销", stored.error_message)

    async def test_legacy_source_can_receive_subject_mapping_and_resync(self):
        source = await self.source()
        async with self.owner.transaction() as session:
            row = await session.get(NotionDataSource, UUID(source["id"]))
            row.subject_id = None
            row.external_source_id = row.external_source_id.replace("-", "")
        response = await self.request(
            "PATCH",
            f"/notion/data-sources/{source['id']}",
            version=source["version"],
            body={"subject_id": source["subject_id"]},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["subject_id"], source["subject_id"])
        result = await self.process(await self.enqueue(source), FixtureTransport([notion_page()]))
        self.assertEqual(result["status"], "succeeded", result)

    async def test_standalone_page_tree_uses_local_chapter_status(self):
        source = await self.source(source_type="page_tree")
        page = notion_page(source["external_source_id"])
        del page["properties"]["状态"]

        def callback(method, url, body):
            if "/pages/" in url:
                return page
            return {"results": [paragraph("普通页面笔记")], "has_more": False}

        transport = FixtureTransport(callback=callback)
        result = await self.process(await self.enqueue(source), transport)
        self.assertEqual(result["status"], "succeeded", result)
        response = await self.request("GET", "/chapters")
        chapter = response.json()["items"][0]
        self.assertEqual(chapter["status"], "not_started")
        response = await self.request(
            "POST", f"/chapters/{chapter['id']}/complete", key=str(uuid4())
        )
        self.assertEqual(response.status_code, 200, response.text)
        result = await self.process(await self.enqueue(source), transport)
        self.assertEqual(result["status"], "succeeded", result)
        response = await self.request("GET", "/chapters/" + chapter["id"])
        self.assertEqual(response.json()["status"], "completed")


class ReaderTests(unittest.TestCase):
    def test_query_preserves_explicit_archive_states(self):
        pages = [notion_page() for _ in range(4)]
        pages[1]["archived"] = True
        pages[2]["in_trash"] = True
        pages[3]["is_archived"] = True
        transport = FixtureTransport(pages)
        client = RuntimeNotionClient(
            token="fixture-only", api_version="2026-03-11", transport=transport
        )
        query = client.query("data_source", str(uuid4()))
        self.assertEqual([page.is_archived for page in query.pages], [False, True, True, True])
        self.assertTrue(all(page.external_version.endswith(":archived") for page in query.pages[1:]))
        self.assertEqual(transport.requests[0][2]["archive_status"], "all")

    def test_blocks_are_recursively_paginated_and_child_pages_remain_separate(self):
        nested_id, child_id = str(uuid4()), str(uuid4())

        def callback(method, url, body):
            if nested_id in url:
                return {"results": [paragraph("嵌套第三层")], "has_more": False}
            if "start_cursor" in url:
                return {
                    "results": [
                        paragraph("第二页正文"),
                        {
                            "id": child_id,
                            "type": "child_page",
                            "has_children": True,
                            "child_page": {"title": "独立子章节"},
                        },
                    ],
                    "has_more": False,
                }
            return {
                "results": [paragraph("第一页正文", block_id=nested_id, children=True)],
                "has_more": True,
                "next_cursor": "cursor+/=",
            }

        transport = FixtureTransport(callback=callback)
        client = RuntimeNotionClient(token="fixture-only", transport=transport)
        text = client.markdown(str(uuid4()))
        for expected in ("第一页正文", "第二页正文", "嵌套第三层", "独立子章节"):
            self.assertIn(expected, text)
        self.assertFalse(any(child_id in url for method, url, body in transport.requests))
        self.assertTrue(any("cursor%2B%2F%3D" in url for method, url, body in transport.requests))

    def test_multi_data_source_database_requires_explicit_choice(self):
        transport = FixtureTransport(
            callback=lambda *_: {"data_sources": [{"id": str(uuid4())}, {"id": str(uuid4())}]}
        )
        client = RuntimeNotionClient(
            token="fixture-only", api_version="2026-03-11", transport=transport
        )
        with self.assertRaisesRegex(Exception, "explicit data_source"):
            client.query("database", str(uuid4()))
