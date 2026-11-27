"""``ai_call_logs`` 对应的调用记录结构与状态机（AI-01 / FR-02）。

字段严格对齐 DATABASE_SCHEMA.md 的 ``ai_call_logs`` 与契约
``AICallLogRead``：provider、model、prompt 版本、token、耗时、状态、错误。
调用日志为追加写：终态（succeeded / failed / cancelled）不可再改写。

时间为 UTC 带时区的 RFC3339 字符串；``clock`` 可注入以便真实单测。
本模块仅使用标准库。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from .errors import AIIntegrationError, ErrorDetail, InvalidStateError
from .validation import AI_CALL_STATUSES, AICALL_LOG_READ_FIELDS

TERMINAL_STATUSES = frozenset({"succeeded", "failed", "cancelled"})


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat()


@dataclass
class AICallLog:
    """一条 AI 调用审计记录（对齐 ``ai_call_logs`` 表）。"""

    operation: str
    provider: str
    model_name: str
    prompt_version: str
    provider_config_id: str
    request_id: str = field(default_factory=lambda: str(uuid4()))
    id: str = field(default_factory=lambda: str(uuid4()))
    status: str = "pending"
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    duration_ms: int | None = None
    attempt_count: int = 1
    error_code: str | None = None
    error_message: str | None = None
    started_at: str = ""
    finished_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    clock: Callable[[], datetime] = field(default=_utc_now, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.started_at:
            self.started_at = _iso(self.clock())
            self._started_dt = self.clock()
        else:
            self._started_dt = datetime.fromisoformat(self.started_at)

    def _assert_mutable(self) -> None:
        if self.status in TERMINAL_STATUSES:
            raise InvalidStateError(
                f"调用日志已处于终态 {self.status!r}，追加写不允许改写",
                details=[ErrorDetail("status", "terminal state is immutable")],
            )

    def start(self) -> None:
        """pending → running。"""
        if self.status != "pending":
            raise InvalidStateError(f"只能从 pending 进入 running，当前为 {self.status!r}")
        self.status = "running"

    def record_attempt(self) -> None:
        """每次重试后累加 ``attempt_count``（对齐契约字段）。"""
        self._assert_mutable()
        self.attempt_count += 1

    def succeed(
        self,
        *,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        total_tokens: int | None = None,
    ) -> None:
        """running → succeeded，写入 token、耗时与完成时间。"""
        self._assert_mutable()
        if self.status != "running":
            raise InvalidStateError(f"只能从 running 进入 succeeded，当前为 {self.status!r}")
        self.status = "succeeded"
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        if total_tokens is not None:
            self.total_tokens = total_tokens
        elif input_tokens is not None or output_tokens is not None:
            self.total_tokens = (input_tokens or 0) + (output_tokens or 0)
        self.error_code = None
        self.error_message = None
        finished = self.clock()
        self.finished_at = _iso(finished)
        self.duration_ms = max(0, int((finished - self._started_dt).total_seconds() * 1000))

    def fail(self, error: AIIntegrationError | BaseException) -> None:
        """running → failed，记录错误码与脱敏错误说明。"""
        self._assert_mutable()
        if self.status != "running":
            raise InvalidStateError(f"只能从 running 进入 failed，当前为 {self.status!r}")
        self.status = "failed"
        self.error_code = getattr(error, "code", "INTERNAL_ERROR")
        self.error_message = str(error)
        self.total_tokens = None
        finished = self.clock()
        self.finished_at = _iso(finished)
        self.duration_ms = max(0, int((finished - self._started_dt).total_seconds() * 1000))

    def cancel(self, reason: str = "") -> None:
        """pending/running → cancelled。"""
        self._assert_mutable()
        self.status = "cancelled"
        self.error_code = "INVALID_STATE"
        self.error_message = reason or "调用被取消"
        finished = self.clock()
        self.finished_at = _iso(finished)
        self.duration_ms = max(0, int((finished - self._started_dt).total_seconds() * 1000))

    def to_contract_dict(self) -> dict[str, Any]:
        """仅输出 ``AICallLogRead`` 契约字段，供 API 序列化。"""
        row = self.to_row_dict()
        return {name: row[name] for name in AICALL_LOG_READ_FIELDS}

    def to_row_dict(self) -> dict[str, Any]:
        """输出 ``ai_call_logs`` 落库字段（含 metadata，不含 prompt 原文/密钥）。"""
        return {
            "id": self.id,
            "provider_config_id": self.provider_config_id,
            "operation": self.operation,
            "provider": self.provider,
            "model_name": self.model_name,
            "prompt_version": self.prompt_version,
            "request_id": self.request_id,
            "status": self.status,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "duration_ms": self.duration_ms,
            "attempt_count": self.attempt_count,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "metadata": dict(self.metadata),
        }


class CallRecorder:
    """一次业务调用对应一条 ``AICallLog`` 的追加写封装。"""

    def __init__(
        self,
        *,
        operation: str,
        provider: str,
        model_name: str,
        prompt_version: str,
        provider_config_id: str,
        request_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.log = AICallLog(
            operation=operation,
            provider=provider,
            model_name=model_name,
            prompt_version=prompt_version,
            provider_config_id=provider_config_id,
            request_id=request_id or str(uuid4()),
            metadata=dict(metadata or {}),
            clock=clock or _utc_now,
        )

    def start(self) -> None:
        self.log.start()

    def retry(self) -> None:
        self.log.record_attempt()

    def succeed(self, result: Any) -> None:
        self.log.succeed(
            input_tokens=getattr(result, "input_tokens", None),
            output_tokens=getattr(result, "output_tokens", None),
            total_tokens=getattr(result, "total_tokens", None),
        )

    def fail(self, error: BaseException) -> None:
        self.log.fail(error)


def validate_call_log_row(row: dict[str, Any]) -> list[str]:
    """校验一条调用日志是否满足契约状态与字段约束（纯逻辑）。"""
    errors: list[str] = []
    missing = sorted(set(AICALL_LOG_READ_FIELDS) - set(row))
    if missing:
        errors.append(f"缺少契约字段: {missing}")
    status = row.get("status")
    if status not in AI_CALL_STATUSES:
        errors.append(f"status 非法: {status!r}")
    for name in ("input_tokens", "output_tokens", "total_tokens", "duration_ms", "attempt_count"):
        value = row.get(name)
        if value is not None and (not isinstance(value, int) or value < 0):
            errors.append(f"{name} 必须为非负整数，实际为 {value!r}")
    return errors
