"""Administrator aggregates and learner parity against isolated PostgreSQL."""

import asyncio
import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4
from zoneinfo import ZoneInfo

from fsrs import Card, Scheduler
from sqlalchemy import func, select

import test_core_api as core

from app.domain import memory, scheduling
from app.models import AuditEvent, User
from app.services.admin_analytics import retention_sample


class RetentionForecast(unittest.TestCase):
    def test_replays_sdk_prediction_at_event_not_stored_probability(self):
        previous_time = datetime(2026, 11, 12, 12, tzinfo=timezone.utc)
        at = previous_time + timedelta(days=4, hours=2)
        initial = memory.initial_state("fsrs", previous_time)
        previous = memory.review(initial, "good", previous_time)
        snapshot = scheduling.to_dict(previous)
        snapshot["retrievability"] = 1.0
        card = Card.from_json(json.dumps(previous.last_calculation["card"]))
        scheduler = Scheduler.from_json(json.dumps(previous.parameters["scheduler"]))
        estimate = scheduler.get_card_retrievability(card, current_datetime=at)
        stage, actual, version = retention_sample(snapshot, at)
        self.assertEqual(stage, 3)
        self.assertEqual(version, memory.VERSION)
        self.assertLess(estimate, 1.0)
        self.assertAlmostEqual(actual, estimate)
        self.assertIsNone(retention_sample(scheduling.to_dict(initial), at))
        self.assertIsNone(retention_sample(snapshot, previous_time - timedelta(seconds=1)))
        snapshot["algorithm_version"] = "unrecognized"
        self.assertEqual(retention_sample(snapshot, at)[0:2], (3, None))
        snapshot.pop("due_at")
        self.assertEqual(retention_sample(snapshot, at), (3, None, ""))


@unittest.skipUnless(os.environ.get("TEST_DATABASE_URL"), "TEST_DATABASE_URL required")
class AdminAnalyticsAPI(unittest.IsolatedAsyncioTestCase):
    sequence = 390
    asyncSetUp = core.CoreAPI.asyncSetUp
    asyncTearDown = core.CoreAPI.asyncTearDown
    login = core.CoreAPI.login
    request = core.CoreAPI.request
    subject = core.CoreAPI.subject
    chapter = core.CoreAPI.chapter
    point = core.CoreAPI.point
    due_task = core.CoreAPI.due_task
    completion = staticmethod(core.CoreAPI.completion)

    def _setupAsyncioRunner(self):
        if sys.platform == "win32":
            self._asyncioRunner = asyncio.Runner(loop_factory=asyncio.SelectorEventLoop)
        else:
            super()._setupAsyncioRunner()

    async def read(self, path=""):
        response = await self.request("GET", "/admin/analytics" + path, user=2)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def test_access_window_and_audit(self):
        response = await self.client.get("/api/v1/admin/analytics")
        self.assertEqual(response.status_code, 401)
        response = await self.request("GET", "/admin/analytics")
        self.assertEqual(response.status_code, 403)
        for query in (
            "?days=91", "?from_date=1900-01-01", "?from_date=2020-01-01&to_date=2021-01-02",
            "?from_date=2026-04-03&to_date=2026-04-02",
        ):
            response = await self.request("GET", "/admin/analytics" + query, user=2)
            self.assertEqual(response.status_code, 400, response.text)
        payload = await self.read("?from_date=1971-09-03&to_date=1971-09-04")
        self.assertEqual([day["date"] for day in payload["learning"]], ["1971-09-03", "1971-09-04"])
        self.assertTrue(all(day["completion_rate"] is None for day in payload["learning"]))
        self.assertTrue(all(day["tokens"] is None for day in payload["ai_usage"]["days"]))
        self.assertEqual(payload["workflow"]["imported_versions"], 0)
        self.assertTrue(all(row["predicted"] is None for row in payload["retention"]))
        self.assertTrue(all(day["average_ms"] is None for day in payload["jobs"]["days"]))
        async with self.owner.transaction() as db:
            audits = await db.scalar(
                select(func.count()).select_from(AuditEvent).where(
                    AuditEvent.actor_id == self.users[2].id,
                    AuditEvent.action == "admin_analytics_read",
                )
            )
        self.assertEqual(audits, 1)

    async def test_learner_write_updates_shared_analytics_and_same_kind_batch_cohort(self):
        now = datetime.now(timezone.utc)
        zone = ZoneInfo("Asia/Shanghai")
        today = now.astimezone(zone).date().isoformat()
        query = f"?from_date={today}&to_date={today}"
        before = await self.read(query)
        _, task, _ = await self.due_task()
        pending = await self.read(query)
        self.assertEqual(pending["today_due"], before["today_due"] + 1)
        response = await self.request(
            "POST", f"/review-tasks/{task['id']}/complete", body=self.completion(), key=str(uuid4())
        )
        self.assertEqual(response.status_code, 200, response.text)
        response = await self.request("GET", "/workspace/insights?days=1")
        self.assertEqual(response.status_code, 200, response.text)
        learner = response.json()
        after = await self.read(query)
        result = after["learning"][0]
        previous = before["learning"][0]
        self.assertEqual(result["knowledge"] - previous["knowledge"], learner["metrics"]["knowledge_total"])
        self.assertEqual(result["reviews"] - previous["reviews"], learner["metrics"]["today_reviews"])
        self.assertEqual(result["assigned"] - previous["assigned"], learner["metrics"]["today_tasks"])
        self.assertEqual(result["completed"] - previous["completed"], learner["metrics"]["today_completed_tasks"])
        self.assertAlmostEqual(result["completion_rate"], result["completed"] / result["assigned"])
        self.assertEqual(after["today_due"], before["today_due"])
        completed_batches = {row["key"]: row for row in after["jobs"]["kinds"]}
        previous_batches = {row["key"]: row for row in before["jobs"]["kinds"]}
        self.assertEqual(completed_batches["review_batch"]["success"] - previous_batches["review_batch"]["success"], 1)
        self.assertIsNone(completed_batches["review_batch"]["average_ms"])

    async def test_split_at_dst_midnight_and_match_the_learner_view(self):
        zone = ZoneInfo("America/New_York")
        chapter = await self.chapter()
        before_start = datetime(2026, 10, 31, 23, 30, tzinfo=zone)
        after_end = datetime(2026, 11, 1, 2, 30, tzinfo=zone)
        current = datetime(2026, 11, 2, 12, tzinfo=zone)
        async with self.owner.transaction() as db:
            for actor in (self.users[0], self.users[2]):
                model = await db.get(User, actor.id)
                model.timezone = zone.key
        query = "?from_date=2026-10-31&to_date=2026-11-01"
        with patch("app.services.admin_analytics.utcnow", return_value=current):
            before = await self.read(query)
            response = await self.request(
                "POST", f"/chapters/{chapter['id']}/study-sessions",
                key=str(uuid4()),
                body={"started_at": before_start.isoformat(), "ended_at": after_end.isoformat()},
            )
            self.assertEqual(response.status_code, 201, response.text)
            after = await self.read(query)
        response = await self.request("GET", "/workspace/insights" + query)
        self.assertEqual(response.status_code, 200, response.text)
        user_values = [row["study_seconds"] for row in response.json()["activity"]]
        self.assertEqual(user_values, [1800, 12600])
        delta = [
            new["study_seconds"] - old["study_seconds"]
            for new, old in zip(after["learning"], before["learning"], strict=True)
        ]
        self.assertEqual(delta, user_values)
        self.assertEqual(after["timezone"], zone.key)
