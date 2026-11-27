"""重试策略与速率限制（纯逻辑，AI-01）。

``max_retries`` / ``rate_limit_per_minute`` 来自 Provider 配置；时钟与
退避等待均可注入，单元测试不产生真实 sleep，也不访问外部服务。
只重试被显式标记为 ``retryable`` 的错误（超时 / 429 / 5xx）。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from .errors import is_retryable


@dataclass(frozen=True)
class RetryPolicy:
    """指数退避重试策略。

    ``max_retries`` 为首次调用失败后的最大额外重试次数；总尝试次数
    ``total_attempts = max_retries + 1``。
    """

    max_retries: int = 3
    base_backoff_seconds: float = 1.0
    backoff_multiplier: float = 2.0
    max_backoff_seconds: float = 30.0

    def __post_init__(self) -> None:
        if self.max_retries < 0:
            raise ValueError("max_retries 必须 >= 0")
        if self.base_backoff_seconds < 0:
            raise ValueError("base_backoff_seconds 必须 >= 0")

    @property
    def total_attempts(self) -> int:
        return self.max_retries + 1

    def should_retry(self, error: BaseException, attempt: int) -> bool:
        """``attempt`` 为 1-based 的当前失败尝试序号。"""
        if attempt > self.max_retries:
            return False
        return is_retryable(error)

    def backoff_seconds(self, attempt: int) -> float:
        """第 ``attempt`` 次失败后应等待的秒数（1-based）。"""
        if attempt < 1:
            raise ValueError("attempt 必须 >= 1")
        raw = self.base_backoff_seconds * (self.backoff_multiplier ** (attempt - 1))
        return min(raw, self.max_backoff_seconds)


class RateLimiter:
    """固定窗口速率限制器（纯逻辑）。

    ``per_minute`` 为 None 表示不限流。``clock`` 默认 ``time.monotonic``，
    测试中注入确定性时钟。
    """

    WINDOW_SECONDS = 60.0

    def __init__(
        self,
        per_minute: int | None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if per_minute is not None and per_minute <= 0:
            raise ValueError("per_minute 必须 > 0 或 None")
        self.per_minute = per_minute
        self._clock: Callable[[], float] = clock or time.monotonic
        self._timestamps: list[float] = []

    def _prune(self, now: float) -> None:
        cutoff = now - self.WINDOW_SECONDS
        self._timestamps = [t for t in self._timestamps if t > cutoff]

    def try_acquire(self) -> bool:
        """尝试取得一个配额；成功记录时间戳，失败不改变状态。"""
        if self.per_minute is None:
            return True
        now = self._clock()
        self._prune(now)
        if len(self._timestamps) < self.per_minute:
            self._timestamps.append(now)
            return True
        return False

    def retry_after_seconds(self) -> float:
        """当前被限流时还需等待的秒数；未被限流返回 0.0。"""
        if self.per_minute is None or len(self._timestamps) < self.per_minute:
            return 0.0
        now = self._clock()
        self._prune(now)
        if len(self._timestamps) < self.per_minute:
            return 0.0
        return max(0.0, self.WINDOW_SECONDS - (now - self._timestamps[0]))

    @property
    def used(self) -> int:
        return len(self._timestamps)
