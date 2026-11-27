"""Real PostgreSQL website configuration, credential and email regressions."""

import asyncio
import os
import ssl
import sys
import unittest
from datetime import timedelta
from unittest.mock import patch
from uuid import UUID, uuid4

import test_core_api as core
import test_notion_runtime as notion_tests
from sqlalchemy import func, select

from app.contracts.models import DailyGenerateRequest
from app.models import (
    ChapterJob,
    KnowledgePoint,
    NotificationDelivery,
    NotificationJob,
    User,
    UserSecret,
    WorkspaceProfile,
)
from app.notifications.transports import SmtpEnvelope, SmtplibTransport, SmtpResult, SmtpTransport
from app.services import learning, mail, workspace
from app.services.common import utcnow
from app.services.credentials import user_settings


class FakeSmtp(SmtpTransport):
    def __init__(self, ok=True):
        self.envelopes = []
        self.ok = ok

    def send(self, envelope):
        self.envelopes.append(envelope)
        return SmtpResult(
            self.ok,
            provider_message_id="fixture-message" if self.ok else None,
            error_message=None if self.ok else "private-fixture-password",
            retryable=True,
        )


@unittest.skipUnless(os.environ.get("TEST_DATABASE_URL"), "TEST_DATABASE_URL required")
class GuidedSetup(unittest.IsolatedAsyncioTestCase):
    sequence = 180
    asyncSetUp = core.CoreAPI.asyncSetUp
    asyncTearDown = core.CoreAPI.asyncTearDown
    login = core.CoreAPI.login
    request = core.CoreAPI.request
    subject = core.CoreAPI.subject
    chapter = core.CoreAPI.chapter
    point = core.CoreAPI.point
    due_task = core.CoreAPI.due_task

    def _setupAsyncioRunner(self):
        if sys.platform == "win32":
            self._asyncioRunner = asyncio.Runner(loop_factory=asyncio.SelectorEventLoop)
        else:
            super()._setupAsyncioRunner()

    async def email(self):
        data = (await self.request("GET", "/workspace/settings")).json()
        response = await self.request(
            "PUT",
            "/workspace/email",
            version=data["profile"]["version"],
            body={
                "provider": "qq",
                "username": "fixture@example.com",
                "password": "private-fixture-password",
                "enabled": True,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def test_public_registration_uses_http_only_revocable_cookie(self):
        email = uuid4().hex + "@example.com"
        response = await self.client.post(
            "/api/v1/auth/register",
            json={"email": email, "display_name": "新用户", "password": "New-user-password-123"},
            headers={"Origin": "http://test"},
        )
        self.assertEqual(response.status_code, 201, response.text)
        cookie = response.headers["set-cookie"].lower()
        self.assertIn("httponly", cookie)
        self.assertIn("samesite=lax", cookie)
        me = await self.client.get("/api/v1/me")
        self.assertEqual(me.json()["role"], "user")
        data = await self.client.get("/api/v1/workspace/settings")
        self.assertIsNone(data.json()["profile"]["onboarding_completed_at"])
        self.assertEqual((await self.client.post("/api/v1/auth/logout")).status_code, 403)
        self.assertEqual(
            (
                await self.client.post("/api/v1/auth/logout", headers={"X-Memory-Client": "web"})
            ).status_code,
            204,
        )
        self.assertEqual((await self.client.get("/api/v1/me")).status_code, 401)

    async def test_registration_rejects_role_escalation_weak_password_and_cross_origin(self):
        body = {"email": uuid4().hex + "@example.com", "display_name": "test", "password": "short"}
        response = await self.client.post("/api/v1/auth/register", json=body)
        self.assertEqual(response.status_code, 400)
        self.assertNotIn('"short"', response.text)
        body["password"] = "Long-safe-password"
        body["role"] = "admin"
        self.assertEqual(
            (await self.client.post("/api/v1/auth/register", json=body)).status_code, 400
        )
        del body["role"]
        self.assertEqual(
            (
                await self.client.post(
                    "/api/v1/auth/register",
                    json=body,
                    headers={"Origin": "https://untrusted.example"},
                )
            ).status_code,
            403,
        )

    async def test_configuration_persists_with_versions_and_user_scope(self):
        data = (await self.request("GET", "/workspace/settings")).json()
        profile = {
            "recipient_email": "receiver@example.com",
            "reminder_time": "08:30",
            "timezone": "Asia/Shanghai",
            "onboarding_step": 2,
        }
        response = await self.request(
            "PUT", "/workspace/profile", version=data["profile"]["version"], body=profile
        )
        self.assertEqual(response.status_code, 200, response.text)
        response = await self.request(
            "PUT", "/workspace/profile", version=data["profile"]["version"], body=profile
        )
        self.assertEqual(response.status_code, 409)
        other = (await self.request("GET", "/workspace/settings", user=1)).json()
        self.assertEqual(other["profile"]["recipient_email"], self.users[1].email)
        self.assertEqual(
            (await self.request("POST", "/workspace/onboarding/complete")).status_code, 200
        )
        data = (await self.request("GET", "/workspace/settings")).json()
        self.assertEqual(data["profile"]["reminder_time"], "08:30")
        self.assertIsNotNone(data["profile"]["onboarding_completed_at"])

    async def test_notion_secret_is_encrypted_bound_to_owner_and_used_for_discovery(self):
        token = "notion-private-fixture-token"
        response = await self.request("PUT", "/workspace/notion/token", body={"token": token})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn(token, response.text)
        data = (await self.request("GET", "/workspace/settings")).json()
        self.assertTrue(data["notion_configured"])
        async with self.owner.transaction() as session:
            secret = await session.scalar(
                select(UserSecret).where(UserSecret.user_id == self.users[0].id)
            )
            self.assertNotIn(token, secret.ciphertext)
        settings = await user_settings(self.app.state.database, self.settings, self.users[0].id)
        reference = workspace.reference(self.users[0].id, "NOTION_TOKEN")
        self.assertEqual(settings.get(reference), token)
        other = await user_settings(self.app.state.database, self.settings, self.users[1].id)
        self.assertFalse(other.get(reference))
        transport = notion_tests.FixtureTransport(
            callback=lambda *_: {
                "results": [
                    {
                        "id": str(uuid4()),
                        "title": [{"plain_text": "我的课程"}],
                        "properties": {
                            "学习状态": {
                                "type": "status",
                                "status": {"options": [{"name": "已完成"}]},
                            }
                        },
                    }
                ]
            }
        )
        result = await workspace.discover_sources(
            self.app.state.database, self.settings, self.users[0].id, transport=transport
        )
        self.assertEqual(result["items"][0]["name"], "我的课程")
        self.assertEqual(result["items"][0]["properties"][0]["options"], ["已完成"])

    async def test_email_save_test_job_retry_and_delivery_are_persistent(self):
        data = await self.email()
        self.assertTrue(data["smtp_configured"])
        self.assertNotIn("private-fixture-password", str(data))
        response = await self.request("POST", "/workspace/email/test", key="test-1")
        self.assertEqual(response.status_code, 202, response.text)
        job_id = UUID(response.json()["id"])
        repeat = await self.request("POST", "/workspace/email/test", key="test-1")
        self.assertEqual(repeat.json()["id"], str(job_id))
        transport = FakeSmtp(False)
        result = await mail.process_mail(
            self.app.state.database, self.settings, job_id, transport=transport
        )
        self.assertEqual(result["status"], "failed")
        async with self.owner.transaction() as session:
            job = await session.get(NotificationJob, job_id)
            self.assertEqual(job.status, "pending")
            self.assertNotIn("private-fixture-password", job.last_error_message)
            job.next_attempt_at = utcnow() - timedelta(seconds=1)
        transport.ok = True
        result = await mail.process_mail(
            self.app.state.database, self.settings, job_id, transport=transport
        )
        self.assertEqual(result["status"], "sent")
        self.assertTrue(transport.envelopes[0].use_ssl)
        self.assertFalse(transport.envelopes[0].use_tls)
        self.assertEqual(transport.envelopes[0].password, "private-fixture-password")
        async with self.owner.transaction() as session:
            latest_delivery = await session.scalar(
                select(NotificationDelivery).where(
                    NotificationDelivery.job_id == job_id,
                    NotificationDelivery.attempt_no == 2,
                )
            )
            self.assertEqual(latest_delivery.response_metadata["provider_accepted"], True)
            self.assertEqual(latest_delivery.response_metadata["final_delivery"], "unconfirmed")
            self.assertEqual(
                await session.scalar(
                    select(func.count(NotificationDelivery.id)).where(
                        NotificationDelivery.job_id == job_id
                    )
                ),
                2,
            )

    async def test_admin_reads_existing_addresses_and_registration_stays_validated(self):
        legacy_email = uuid4().hex + "@example.test"
        async with self.owner.transaction() as session:
            user = await session.get(User, self.users[1].id)
            user.email = legacy_email
        result = await self.request("GET", "/admin/users?q=" + legacy_email, user=2)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["items"][0]["email"], legacy_email)
        result = await self.client.post(
            "/api/v1/auth/register",
            json={"email": legacy_email, "display_name": "test", "password": "Safe-password-123"},
        )
        self.assertEqual(result.status_code, 400)

    async def test_expired_email_lease_reconciles_history_and_enforces_retry_limit(self):
        await self.email()
        response = await self.request("POST", "/workspace/email/test", key="expired-mail")
        job_id = UUID(response.json()["id"])
        transport = FakeSmtp()
        for attempt, expected in ((1, "sent"), (3, "failed")):
            async with self.owner.transaction() as session:
                job = await session.get(NotificationJob, job_id)
                job.status, job.attempt_count = "processing", attempt
                job.sent_at = None
                job.locked_until = utcnow() - timedelta(seconds=1)
                session.add(
                    NotificationDelivery(
                        user_id=job.user_id,
                        job_id=job.id,
                        attempt_no=attempt,
                        status="sending",
                        attempted_at=utcnow() - timedelta(minutes=3),
                    )
                )
            result = await mail.process_mail(
                self.app.state.database, self.settings, job_id, transport=transport
            )
            self.assertEqual(result["status"], expected)
            async with self.owner.transaction() as session:
                previous = await session.scalar(
                    select(NotificationDelivery).where(
                        NotificationDelivery.job_id == job_id,
                        NotificationDelivery.attempt_no == attempt,
                    )
                )
                self.assertEqual(previous.status, "failed")
                self.assertEqual(previous.error_code, "DELIVERY_UNCERTAIN")
                job = await session.get(NotificationJob, job_id)
                self.assertIsNone(job.locked_until)
                self.assertEqual(job.attempt_count, attempt + 1 if attempt == 1 else 3)
        self.assertEqual(len(transport.envelopes), 1)

    async def test_digest_contains_actual_content_explanation_source_and_review_link(self):
        await self.email()
        chapter = await self.chapter(status="completed")
        point = await self.point(chapter=chapter, active=True)
        await self.request(
            "POST",
            f"/knowledge-points/{point['id']}/review-items",
            key=str(uuid4()),
            body={
                "question_type": "qa",
                "question": "主动回忆问题",
                "answer": "答案正文",
                "explanation": "真实解析",
            },
        )
        from app.models import ScheduleState

        async with self.owner.transaction() as session:
            schedule = await session.scalar(
                select(ScheduleState).where(ScheduleState.knowledge_point_id == UUID(point["id"]))
            )
            schedule.due_at = utcnow() - timedelta(seconds=1)
            stored_point = await session.get(KnowledgePoint, UUID(point["id"]))
            stored_point.manual_revision = False  # emulates a point persisted by the AI worker
            chapter_job = await session.scalar(
                select(ChapterJob).where(ChapterJob.chapter_id == UUID(chapter["id"]))
            )
            chapter_job.status = "succeeded"
            chapter_job.result = {"analysis": {"knowledge_points": [{
                "knowledge_point_id": point["id"], "pitfalls": ["不要把状态甲和乙混为一谈"],
            }]}}
            profile = await session.scalar(
                select(WorkspaceProfile).where(WorkspaceProfile.user_id == self.users[0].id)
            )
            profile.reminder_time = "00:00"
        from zoneinfo import ZoneInfo

        await learning.generate_batch(
            self.app.state.database,
            self.settings,
            self.users[0].id,
            DailyGenerateRequest(
                local_date=utcnow().astimezone(ZoneInfo("Asia/Shanghai")).date(),
                timezone="Asia/Shanghai",
            ),
            str(uuid4()),
        )
        first = await mail.queue_digest(self.app.state.database, self.settings, self.users[0].id)
        second = await mail.queue_digest(self.app.state.database, self.settings, self.users[0].id)
        self.assertEqual(first["id"], second["id"])
        async with self.owner.transaction() as session:
            job = await session.get(NotificationJob, first["id"])
            for text in [
                "原文内容",
                "答案正文",
                "真实解析",
                "主动回忆问题",
                "https://www.notion.so/test-page",
                "/app?view=review",
                "已复习",
                "当前阶段",
                "下次复习（当前计划）",
                "+0800",
                "不要把状态甲和乙混为一谈",
            ]:
                self.assertIn(text, job.rendered_body)

    async def test_generated_batch_refreshes_when_new_knowledge_arrives_same_day(self):
        from zoneinfo import ZoneInfo

        request = DailyGenerateRequest(
            local_date=utcnow().astimezone(ZoneInfo("Asia/Shanghai")).date(),
            timezone="Asia/Shanghai",
        )
        empty = await learning.generate_batch(
            self.app.state.database, self.settings, self.users[0].id, request, "daily"
        )
        self.assertEqual(empty.tasks, [])
        await self.due_task()
        updated = await learning.generate_batch(
            self.app.state.database, self.settings, self.users[0].id, request, "daily", refresh=True
        )
        self.assertEqual(len(updated.tasks), 1)
        again = await learning.generate_batch(
            self.app.state.database, self.settings, self.users[0].id, request, "daily", refresh=True
        )
        self.assertEqual(len(again.tasks), 1)

    async def test_unapproved_custom_smtp_host_is_rejected(self):
        data = (await self.request("GET", "/workspace/settings")).json()
        result = await self.request(
            "PUT",
            "/workspace/email",
            version=data["profile"]["version"],
            body={
                "provider": "custom",
                "host": "127.0.0.1",
                "username": "fixture@example.com",
                "password": "fixture",
            },
        )
        self.assertEqual(result.status_code, 400)


class SmtpSecurity(unittest.TestCase):
    def test_smtp_ssl_uses_certificate_verification(self):
        envelope = SmtpEnvelope(
            host="smtp.qq.com",
            port=465,
            user="fixture@example.com",
            password="fixture",
            from_addr="fixture@example.com",
            to_addrs=["receiver@example.com"],
            subject="测试",
            body="内容",
            use_tls=False,
            use_ssl=True,
        )
        with patch("app.notifications.transports.smtplib.SMTP_SSL") as ssl_client:
            result = SmtplibTransport().send(envelope)
            self.assertTrue(result.ok)
            context = ssl_client.call_args.kwargs["context"]
            self.assertTrue(context.check_hostname)
            self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
