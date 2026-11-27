"""指数退避重试（纯函数，确定性，可单测）。

只重试「可重试错误」：网络 / 超时 / 5xx / 429 / 系统繁忙类业务码。
缺凭据(CONFIG_MISSING)、内容不具体(SEMANTIC_VALIDATION_ERROR)、
模板错误(VALIDATION_ERROR)、参数类 4xx 一律不重试。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True)
class RetryPolicy:
    """退避策略；与 .env.example 的 NOTIFY_MAX_RETRIES / NOTIFY_RETRY_BACKOFF_SECONDS 对齐。"""

    max_attempts: int = 3                    # 总尝试次数上限（含首次）
    base_seconds: float = 60.0               # 首次失败后的等待
    multiplier: float = 2.0                  # 指数底
    max_delay_seconds: float | None = 3600.0  # 单次等待上限（cap）

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts 必须 >= 1")
        if self.base_seconds < 0:
            raise ValueError("base_seconds 必须 >= 0")
        if self.multiplier < 1:
            raise ValueError("multiplier 必须 >= 1")


def backoff_delays(policy: RetryPolicy) -> tuple[float, ...]:
    """返回每次失败后「重试前」等待秒数，长度 = max_attempts - 1。

    第 k 次重试等待 = min(base * multiplier**(k-1), cap)。
    纯函数：无随机、无 I/O，便于固定用例单测。
    """
    delays: list[float] = []
    for k in range(1, policy.max_attempts):
        delay = policy.base_seconds * (policy.multiplier ** (k - 1))
        if policy.max_delay_seconds is not None:
            delay = min(delay, policy.max_delay_seconds)
        delays.append(float(delay))
    return tuple(delays)


#: 可重试的 HTTP 状态码；其余 5xx 也视为可重试（见 is_retryable_status）。
RETRYABLE_HTTP_STATUS: frozenset[int] = frozenset({408, 425, 429, 500, 502, 503, 504})


def is_retryable_status(status_code: int | None) -> bool:
    if status_code is None:
        return True  # 连接/超时：无 HTTP 状态，视为可重试
    return status_code in RETRYABLE_HTTP_STATUS or 500 <= status_code < 600


def should_retry(attempt_no: int, policy: RetryPolicy, *, error_retryable: bool = True) -> bool:
    """attempt_no 为「刚失败的尝试序号」(1-based)。"""
    return error_retryable and attempt_no < policy.max_attempts


def next_attempt_at(now: datetime, attempt_no: int, policy: RetryPolicy) -> datetime | None:
    """计算下次尝试的 UTC 时间；若无更多重试返回 None。

    now 统一按 UTC 处理：若传入 naive datetime，视为 UTC。
    """
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    delays = backoff_delays(policy)
    index = attempt_no - 1
    if index < 0 or index >= len(delays):
        return None
    return now + timedelta(seconds=delays[index])
