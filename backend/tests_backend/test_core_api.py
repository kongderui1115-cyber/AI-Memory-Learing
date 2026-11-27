"""Real PostgreSQL HTTP integration and tenant/security regressions."""

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import os
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.config import Settings
from app.contracts.core import UserCreate
from app.database import Database
from app.main import create_app
from app.models import (
    DailyReviewTask,
    KnowledgePoint,
    ReviewHistory,
    ScheduleState,
    User,
    UserSession,
)
from app.security import hash_password

PASSWORD = "Integration-passphrase-2026"
PASSWORD_HASH = hash_password(PASSWORD)
SECRET = "a1b2c3d4e5f6" * 8


@unittest.skipUnless(os.environ.get("TEST_DATABASE_URL"), "TEST_DATABASE_URL required")
class CoreAPI(unittest.IsolatedAsyncioTestCase):
    sequence = 0

    def _setupAsyncioRunner(self):
        if sys.platform == "win32":
            self._asyncioRunner = asyncio.Runner(loop_factory=asyncio.SelectorEventLoop)
        else:
            super()._setupAsyncioRunner()

    async def asyncSetUp(self):
        type(self).sequence += 1
        self.owner = Database(Settings(database_url=os.environ["TEST_DATABASE_URL"]))
        self.users = []
        async with self.owner.transaction() as session:
            for role in ("user", "user", "admin"):
                user = User(
                    id=uuid4(),
                    email=f"{uuid4()}@example.com",
                    display_name=role,
                    password_hash=PASSWORD_HASH,
                    role=role,
                )
                session.add(user)
                self.users.append(user)
        self.settings = Settings(
            database_url=os.environ.get("TEST_APP_DATABASE_URL", os.environ["TEST_DATABASE_URL"]),
            secret_key=SECRET,
            scheduler_strategy="ebbinghaus",
        )
        self.app = create_app(self.settings)
        self.lifespan = self.app.router.lifespan_context(self.app)
        await self.lifespan.__aenter__()
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(
                app=self.app,
                raise_app_exceptions=False,
                client=(f"198.51.100.{type(self).sequence}", 10000),
            ),
            base_url="http://test",
        )
        self.tokens = {}

    async def asyncTearDown(self):
        await self.client.aclose()
        await self.lifespan.__aexit__(None, None, None)
        await self.owner.close()

    async def login(self, user=0, password=PASSWORD):
        return await self.client.post(
            "/api/v1/auth/token", json={"email": self.users[user].email, "password": password}
        )

    async def request(self, method, path, *, user=0, body=None, key=None, version=None):
        if user not in self.tokens:
            response = await self.login(user)
            self.assertEqual(response.status_code, 200, response.text)
            self.tokens[user] = response.json()["access_token"]
        headers = {"Authorization": "Bearer " + self.tokens[user]}
        if key is not None:
            headers["Idempotency-Key"] = key
        if version is not None:
            headers["If-Match"] = f'"{version}"'
        return await self.client.request(method, "/api/v1" + path, json=body, headers=headers)

    async def subject(self, user=0, key=None):
        response = await self.request(
            "POST",
            "/subjects",
            user=user,
            key=key or str(uuid4()),
            body={"name": "通用学科", "slug": "subject-" + uuid4().hex[:12]},
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    async def chapter(self, status="in_progress"):
        subject = await self.subject()
        response = await self.request(
            "POST",
            "/chapters",
            key=str(uuid4()),
            body={
                "subject_id": subject["id"],
                "title": "分次学习的章节",
                "status": status,
                "content": "这是真实测试写入的章节正文",
                "source_url": "https://www.notion.so/test-page",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    async def point(self, chapter=None, active=False):
        subject_id = chapter["subject_id"] if chapter else (await self.subject())["id"]
        body = {
            "subject_id": subject_id,
            "title": "知识点",
            "body": "原文内容",
            "summary": "摘要",
            "difficulty": 2,
            "status": "active" if active else "draft",
        }
        if chapter:
            body["chapter_id"] = chapter["id"]
        response = await self.request("POST", "/knowledge-points", body=body, key=str(uuid4()))
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    async def due_task(self):
        point = await self.point(active=True)
        item = await self.request(
            "POST",
            f"/knowledge-points/{point['id']}/review-items",
            key=str(uuid4()),
            body={
                "question_type": "qa",
                "question": "问题",
                "answer": "答案",
                "explanation": "解析",
            },
        )
        self.assertEqual(item.status_code, 201, item.text)
        async with self.owner.transaction() as session:
            state = await session.scalar(
                select(ScheduleState).where(ScheduleState.knowledge_point_id == point["id"])
            )
            state.due_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        response = await self.request(
            "POST",
            "/review-batches/generate",
            key=str(uuid4()),
            body={
                "local_date": datetime.now(timezone.utc)
                .astimezone(ZoneInfo("Asia/Shanghai"))
                .date()
                .isoformat(),
                "timezone": "Asia/Shanghai",
                "daily_limit": 30,
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return point, response.json()["tasks"][0], response.json()

    @staticmethod
    def completion():
        return {
            "rating": "good",
            "duration_seconds": 20,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
        }

    async def test_health_real_database_and_invalid_request_id(self):
        result = await self.client.get("/api/v1/health/ready", headers={"X-Request-ID": "invalid"})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["checks"]["database"]["status"], "ok")
        self.assertEqual(len(result.headers["X-Request-ID"]), 36)

    async def test_login_me_logout_revokes_token(self):
        me = await self.request("GET", "/me")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["id"], str(self.users[0].id))
        self.assertNotIn("password_hash", me.text)
        self.assertEqual((await self.request("POST", "/auth/logout")).status_code, 204)
        self.assertEqual((await self.request("GET", "/me")).status_code, 401)

    async def test_missing_and_tampered_tokens(self):
        self.assertEqual((await self.client.get("/api/v1/me")).status_code, 401)
        self.assertEqual(
            (
                await self.client.get(
                    "/api/v1/me", headers={"Authorization": "Bearer invalid.jwt.token"}
                )
            ).status_code,
            401,
        )

    async def test_six_failures_lock_valid_password_and_persist(self):
        for _ in range(5):
            self.assertEqual((await self.login(password="wrong-password-123")).status_code, 401)
        response = await self.login(password="wrong-password-123")
        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response.headers)
        self.assertEqual((await self.login()).status_code, 429)

    async def test_lock_expiry_allows_login(self):
        for _ in range(6):
            await self.login(password="wrong-password-123")
        from app.models import LoginThrottle

        async with self.owner.transaction() as session:
            for row in await session.scalars(
                select(LoginThrottle).where(LoginThrottle.key.like("account:%"))
            ):
                # Change only this test account's digest.
                import hashlib

                if (
                    row.key
                    == "account:"
                    + hashlib.sha256(self.users[0].email.casefold().encode()).hexdigest()
                ):
                    row.locked_until = datetime.now(timezone.utc) - timedelta(seconds=1)
                    row.window_started_at = datetime.now(timezone.utc) - timedelta(minutes=20)
        self.assertEqual((await self.login()).status_code, 200)

    async def test_user_cannot_access_admin_and_event_is_audited(self):
        self.assertEqual((await self.request("GET", "/admin/users")).status_code, 403)
        response = await self.request(
            "GET", f"/admin/audit-events?user_id={self.users[0].id}", user=2
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(item["outcome"] == "forbidden" for item in response.json()["items"]))

    async def test_admin_user_creation_idempotency_and_password_policy(self):
        body = {
            "email": f"{uuid4()}@example.com",
            "display_name": "新用户",
            "password": "1234567890",
        }
        key = str(uuid4())
        first = await self.request("POST", "/admin/users", user=2, body=body, key=key)
        second = await self.request("POST", "/admin/users", user=2, body=body, key=key)
        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(first.json()["id"], second.json()["id"])
        self.assertNotIn("password", first.text)
        changed = await self.request(
            "POST", "/admin/users", user=2, body={**body, "password": "1234567891"}, key=key
        )
        self.assertEqual(changed.status_code, 409)
        bad = await self.request(
            "POST", "/admin/users", user=2, body={**body, "password": "123456789"}, key=str(uuid4())
        )
        self.assertEqual(bad.status_code, 400)

    async def test_disable_user_revokes_existing_session(self):
        await self.request("GET", "/me")
        result = await self.request(
            "PATCH",
            f"/admin/users/{self.users[0].id}",
            user=2,
            version=1,
            body={"is_active": False},
        )
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual((await self.request("GET", "/me")).status_code, 401)

    async def test_password_change_revokes_all_sessions(self):
        result = await self.request(
            "POST",
            "/auth/password",
            body={"current_password": PASSWORD, "new_password": "Another-passphrase-2026"},
        )
        self.assertEqual(result.status_code, 204, result.text)
        self.assertEqual((await self.request("GET", "/me")).status_code, 401)
        self.assertEqual((await self.login(password="Another-passphrase-2026")).status_code, 200)

    async def test_subject_ownership_version_and_hierarchy(self):
        subject = await self.subject()
        self.assertEqual(
            (await self.request("GET", f"/subjects/{subject['id']}", user=1)).status_code, 404
        )
        result = await self.request(
            "PATCH", f"/subjects/{subject['id']}", body={"name": "新名称"}, version=1
        )
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(
            (
                await self.request(
                    "PATCH", f"/subjects/{subject['id']}", body={"name": "旧覆盖"}, version=1
                )
            ).status_code,
            409,
        )
        self.assertEqual(
            (
                await self.request(
                    "PATCH",
                    f"/subjects/{subject['id']}",
                    body={"parent_id": subject["id"]},
                    version=2,
                )
            ).status_code,
            400,
        )

    async def test_concurrent_subject_idempotency(self):
        await self.request("GET", "/me")
        key = str(uuid4())
        body = {"name": "并发学科", "slug": "concurrent-" + uuid4().hex[:10]}
        results = await asyncio.gather(
            *(self.request("POST", "/subjects", body=body, key=key) for _ in range(2))
        )
        self.assertEqual([row.status_code for row in results], [201, 201])
        self.assertEqual(results[0].json()["id"], results[1].json()["id"])

    async def test_keyset_pagination_and_cursor_validation(self):
        for _ in range(3):
            await self.subject()
        first = (await self.request("GET", "/subjects?limit=1")).json()
        self.assertTrue(first["has_more"])
        second = (
            await self.request("GET", "/subjects?limit=1&cursor=" + first["next_cursor"])
        ).json()
        self.assertNotEqual(first["items"][0]["id"], second["items"][0]["id"])
        self.assertEqual((await self.request("GET", "/subjects?cursor=invalid")).status_code, 400)

    async def test_chapter_learning_sessions_and_completion_queue(self):
        chapter = await self.chapter()
        end = datetime.now(timezone.utc) - timedelta(seconds=2)
        body = {
            "started_at": (end - timedelta(minutes=30)).isoformat(),
            "ended_at": end.isoformat(),
        }
        key = str(uuid4())
        response = await self.request(
            "POST", f"/chapters/{chapter['id']}/study-sessions", body=body, key=key
        )
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["duration_seconds"], 1800)
        replayed = await self.request(
            "POST", f"/chapters/{chapter['id']}/study-sessions", body=body, key=key
        )
        self.assertEqual(response.json()["id"], replayed.json()["id"])
        before = await self.request("GET", f"/chapters/{chapter['id']}/jobs")
        self.assertEqual(before.json()["items"], [])
        for _ in range(2):
            self.assertEqual(
                (
                    await self.request(
                        "POST", f"/chapters/{chapter['id']}/complete", key=str(uuid4())
                    )
                ).status_code,
                200,
            )
        after = await self.request("GET", f"/chapters/{chapter['id']}/jobs")
        self.assertEqual(len(after.json()["items"]), 1)

    async def test_unfinished_chapter_prevents_cards_and_schedule(self):
        chapter = await self.chapter()
        point = await self.point(chapter)
        blocked = await self.request(
            "POST", f"/knowledge-points/{point['id']}/activate", key=str(uuid4())
        )
        self.assertEqual(blocked.status_code, 400, blocked.text)
        blocked = await self.request(
            "POST",
            f"/knowledge-points/{point['id']}/review-items",
            key=str(uuid4()),
            body={"question_type": "qa", "question": "问题", "answer": "答案"},
        )
        self.assertEqual(blocked.status_code, 400, blocked.text)

    async def test_knowledge_foreign_subject_and_source(self):
        other = await self.subject(user=1)
        bad = await self.request(
            "POST",
            "/knowledge-points",
            key=str(uuid4()),
            body={
                "subject_id": other["id"],
                "title": "越权",
                "body": "正文",
                "summary": "摘要",
                "difficulty": 1,
            },
        )
        self.assertEqual(bad.status_code, 404, bad.text)
        chapter = await self.chapter("completed")
        point = await self.point(chapter, active=True)
        self.assertEqual(point["source_url"], chapter["source_url"])
        self.assertEqual(
            (await self.request("GET", f"/knowledge-points/{point['id']}", user=1)).status_code, 404
        )
        admin = await self.request(
            "GET", f"/admin/users/{self.users[0].id}/knowledge-points", user=2
        )
        self.assertEqual(len(admin.json()["items"]), 1)

    async def test_database_enforces_cross_user_foreign_key(self):
        subject = await self.subject()
        with self.assertRaises(IntegrityError):
            async with self.owner.transaction() as session:
                session.add(
                    KnowledgePoint(
                        user_id=self.users[1].id,
                        subject_id=subject["id"],
                        title="越权",
                        body="正文",
                        summary="摘要",
                        difficulty=1,
                        canonical_hash=uuid4().hex * 2,
                    )
                )

    async def test_daily_task_content_and_idempotent_completion(self):
        point, task, batch = await self.due_task()
        content = await self.request("GET", f"/review-tasks/{task['id']}/content")
        self.assertEqual(content.status_code, 200, content.text)
        self.assertEqual(content.json()["review_item"]["explanation"], "解析")
        body, key = self.completion(), str(uuid4())
        responses = await asyncio.gather(
            *(
                self.request("POST", f"/review-tasks/{task['id']}/complete", body=body, key=key)
                for _ in range(2)
            )
        )
        self.assertEqual(
            [row.status_code for row in responses], [200, 200], [row.text for row in responses]
        )
        self.assertEqual(responses[0].json()["history"]["id"], responses[1].json()["history"]["id"])
        self.assertEqual(responses[0].json()["schedule"]["review_count"], 1)
        conflict = await self.request(
            "POST",
            f"/review-tasks/{task['id']}/complete",
            body={**body, "duration_seconds": 21},
            key=key,
        )
        self.assertEqual(conflict.status_code, 409)
        batch_read = await self.request("GET", f"/review-batches/{batch['id']}")
        self.assertEqual(batch_read.json()["status"], "completed")

    async def test_review_history_is_user_scoped_and_statistics_persist(self):
        point, task, batch = await self.due_task()
        result = await self.request(
            "POST", f"/review-tasks/{task['id']}/complete", body=self.completion(), key=str(uuid4())
        )
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual((await self.request("GET", "/review-history", user=1)).json()["items"], [])
        result = await self.request(
            "GET",
            f"/statistics/overview?from_date={batch['local_date']}&to_date={batch['local_date']}",
        )
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["completed_tasks"], 1)
        self.assertEqual(result.json()["completion_rate"], 1)

    async def test_completion_commit_failure_rolls_back_all_records(self):
        point, task, batch = await self.due_task()
        name = "integration_" + uuid4().hex
        async with self.owner.transaction() as session:
            await session.execute(
                text(
                    f"CREATE FUNCTION {name}() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.user_id = '{self.users[0].id}'::uuid THEN RAISE EXCEPTION 'integration rollback probe'; END IF; RETURN NEW; END $$"
                )
            )
            await session.execute(
                text(
                    f"CREATE CONSTRAINT TRIGGER {name} AFTER INSERT ON review_history DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION {name}()"
                )
            )
        try:
            result = await self.request(
                "POST",
                f"/review-tasks/{task['id']}/complete",
                body=self.completion(),
                key=str(uuid4()),
            )
            self.assertEqual(result.status_code, 500, result.text)
            self.assertNotIn("integration rollback probe", result.text)
            async with self.owner.transaction() as session:
                row = await session.get(DailyReviewTask, task["id"])
                state = await session.scalar(
                    select(ScheduleState).where(ScheduleState.knowledge_point_id == point["id"])
                )
                count = await session.scalar(
                    select(func.count())
                    .select_from(ReviewHistory)
                    .where(ReviewHistory.user_id == self.users[0].id)
                )
                self.assertEqual(
                    (row.status, state.review_count, state.state_version, count),
                    ("pending", 0, 1, 0),
                )
        finally:
            async with self.owner.transaction() as session:
                await session.execute(text(f"DROP TRIGGER {name} ON review_history"))
                await session.execute(text(f"DROP FUNCTION {name}()"))

    async def test_online_heartbeat_logout_and_time_filters(self):
        await self.request("GET", "/me")
        async with self.owner.transaction() as session:
            row = await session.scalar(
                select(UserSession).where(UserSession.user_id == self.users[0].id)
            )
            row.last_seen_at = datetime.now(timezone.utc) - timedelta(minutes=6)
        path = f"/admin/sessions?user_id={self.users[0].id}"
        self.assertEqual(
            len((await self.request("GET", path + "&online=false", user=2)).json()["items"]), 1
        )
        self.assertEqual((await self.request("POST", "/auth/heartbeat")).status_code, 200)
        self.assertEqual(
            len((await self.request("GET", path + "&online=true", user=2)).json()["items"]), 1
        )
        self.assertEqual(
            (await self.request("GET", path + "&from=2026-01-01T00:00:00", user=2)).status_code, 400
        )
        self.assertEqual((await self.request("POST", "/auth/logout")).status_code, 204)
        self.assertEqual(
            (await self.request("GET", path + "&online=true", user=2)).json()["items"], []
        )

    async def test_security_log_has_no_password_or_token_digest(self):
        await self.request("GET", "/me")
        response = await self.request("GET", "/admin/audit-events", user=2)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn(PASSWORD, response.text)
        self.assertNotIn("password_hash", response.text)
        self.assertNotIn("token_digest", response.text)

    async def test_official_fsrs_normal_http_flow_and_strategy_switch(self):
        self.settings = replace(self.settings, scheduler_strategy="fsrs")
        self.app.state.settings = self.settings
        point = await self.point(active=True)
        card = await self.request(
            "POST",
            f"/knowledge-points/{point['id']}/review-items",
            key=str(uuid4()),
            body={"question_type": "qa", "question": "问题", "answer": "答案"},
        )
        self.assertEqual(card.status_code, 201, card.text)
        from zoneinfo import ZoneInfo

        body = {
            "local_date": datetime.now(timezone.utc)
            .astimezone(ZoneInfo("Asia/Shanghai"))
            .date()
            .isoformat(),
            "timezone": "Asia/Shanghai",
        }
        batch = await self.request("POST", "/review-batches/generate", body=body, key=str(uuid4()))
        self.assertEqual(batch.status_code, 201, batch.text)
        task = batch.json()["tasks"][0]
        result = await self.request(
            "POST", f"/review-tasks/{task['id']}/complete", body=self.completion(), key=str(uuid4())
        )
        self.assertEqual(result.status_code, 200, result.text)
        state = result.json()["schedule"]
        self.assertEqual(state["algorithm_version"], "fsrs-6-sdk-6.3.3")
        changed = await self.request(
            "PUT",
            f"/knowledge-points/{point['id']}/schedule/strategy",
            version=state["version"],
            body={"strategy": "ebbinghaus", "parameters": {"intervals_days": [1, 3, 7]}},
        )
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(changed.json()["review_count"], 1)

    async def test_application_role_cannot_rewrite_audit(self):
        if not os.environ.get("TEST_APP_DATABASE_URL"):
            self.skipTest("Restricted application role required")
        await self.request("GET", "/me")
        with self.assertRaises(DBAPIError):
            async with self.app.state.database.transaction() as session:
                await session.execute(
                    text("UPDATE audit_events SET outcome='tampered' WHERE actor_id=:id"),
                    {"id": self.users[0].id},
                )

    async def test_invalid_batch_timezone_returns_validation_error(self):
        result = await self.request(
            "POST",
            "/review-batches/generate",
            key=str(uuid4()),
            body={"local_date": "2026-11-16", "timezone": "Invalid/Timezone"},
        )
        self.assertEqual(result.status_code, 400, result.text)

    async def test_legacy_authentication_creates_a_revocable_session(self):
        from app.services.auth import authenticate

        token = await authenticate(
            self.app.state.database, self.settings, self.users[0].email, PASSWORD
        )
        headers = {"Authorization": "Bearer " + token}
        self.assertEqual((await self.client.get("/api/v1/me", headers=headers)).status_code, 200)
        self.assertEqual(
            (await self.client.post("/api/v1/auth/logout", headers=headers)).status_code, 204
        )
        self.assertEqual((await self.client.get("/api/v1/me", headers=headers)).status_code, 401)

    async def test_skip_reason_is_persisted_and_payload_replay_is_checked(self):
        point, task, batch = await self.due_task()
        key = str(uuid4())
        result = await self.request(
            "POST",
            f"/review-tasks/{task['id']}/skip",
            key=key,
            body={"reason": "今天先完成其他章节"},
        )
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["skip_reason"], "今天先完成其他章节")
        changed = await self.request(
            "POST", f"/review-tasks/{task['id']}/skip", key=key, body={"reason": "不同原因"}
        )
        self.assertEqual(changed.status_code, 409, changed.text)
        saved = await self.request("GET", f"/review-tasks/{task['id']}")
        self.assertEqual(saved.json()["status"], "skipped")
        state = await self.request("GET", f"/knowledge-points/{point['id']}/schedule")
        self.assertEqual(state.json()["review_count"], 0)

    async def test_defer_only_moves_one_point_and_replays_across_daylight_saving(self):
        point, task, _ = await self.due_task()
        other = await self.point(active=True)
        async with self.owner.transaction() as session:
            user = await session.get(User, self.users[0].id)
            user.timezone = "America/New_York"
            schedule = await session.scalar(
                select(ScheduleState).where(ScheduleState.knowledge_point_id == point["id"])
            )
            schedule.due_at = datetime(2026, 10, 31, tzinfo=timezone.utc)
        endpoint = f"/review-tasks/{task['id']}/defer"
        response = await self.request("POST", endpoint, user=1, key=str(uuid4()), body={"days": 2})
        self.assertEqual(response.status_code, 404, response.text)
        before = (await self.request("GET", f"/knowledge-points/{other['id']}/schedule")).json()
        key = str(uuid4())
        with patch("app.services.learning.utcnow", return_value=datetime(2026, 10, 31, 20, tzinfo=timezone.utc)):
            result = await self.request("POST", endpoint, body={"days": 2}, key=key)
        self.assertEqual(result.status_code, 200, result.text)
        replay = await self.request("POST", endpoint, body={"days": 2}, key=key)
        self.assertEqual(result.json(), replay.json())
        state = (await self.request("GET", f"/knowledge-points/{point['id']}/schedule")).json()
        self.assertEqual(datetime.fromisoformat(state["due_at"]), datetime(2026, 11, 2, 5, tzinfo=timezone.utc))
        self.assertEqual(state["review_count"], 0)
        self.assertIsNone(state["last_reviewed_at"])
        self.assertEqual((await self.request("GET", f"/knowledge-points/{other['id']}/schedule")).json(), before)
        histories = (await self.request("GET", "/review-history")).json()
        self.assertFalse(histories["items"])

    async def test_memory_preferences_and_processing_scope(self):
        current = (await self.request("GET", "/workspace/settings")).json()["profile"]
        saved = await self.request(
            "PUT", "/workspace/memory-preferences", version=current["version"],
            body={"strategy": "ebbinghaus", "intervals_days": [3, 10]},
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        point = await self.point(active=True)
        state = (await self.request("GET", f"/knowledge-points/{point['id']}/schedule")).json()
        self.assertEqual((state["strategy"], state["parameters"]["intervals_days"]), ("ebbinghaus", [3, 10]))
        created = await self.request("POST", "/chapters", key=str(uuid4()), body={
            "subject_id": point["subject_id"], "title": "Notion 任务验收",
            "content": "隔离库验收笔记", "status": "completed", "external_page_id": str(uuid4()),
        })
        self.assertEqual(created.status_code, 201, created.text)
        progress = await self.request("GET", "/workspace/processing")
        self.assertEqual(progress.status_code, 200, progress.text)
        self.assertEqual(len(progress.json()["notes"]), 1)
        self.assertEqual(progress.json()["notes"][0]["status"], "pending")
        self.assertNotIn("is_verified", progress.json())
        other = await self.request("GET", "/workspace/processing", user=1)
        self.assertEqual(other.status_code, 200, other.text)
        self.assertFalse(other.json()["notes"])

    async def test_persistence_and_session_after_application_restart(self):
        subject = await self.subject()
        new_app = create_app(self.settings)
        async with new_app.router.lifespan_context(new_app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=new_app), base_url="http://test"
            ) as client:
                result = await client.get(
                    f"/api/v1/subjects/{subject['id']}",
                    headers={"Authorization": "Bearer " + self.tokens[0]},
                )
                self.assertEqual(result.status_code, 200, result.text)
                self.assertEqual(result.json()["id"], subject["id"])

    async def test_online_filter_excludes_disabled_legacy_users(self):
        await self.request("GET", "/me")
        async with self.owner.transaction() as session:
            user = await session.get(User, self.users[0].id)
            user.is_active = False
        result = await self.request(
            "GET", f"/admin/sessions?online=true&user_id={self.users[0].id}", user=2
        )
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["items"], [])

    async def test_datetime_output_is_utc(self):
        chapter = await self.chapter()
        end = datetime.now(timezone(timedelta(hours=8))) - timedelta(seconds=2)
        body = {"started_at": (end - timedelta(minutes=2)).isoformat(), "ended_at": end.isoformat()}
        result = await self.request(
            "POST", f"/chapters/{chapter['id']}/study-sessions", body=body, key=str(uuid4())
        )
        self.assertEqual(result.status_code, 201, result.text)
        self.assertTrue(result.json()["started_at"].endswith("Z"))
        self.assertTrue(result.json()["created_at"].endswith("Z"))


class PasswordPolicy(unittest.TestCase):
    def test_new_account_requires_ten_characters(self):
        with self.assertRaises(ValueError):
            UserCreate(email="person@example.com", display_name="test", password="123456789")
