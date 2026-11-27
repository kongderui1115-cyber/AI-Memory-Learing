"""指数退避重试序列纯函数测试（固定用例，确定性）。"""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.notifications.retry import (  # noqa: E402
    RetryPolicy,
    backoff_delays,
    is_retryable_status,
    next_attempt_at,
    should_retry,
)


class BackoffSequenceTest(unittest.TestCase):
    def test_default_exponential_sequence(self):
        policy = RetryPolicy(max_attempts=4, base_seconds=60, multiplier=2, max_delay_seconds=None)
        self.assertEqual(backoff_delays(policy), (60.0, 120.0, 240.0))

    def test_base_and_multiplier(self):
        policy = RetryPolicy(max_attempts=5, base_seconds=5, multiplier=3, max_delay_seconds=None)
        self.assertEqual(backoff_delays(policy), (5.0, 15.0, 45.0, 135.0))

    def test_cap_is_applied(self):
        policy = RetryPolicy(max_attempts=5, base_seconds=10, multiplier=10, max_delay_seconds=100)
        self.assertEqual(backoff_delays(policy), (10.0, 100.0, 100.0, 100.0))

    def test_single_attempt_has_no_delays(self):
        self.assertEqual(backoff_delays(RetryPolicy(max_attempts=1)), ())

    def test_invalid_policy_rejected(self):
        with self.assertRaises(ValueError):
            RetryPolicy(max_attempts=0)
        with self.assertRaises(ValueError):
            RetryPolicy(multiplier=0.5)

    def test_next_attempt_at_is_utc_based(self):
        now = datetime(2026, 11, 13, 12, 0, 0, tzinfo=timezone.utc)
        policy = RetryPolicy(max_attempts=3, base_seconds=60, multiplier=2, max_delay_seconds=None)
        self.assertEqual(next_attempt_at(now, 1, policy), now + timedelta(seconds=60))
        self.assertEqual(next_attempt_at(now, 2, policy), now + timedelta(seconds=120))
        self.assertIsNone(next_attempt_at(now, 3, policy))
        self.assertIsNone(next_attempt_at(now, 4, policy))

    def test_naive_now_treated_as_utc(self):
        now = datetime(2026, 11, 13, 12, 0, 0)  # naive
        result = next_attempt_at(now, 1, RetryPolicy(max_attempts=2, base_seconds=30))
        self.assertIsNotNone(result.tzinfo)
        self.assertEqual(result.tzinfo, timezone.utc)

    def test_should_retry(self):
        policy = RetryPolicy(max_attempts=3)
        self.assertTrue(should_retry(1, policy))
        self.assertTrue(should_retry(2, policy))
        self.assertFalse(should_retry(3, policy))
        self.assertFalse(should_retry(1, policy, error_retryable=False))

    def test_retryable_status_classification(self):
        for code in (408, 429, 500, 502, 503, 504, 599):
            self.assertTrue(is_retryable_status(code), f"{code} 应可重试")
        for code in (200, 400, 401, 403, 404, 422):
            self.assertFalse(is_retryable_status(code), f"{code} 不应重试")
        self.assertTrue(is_retryable_status(None))  # 连接/超时


if __name__ == "__main__":
    unittest.main()
