"""Dashboard aggregation against the real isolated PostgreSQL test database."""

import asyncio
import os
import sys
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import test_core_api as core

from app.models import StudySession, User


@unittest.skipUnless(os.environ.get("TEST_DATABASE_URL"), "TEST_DATABASE_URL required")
class WorkspaceInsights(unittest.IsolatedAsyncioTestCase):
    sequence = 340
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

    async def test_empty_and_tenant_isolation_without_manufactured_values(self):
        await self.point(active=True)
        response = await self.request("GET", "/workspace/insights", user=1)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(len(result["activity"]), 14)
        self.assertEqual(result["metrics"]["knowledge_total"], 0)
        self.assertIsNone(result["metrics"]["recall_rate"])
        self.assertEqual(result["metrics"]["learning_days"], 0)
        self.assertFalse(result["subjects"])
        self.assertFalse(result["upcoming"])
        self.assertTrue(all(row["study_seconds"] == 0 for row in result["activity"]))
        response = await self.request("GET", "/workspace/insights")
        self.assertEqual(response.json()["metrics"]["knowledge_total"], 1)
        self.assertEqual(response.json()["memory"][0]["count"], 1)

    async def test_cross_midnight_study_is_split_in_account_timezone(self):
        chapter = await self.chapter()
        zone = ZoneInfo("Asia/Shanghai")
        start = datetime(2026, 11, 17, 23, 30, tzinfo=zone)
        end = start + timedelta(hours=1)
        async with self.owner.transaction() as session:
            session.add(
                StudySession(
                    user_id=self.users[0].id,
                    chapter_id=chapter["id"],
                    started_at=start,
                    ended_at=end,
                    duration_seconds=3600,
                )
            )
        with patch(
            "app.services.insights.utcnow", return_value=datetime(2026, 11, 18, 12, tzinfo=zone)
        ):
            response = await self.request("GET", "/workspace/insights?days=2")
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual([row["study_seconds"] for row in data["activity"]], [1800, 1800])
        self.assertEqual(data["metrics"]["today_study_seconds"], 1800)
        self.assertEqual(data["metrics"]["streak_days"], 1)

    async def test_dst_calendar_day_uses_elapsed_seconds(self):
        chapter = await self.chapter()
        zone = ZoneInfo("America/New_York")
        start, end = datetime(2026, 11, 1, tzinfo=zone), datetime(2026, 11, 2, tzinfo=zone)
        async with self.owner.transaction() as session:
            user = await session.get(User, self.users[0].id)
            user.timezone = zone.key
            session.add(
                StudySession(
                    user_id=user.id,
                    chapter_id=chapter["id"],
                    started_at=start,
                    ended_at=end,
                    duration_seconds=90000,
                )
            )
        with patch(
            "app.services.insights.utcnow", return_value=datetime(2026, 11, 2, 12, tzinfo=zone)
        ):
            response = await self.request("GET", "/workspace/insights?days=2")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["activity"][0]["study_seconds"], 90000)
        self.assertEqual(response.json()["timezone"], zone.key)

    async def test_real_review_updates_counts_success_rate_history_and_projection(self):
        point, task, _ = await self.due_task()
        response = await self.request("GET", "/review-tasks?q=知识&limit=1")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["items"][0]["knowledge_title"], point["title"])
        self.assertEqual(response.json()["items"][0]["subject_id"], point["subject_id"])
        response = await self.request(
            "POST", f"/review-tasks/{task['id']}/complete", body=self.completion(), key=str(uuid4())
        )
        self.assertEqual(response.status_code, 200, response.text)
        response = await self.request("GET", "/workspace/insights")
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["metrics"]["today_reviews"], 1)
        self.assertEqual(data["metrics"]["today_completed_tasks"], 1)
        self.assertEqual(data["metrics"]["pending_reviews"], 0)
        self.assertEqual(data["metrics"]["recall_rate"], 1)
        self.assertEqual(data["metrics"]["streak_days"], 1)
        self.assertEqual(data["memory"][1]["count"], 1)
        self.assertEqual(sum(p["count"] for p in data["upcoming"]), 1)
        response = await self.request("GET", "/review-history?q=知识&rating=good")
        self.assertEqual(response.json()["items"][0]["knowledge_title"], point["title"])
        response = await self.request("GET", "/review-history?q=absent")
        self.assertEqual(response.json()["items"], [])
        response = await self.request("GET", "/review-history?q=知识", user=1)
        self.assertEqual(response.json()["items"], [])

    async def test_range_authentication_and_invalid_query_guards(self):
        response = await self.client.get("/api/v1/workspace/insights")
        self.assertEqual(response.status_code, 401)
        for query in (
            "days=0",
            "days=91",
            "to_date=0001-01-01",
            "from_date=9999-12-31&to_date=9999-12-31",
            "to_date=0001-01-01",
            "from_date=9999-12-31&to_date=9999-12-31",
            "from_date=2026-11-18&to_date=2026-11-17",
            "from_date=2025-01-01&to_date=2026-11-18",
        ):
            response = await self.request("GET", "/workspace/insights?" + query)
            self.assertEqual(response.status_code, 400, (query, response.text))
        response = await self.request("GET", "/chapters?q=" + "a" * 201)
        self.assertEqual(response.status_code, 400)

    async def test_chapter_search_is_paginated_and_scoped(self):
        chapter = await self.chapter()
        response = await self.request("GET", "/chapters?q=分次&limit=1")
        self.assertEqual(response.json()["items"][0]["id"], chapter["id"])
        response = await self.request("GET", "/chapters?q=missing")
        self.assertFalse(response.json()["items"])
        response = await self.request("GET", "/chapters?q=分次", user=1)
        self.assertFalse(response.json()["items"])
