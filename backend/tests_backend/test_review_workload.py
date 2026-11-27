"""Review workload and open queue regressions against the dedicated PostgreSQL database."""

import asyncio
import os
import sys
import unittest
from dataclasses import replace
from datetime import timedelta
from uuid import UUID, uuid4

import test_core_api as core
from sqlalchemy import func, select, update

from app.models import DailyReviewBatch, ScheduleState
from app.services.common import utcnow


@unittest.skipUnless(os.environ.get("TEST_DATABASE_URL"), "TEST_DATABASE_URL required")
class ReviewWorkloadTests(unittest.IsolatedAsyncioTestCase):
    sequence = 770
    asyncSetUp = core.CoreAPI.asyncSetUp
    asyncTearDown = core.CoreAPI.asyncTearDown
    login = core.CoreAPI.login
    request = core.CoreAPI.request
    subject = core.CoreAPI.subject
    point = core.CoreAPI.point
    completion = staticmethod(core.CoreAPI.completion)

    def _setupAsyncioRunner(self):
        if sys.platform == "win32":
            self._asyncioRunner = asyncio.Runner(loop_factory=asyncio.SelectorEventLoop)
        else:
            super()._setupAsyncioRunner()

    async def due_point(self):
        point = await self.point(active=True)
        async with self.owner.transaction() as session:
            await session.execute(
                update(ScheduleState)
                .where(ScheduleState.knowledge_point_id == UUID(point["id"]))
                .values(due_at=utcnow() - timedelta(minutes=1))
            )
        return point

    async def workload(self, user=0):
        response = await self.request("GET", "/workspace/review-workload", user=user)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def generate(self, snapshot, limit=None, subject_id=None):
        body = {
            "local_date": snapshot["local_date"],
            "timezone": snapshot["timezone"],
            "daily_limit": snapshot["daily_limit"] if limit is None else limit,
        }
        if subject_id:
            body["subject_id"] = subject_id
        response = await self.request(
            "POST", "/review-batches/generate", key=str(uuid4()), body=body
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["tasks"]

    async def test_due_before_generation_capacity_open_queue_and_isolation(self):
        await self.due_point()
        await self.due_point()
        await self.point()
        before = await self.workload()
        self.assertEqual(
            (before["queued"], before["due_unqueued"], before["can_enqueue"]), (0, 2, 2)
        )
        self.assertIsNone(before["estimated_seconds"])
        self.assertFalse(before["automatic_processing_enabled"])
        other = await self.workload(user=1)
        self.assertEqual((other["queued"], other["due_unqueued"], other["can_enqueue"]), (0, 0, 0))
        async with self.owner.transaction() as session:
            count = await session.scalar(
                select(func.count())
                .select_from(DailyReviewBatch)
                .where(DailyReviewBatch.user_id == self.users[0].id)
            )
            self.assertEqual(count, 0)
        task = (await self.generate(before, 1))[0]
        response = await self.request("POST", f"/review-tasks/{task['id']}/start", key=str(uuid4()))
        self.assertEqual(response.status_code, 200, response.text)
        response = await self.request("GET", "/review-tasks?status=open")
        self.assertEqual([row["status"] for row in response.json()["items"]], ["in_progress"])
        response = await self.request("GET", "/review-tasks?status=pending")
        self.assertEqual(response.json()["items"], [])
        after = await self.workload()
        self.assertEqual((after["queued"], after["due_unqueued"], after["can_enqueue"]), (1, 1, 0))
        self.assertEqual(after["daily_limit"], 1)
        self.assertEqual([row["id"] for row in await self.generate(after)], [task["id"]])

    async def test_skipped_today_is_not_a_new_candidate_for_same_batch(self):
        await self.due_point()
        task = (await self.generate(await self.workload()))[0]
        response = await self.request(
            "POST", f"/review-tasks/{task['id']}/skip", key=str(uuid4()), body={}
        )
        self.assertEqual(response.status_code, 200, response.text)
        snapshot = await self.workload()
        self.assertEqual(
            (snapshot["queued"], snapshot["due_unqueued"], snapshot["can_enqueue"]), (0, 1, 0)
        )

    async def test_subject_batches_share_capacity_and_skip_does_not_requeue(self):
        self.app.state.settings = replace(self.settings, daily_review_limit=1)
        first, second = await self.due_point(), await self.due_point()
        snapshot = await self.workload()
        assigned = await self.generate(snapshot, limit=5, subject_id=first["subject_id"])
        self.assertEqual(len(assigned), 1)
        response = await self.request(
            "POST", f"/review-tasks/{assigned[0]['id']}/skip", key=str(uuid4()), body={}
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(await self.generate(snapshot, limit=5, subject_id=second["subject_id"]), [])
        self.assertEqual(await self.generate(snapshot, limit=5), [])
        self.assertEqual((await self.workload())["can_enqueue"], 0)

    async def test_estimate_is_personal_median_and_excludes_invalid_durations(self):
        for _ in range(9):
            await self.due_point()
        tasks = await self.generate(await self.workload())
        for task, seconds in zip(tasks, [8, 12, 32, 46, 50, 0, 4000], strict=False):
            response = await self.request(
                "POST",
                f"/review-tasks/{task['id']}/complete",
                key=str(uuid4()),
                body={**self.completion(), "duration_seconds": seconds},
            )
            self.assertEqual(response.status_code, 200, response.text)
        snapshot = await self.workload()
        self.assertEqual(snapshot["queued"], 2)
        self.assertEqual(snapshot["sample_size"], 5)
        self.assertEqual(snapshot["estimated_seconds"], 64)
        self.assertIsNone((await self.workload(user=1))["estimated_seconds"])
