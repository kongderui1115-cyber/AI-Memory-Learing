"""Cross-user admin connector API on isolated PostgreSQL; no external transport."""

import asyncio
import os
import sys
import unittest
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import test_core_api as core
from sqlalchemy import func, select

from app.models import (
    AuditEvent,
    DailyReviewBatch,
    NotificationChannelConfig,
    NotificationDelivery,
    NotificationJob,
    NotificationTemplate,
    NotionDataSource,
    NotionIntegration,
    Subject,
    SyncRun,
    UserSecret,
)
from app.services.common import utcnow


@unittest.skipUnless(os.environ.get("TEST_DATABASE_URL"), "TEST_DATABASE_URL required")
class AdminConnectors(unittest.IsolatedAsyncioTestCase):
    sequence = 184
    asyncSetUp = core.CoreAPI.asyncSetUp
    asyncTearDown = core.CoreAPI.asyncTearDown
    login = core.CoreAPI.login
    request = core.CoreAPI.request
    subject = core.CoreAPI.subject
    chapter = core.CoreAPI.chapter

    def _setupAsyncioRunner(self):
        if sys.platform == "win32":
            self._asyncioRunner = asyncio.Runner(loop_factory=asyncio.SelectorEventLoop)
        else:
            super()._setupAsyncioRunner()

    async def seed_source(self, owner, *, enabled=True):
        credential_ref = f"MEMORY_USER_{owner.hex.upper()}_NOTION_TOKEN"
        async with self.owner.transaction() as session:
            integration = NotionIntegration(
                user_id=owner, name=uuid4().hex, credential_ref=credential_ref, api_version="2026-03-11",
            )
            subject = Subject(user_id=owner, name="学习学科", slug=uuid4().hex)
            session.add_all([integration, subject])
            await session.flush()
            source = NotionDataSource(
                user_id=owner, integration_id=integration.id, subject_id=subject.id,
                source_type="data_source", external_source_id=str(uuid4()),
                name="连接的知识库", is_enabled=enabled,
            )
            session.add(source)
            await session.flush()
            return source.id, credential_ref

    async def seed_delivery(self, owner):
        credential_ref = f"MEMORY_USER_{owner.hex.upper()}_SMTP_PASSWORD"
        sent_at = utcnow()
        async with self.owner.transaction() as session:
            channel = NotificationChannelConfig(
                user_id=owner, name="有历史记录的邮箱", channel_type="smtp", credential_ref=credential_ref,
                settings={"credential_value": "private-channel-sentinel"},
            )
            template = NotificationTemplate(
                user_id=owner, channel_type="smtp", template_key=uuid4().hex,
                title_template="{title}", body_template="{body}",
            )
            session.add_all([
                channel, template,
                UserSecret(user_id=owner, name=credential_ref, ciphertext="private-ciphertext-sentinel"),
            ])
            await session.flush()
            job = NotificationJob(
                user_id=owner, channel_config_id=channel.id, template_id=template.id, purpose="digest",
                status="sent", idempotency_key=uuid4().hex, attempt_count=2, max_attempts=3, sent_at=sent_at,
                rendered_title="private-learnermessage-sentinel",
            )
            session.add(job)
            await session.flush()
            delivery = NotificationDelivery(
                user_id=owner, job_id=job.id, status="sent", attempt_no=2, duration_ms=42,
                attempted_at=sent_at, provider_message_id="private-provider-message-sentinel",
                request_metadata={"password": "private-delivery-request-sentinel"},
                response_metadata={
                    "provider_accepted": True, "final_delivery": "unconfirmed",
                    "unstructured_response": "private-provider-response-sentinel",
                },
            )
            session.add(delivery)
            await session.flush()
            return channel.id, job.id, delivery.id, credential_ref

    async def test_admin_only_and_paginated_sources_are_owned_and_redacted(self):
        owner = self.users[0].id
        source_id, ref = await self.seed_source(owner)
        second_id, _ = await self.seed_source(owner)
        await self.seed_source(self.users[1].id)
        finished = utcnow()
        async with self.owner.transaction() as session:
            session.add(UserSecret(user_id=owner, name=ref, ciphertext="private-notion-token-sentinel"))
            session.add(
                SyncRun(
                    user_id=owner, data_source_id=source_id, trigger_type="scheduled",
                    status="partial", idempotency_key=uuid4().hex, attempt=1,
                    started_at=finished - timedelta(seconds=2), finished_at=finished,
                    items_seen=3, items_imported=2, items_failed=1, error_code="VALIDATION_ERROR",
                    error_message="private-notion-error-sentinel",
                )
            )
        query = f"/admin/sources?user_id={owner}&limit=1"
        anonymous = await self.client.get("/api/v1" + query)
        self.assertEqual(anonymous.status_code, 401, anonymous.text)
        for path in (query, f"/admin/sources/{source_id}/runs", "/admin/notification-channels",
                     "/admin/notification-deliveries", "/admin/jobs"):
            with self.subTest(path=path):
                denied = await self.request("GET", path, user=0)
                self.assertEqual(denied.status_code, 403, denied.text)
        first = await self.request("GET", query, user=2)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertTrue(first.json()["has_more"])
        second = await self.request(
            "GET", query + f"&cursor={first.json()['next_cursor']}", user=2
        )
        self.assertEqual(second.status_code, 200, second.text)
        self.assertFalse(second.json()["has_more"])
        by_id = {item["id"]: item for response in (first, second) for item in response.json()["items"]}
        self.assertEqual(set(by_id), {str(source_id), str(second_id)})
        source = by_id[str(source_id)]
        self.assertEqual(source["user_id"], str(owner))
        self.assertEqual((source["last_status"], source["items_imported"], source["items_failed"]), ("partial", 2, 1))
        self.assertIsNotNone(source["last_synced_at"])
        self.assertTrue(source["credential_configured"])
        runs = await self.request("GET", f"/admin/sources/{source_id}/runs", user=2)
        self.assertEqual(runs.status_code, 200, runs.text)
        self.assertEqual(runs.json()["items"][0]["error_code"], "VALIDATION_ERROR")
        for response in (first, second, runs):
            self.assertNotIn("private-", response.text)
            self.assertNotIn(ref, response.text)
        missing = await self.request("GET", f"/admin/sources/{uuid4()}/runs", user=2)
        self.assertEqual(missing.status_code, 404, missing.text)

    async def test_queue_only_reuses_existing_pending_run_and_audits_target(self):
        owner = self.users[0].id
        source_id, _ = await self.seed_source(owner)
        disabled_id, _ = await self.seed_source(owner, enabled=False)
        path = f"/admin/sources/{source_id}/sync"
        key = str(uuid4())
        denied = await self.request("POST", path, user=0, key=key)
        self.assertEqual(denied.status_code, 403, denied.text)
        self.assertFalse(self.app.state.settings.background_tasks_enabled)
        with patch("app.services.notion.RuntimeNotionClient") as transport:
            queued = await self.request("POST", path, key=key, user=2)
            replayed = await self.request("POST", path, key=key, user=2)
            overlapping = await self.request("POST", path, key=str(uuid4()), user=2)
            disabled = await self.request("POST", f"/admin/sources/{disabled_id}/sync", key=str(uuid4()), user=2)
            transport.assert_not_called()
        self.assertEqual(disabled.status_code, 400, disabled.text)
        self.assertEqual(disabled.json()["error"]["code"], "INVALID_STATE")
        self.assertEqual(queued.status_code, 202, queued.text)
        self.assertEqual(replayed.json()["id"], queued.json()["id"])
        self.assertEqual(overlapping.json()["id"], queued.json()["id"])
        self.assertEqual((queued.json()["status"], queued.json()["attempt"]), ("pending", 0))
        async with self.owner.transaction() as session:
            rows = await session.scalar(select(func.count()).select_from(SyncRun).where(
                SyncRun.user_id == owner, SyncRun.data_source_id == source_id
            ))
            self.assertEqual(rows, 1)
            audit_rows = await session.scalars(select(AuditEvent).where(
                AuditEvent.action == "admin_source_sync_queued", AuditEvent.resource == str(source_id)
            ))
            self.assertEqual(
                {(row.actor_id, row.target_user_id) for row in audit_rows}, {(self.users[2].id, owner)}
            )

    async def test_delivery_attempts_and_job_types_report_real_scope_and_hide_payloads(self):
        owner = self.users[0].id
        channel_id, job_id, delivery_id, ref = await self.seed_delivery(owner)
        await self.seed_delivery(self.users[1].id)
        source_id, _ = await self.seed_source(owner)
        chapter = await self.chapter(status="completed")
        await self.request("POST", f"/admin/sources/{source_id}/sync", key=str(uuid4()), user=2)
        async with self.owner.transaction() as session:
            session.add(DailyReviewBatch(
                user_id=owner, local_date=utcnow().date(), timezone="UTC", daily_limit=20,
                status="ready", idempotency_key=uuid4().hex,
            ))
        channel_result = await self.request("GET", f"/admin/notification-channels?user_id={owner}", user=2)
        delivery_result = await self.request(
            "GET", f"/admin/notification-deliveries?channel_id={channel_id}&status=sent", user=2
        )
        job_result = await self.request("GET", f"/admin/jobs?user_id={owner}", user=2)
        for response in (channel_result, delivery_result, job_result):
            self.assertEqual(response.status_code, 200, response.text)
            self.assertNotIn("private-", response.text)
            self.assertNotIn(ref, response.text)
        [channel] = channel_result.json()["items"]
        self.assertEqual(channel["id"], str(channel_id))
        self.assertTrue(channel["credential_configured"])
        self.assertEqual(channel["last_status"], "sent")
        [delivery] = delivery_result.json()["items"]
        self.assertEqual(delivery["id"], str(delivery_id))
        self.assertEqual(delivery["attempt_no"], 2)
        self.assertEqual(delivery["duration_ms"], 42)
        self.assertTrue(delivery["provider_accepted"])
        self.assertEqual(delivery["final_delivery"], "unconfirmed")
        by_kind = {row["kind"]: row for row in job_result.json()["items"]}
        self.assertEqual(set(by_kind), {"notion", "chapter", "review_batch", "notification"})
        self.assertEqual(by_kind["chapter"]["name"], chapter["title"])
        self.assertEqual(by_kind["notification"]["id"], str(job_id))
        filtered = await self.request(
            "GET", f"/admin/jobs?user_id={owner}&kind=notification&status=sent", user=2
        )
        self.assertEqual(filtered.status_code, 200, filtered.text)
        self.assertEqual(filtered.json()["items"], [by_kind["notification"]])
