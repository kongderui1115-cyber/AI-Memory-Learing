"""Real PostgreSQL review integration, enabled explicitly with TEST_DATABASE_URL."""
import asyncio
import os
import sys
import unittest
from dataclasses import asdict
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import select, func
from app.config import Settings
from app.database import Database
from app.domain.scheduling import initial_state
from app.contracts.models import ReviewCompleteRequest
from app.models import User, Subject, KnowledgePoint, ScheduleState, DailyReviewBatch, DailyReviewTask, ReviewHistory
from app.services.reviews import complete_review, ReviewError


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'), 'TEST_DATABASE_URL required')
class ReviewIntegrationTests(unittest.IsolatedAsyncioTestCase):
    def _setupAsyncioRunner(self):
        if sys.platform == 'win32':
            self._asyncioRunner = asyncio.Runner(loop_factory=asyncio.SelectorEventLoop)
        else:
            super()._setupAsyncioRunner()

    async def test_concurrent_replay_and_persistence(self):
        database = Database(Settings(database_url=os.environ['TEST_DATABASE_URL']))
        now = datetime.now(timezone.utc)
        user_id, subject_id, point_id, batch_id, task_id = [uuid4() for _ in range(5)]
        try:
            async with database.transaction() as session:
                session.add(User(id=user_id, email=f'{user_id}@example.test', display_name='test', password_hash='unused'))
                await session.flush()
                session.add(Subject(id=subject_id, user_id=user_id, slug='math', name='数学'))
                await session.flush()
                session.add(KnowledgePoint(id=point_id, user_id=user_id, subject_id=subject_id,
                    status='active', title='事务', body='测试原文', summary='测试摘要', difficulty=1, canonical_hash='a'*64))
                session.add(DailyReviewBatch(id=batch_id, user_id=user_id, local_date=now.date(),
                    timezone='UTC', daily_limit=10, status='ready', idempotency_key=str(uuid4())))
                await session.flush()
                session.add(ScheduleState(user_id=user_id, knowledge_point_id=point_id,
                    **asdict(initial_state('ebbinghaus', now))))
                session.add(DailyReviewTask(id=task_id, user_id=user_id, batch_id=batch_id,
                    knowledge_point_id=point_id, scheduled_due_at=now, position=0))
            request = ReviewCompleteRequest(rating='good', duration_seconds=10, reviewed_at=now)
            results = await asyncio.gather(*[
                complete_review(database, user_id, task_id, request, 'same-review') for _ in range(2)])
            self.assertEqual(results[0].id, results[1].id)
            with self.assertRaises(ReviewError) as conflict:
                await complete_review(database, user_id, task_id,
                    request.model_copy(update={'duration_seconds': 11}), 'same-review')
            self.assertEqual(conflict.exception.code, 'IDEMPOTENCY_CONFLICT')
            async with database.transaction() as session:
                count = await session.scalar(select(func.count()).select_from(ReviewHistory).where(ReviewHistory.user_id == user_id))
                task = await session.get(DailyReviewTask, task_id)
                state = await session.scalar(select(ScheduleState).where(ScheduleState.knowledge_point_id == point_id))
                self.assertEqual(count, 1)
                self.assertEqual(task.status, 'completed')
                self.assertEqual(state.review_count, 1)
                self.assertEqual(state.state_version, 2)
        finally:
            await database.close()