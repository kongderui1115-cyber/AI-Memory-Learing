"""AI-01 重试策略与速率限制测试（真实纯逻辑，注入时钟，不 sleep、不联网）。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_TESTS = Path(__file__).resolve().parent
for _path in (str(_BACKEND), str(_TESTS)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from app.ai.errors import (  # noqa: E402
    ConfigMissingError,
    ProviderAuthError,
    ProviderRateLimitedError,
    ProviderResponseError,
    ProviderServiceError,
    ProviderTimeoutError,
)
from app.ai.retry import RateLimiter, RetryPolicy  # noqa: E402


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class RetryPolicyTests(unittest.TestCase):
    def test_total_attempts(self):
        self.assertEqual(RetryPolicy(max_retries=0).total_attempts, 1)
        self.assertEqual(RetryPolicy(max_retries=3).total_attempts, 4)

    def test_only_retryable_errors(self):
        policy = RetryPolicy(max_retries=2)
        for error in (
            ProviderTimeoutError("t"),
            ProviderRateLimitedError("r"),
            ProviderServiceError("s"),
        ):
            with self.subTest(error=type(error).__name__):
                self.assertTrue(policy.should_retry(error, 1))
        for error in (
            ProviderAuthError("a"),
            ProviderResponseError("p"),
            ConfigMissingError("c"),
            ValueError("v"),
        ):
            with self.subTest(error=type(error).__name__):
                self.assertFalse(policy.should_retry(error, 1))

    def test_exhausted_retries_not_retried(self):
        policy = RetryPolicy(max_retries=2)
        self.assertTrue(policy.should_retry(ProviderTimeoutError("t"), 2))
        self.assertFalse(policy.should_retry(ProviderTimeoutError("t"), 3))

    def test_backoff_exponential_and_capped(self):
        policy = RetryPolicy(
            max_retries=10, base_backoff_seconds=1.0,
            backoff_multiplier=2.0, max_backoff_seconds=5.0,
        )
        self.assertEqual(policy.backoff_seconds(1), 1.0)
        self.assertEqual(policy.backoff_seconds(2), 2.0)
        self.assertEqual(policy.backoff_seconds(3), 4.0)
        self.assertEqual(policy.backoff_seconds(4), 5.0)
        self.assertEqual(policy.backoff_seconds(10), 5.0)

    def test_invalid_construction(self):
        with self.assertRaises(ValueError):
            RetryPolicy(max_retries=-1)
        with self.assertRaises(ValueError):
            RetryPolicy(base_backoff_seconds=-1)


class RateLimiterTests(unittest.TestCase):
    def test_unlimited_when_none(self):
        limiter = RateLimiter(None)
        for _ in range(100):
            self.assertTrue(limiter.try_acquire())
        self.assertEqual(limiter.retry_after_seconds(), 0.0)

    def test_quota_enforced_within_window(self):
        clock = FakeClock()
        limiter = RateLimiter(3, clock=clock)
        self.assertTrue(limiter.try_acquire())
        self.assertTrue(limiter.try_acquire())
        self.assertTrue(limiter.try_acquire())
        self.assertFalse(limiter.try_acquire())
        self.assertEqual(limiter.used, 3)

    def test_window_expiry_frees_quota(self):
        clock = FakeClock()
        limiter = RateLimiter(2, clock=clock)
        self.assertTrue(limiter.try_acquire())
        self.assertTrue(limiter.try_acquire())
        self.assertFalse(limiter.try_acquire())
        clock.advance(61.0)
        self.assertTrue(limiter.try_acquire())
        self.assertEqual(limiter.used, 1)

    def test_retry_after_seconds(self):
        clock = FakeClock()
        limiter = RateLimiter(1, clock=clock)
        self.assertTrue(limiter.try_acquire())
        self.assertFalse(limiter.try_acquire())
        self.assertAlmostEqual(limiter.retry_after_seconds(), 60.0)
        clock.advance(45.0)
        self.assertAlmostEqual(limiter.retry_after_seconds(), 15.0)
        clock.advance(16.0)
        self.assertEqual(limiter.retry_after_seconds(), 0.0)

    def test_invalid_quota(self):
        with self.assertRaises(ValueError):
            RateLimiter(0)
        with self.assertRaises(ValueError):
            RateLimiter(-1)


if __name__ == "__main__":
    unittest.main()
