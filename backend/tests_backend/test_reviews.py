"""Review input guards run before database access."""
import unittest
from datetime import datetime, timezone
from uuid import uuid4
from pydantic import ValidationError
from app.contracts.models import ReviewCompleteRequest
from app.services.reviews import complete_review, ReviewError


class ReviewValidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_idempotency_keys_before_database_access(self):
        request = ReviewCompleteRequest(rating='good', duration_seconds=5,
                                        reviewed_at=datetime.now(timezone.utc))
        for key in ('', 'x' * 129):
            with self.subTest(key_length=len(key)):
                with self.assertRaises(ReviewError) as error:
                    await complete_review(None, uuid4(), uuid4(), request, key)
                self.assertEqual(error.exception.code, 'VALIDATION_ERROR')

    def test_review_time_requires_timezone(self):
        with self.assertRaises(ValidationError):
            ReviewCompleteRequest(rating='good', duration_seconds=0,
                                  reviewed_at=datetime(2026, 11, 13))

    def test_negative_duration_rejected(self):
        with self.assertRaises(ValidationError):
            ReviewCompleteRequest(rating='good', duration_seconds=-1,
                                  reviewed_at=datetime.now(timezone.utc))