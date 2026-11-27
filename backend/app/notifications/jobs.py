"""NOTIF-05 通知任务 / 投递 / 状态追踪领域对象。

字段与 DATABASE_SCHEMA.md 第 2 节「通知」表一一对应：
  notification_jobs、notification_deliveries（channel_configs / templates 由 config / worker 提供）。
状态机：pending -> processing -> sent；失败可回 pending 重试，耗尽后 failed；cancelled。

持久化说明：本模块只提供领域对象、状态机与「内存仓储端口」。
真实落库由 Backend 的 SQLAlchemy / Alembic 负责；按 BLK-05 本机 5432 实例未授权，
本批次不连接任何数据库，InMemoryJobRepository 仅用于编排与单测（明确标注，非数据库）。
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

from .contract_values import DeliveryStatus, JobStatus
from .errors import NotificationError
from .ports import RenderedMessage


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class NotificationJob:
    """notification_jobs 行。segments / channel_type 是编排运行态，不映射 DB 列。"""

    user_id: str
    task_id: str
    channel_config_id: str
    template_id: str
    idempotency_key: str
    rendered_title: str = ""
    rendered_body: str = ""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: str = JobStatus.PENDING
    attempt_count: int = 0
    max_attempts: int = 3
    next_attempt_at: datetime | None = None
    last_error_code: str | None = None
    last_error_message: str | None = None
    sent_at: datetime | None = None
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    # ---- 运行态（不落库）----
    #: 按渠道长度分段后的待发消息；冻结表结构无显式列，详见交付说明中的契约差异项。
    segments: list[RenderedMessage] = field(default_factory=list, repr=False)
    channel_type: str = ""

    def mark_processing(self, now: datetime) -> None:
        self._require((JobStatus.PENDING,))
        self.status = JobStatus.PROCESSING
        self.updated_at = now

    def mark_sent(self, now: datetime) -> None:
        self._require((JobStatus.PROCESSING,))
        self.status = JobStatus.SENT
        self.sent_at = now
        self.next_attempt_at = None
        self.last_error_code = None
        self.last_error_message = None
        self.updated_at = now

    def mark_retry(
        self, next_at: datetime, code: str | None, message: str | None, now: datetime
    ) -> None:
        self._require((JobStatus.PROCESSING,))
        self.status = JobStatus.PENDING
        self.next_attempt_at = next_at
        self.last_error_code = code
        self.last_error_message = message
        self.updated_at = now

    def mark_failed(self, code: str | None, message: str | None, now: datetime) -> None:
        self._require((JobStatus.PROCESSING, JobStatus.PENDING))
        self.status = JobStatus.FAILED
        self.next_attempt_at = None
        self.last_error_code = code
        self.last_error_message = message
        self.updated_at = now

    def cancel(self, now: datetime) -> None:
        self._require((JobStatus.PENDING,))
        self.status = JobStatus.CANCELLED
        self.updated_at = now

    def requeue(self, now: datetime) -> None:
        """POST /notification/jobs/{id}/retry：仅 failed 可重试，开启新一轮尝试。"""
        self._require((JobStatus.FAILED,))
        self.status = JobStatus.PENDING
        self.attempt_count = 0
        self.next_attempt_at = now
        self.last_error_code = None
        self.last_error_message = None
        self.updated_at = now

    def _require(self, allowed: Iterable[str]) -> None:
        if self.status not in allowed:
            raise NotificationError(
                f"非法状态转移: {self.status} -> (需要 {list(allowed)})",
                code="INVALID_STATE",
            )


@dataclass
class NotificationDelivery:
    """notification_deliveries 行（追加写，无 UPDATE/DELETE 业务端点）。"""

    user_id: str
    job_id: str
    attempt_no: int
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: str = DeliveryStatus.SENDING
    provider_message_id: str | None = None
    request_metadata: dict[str, Any] = field(default_factory=dict)
    response_metadata: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    duration_ms: int | None = None
    attempted_at: datetime = field(default_factory=_utcnow)
    created_at: datetime = field(default_factory=_utcnow)

    @classmethod
    def start(
        cls,
        job: NotificationJob,
        attempt_no: int,
        now: datetime,
        request_metadata: dict[str, Any],
    ) -> "NotificationDelivery":
        return cls(
            user_id=job.user_id,
            job_id=job.id,
            attempt_no=attempt_no,
            attempted_at=now,
            created_at=now,
            request_metadata=dict(request_metadata),
        )

    def mark_sent(
        self,
        provider_message_id: str | None,
        response_metadata: dict[str, Any],
        duration_ms: int,
    ) -> None:
        self.status = DeliveryStatus.SENT
        self.provider_message_id = provider_message_id
        self.response_metadata = dict(response_metadata)
        self.duration_ms = duration_ms

    def mark_failed(
        self,
        error_code: str | None,
        error_message: str | None,
        response_metadata: dict[str, Any],
        duration_ms: int,
    ) -> None:
        self.status = DeliveryStatus.FAILED
        self.error_code = error_code
        self.error_message = error_message
        self.response_metadata = dict(response_metadata)
        self.duration_ms = duration_ms


class JobRepository(ABC):
    """持久化端口。Backend 以 PostgreSQL 实现；本批次仅提供内存实现。"""

    @abstractmethod
    def save_job(self, job: NotificationJob) -> None: ...

    @abstractmethod
    def get_job(self, job_id: str) -> NotificationJob | None: ...

    @abstractmethod
    def find_by_idempotency_key(self, user_id: str, key: str) -> NotificationJob | None: ...

    @abstractmethod
    def list_jobs(
        self, *, user_id: str | None = None, status: str | None = None
    ) -> list[NotificationJob]: ...

    @abstractmethod
    def append_delivery(self, delivery: NotificationDelivery) -> None: ...

    @abstractmethod
    def list_deliveries(self, job_id: str) -> list[NotificationDelivery]: ...


class InMemoryJobRepository(JobRepository):
    """内存实现：仅用于领域编排与单元测试。

    明确标注：这不是数据库、不代表已联调；真实持久化由 Backend 落 PostgreSQL（BLK-05 未授权）。
    """

    def __init__(self) -> None:
        self._jobs: dict[str, NotificationJob] = {}
        self._keys: dict[tuple[str, str], str] = {}
        self._deliveries: dict[str, list[NotificationDelivery]] = {}

    def save_job(self, job: NotificationJob) -> None:
        self._jobs[job.id] = job
        self._keys[(job.user_id, job.idempotency_key)] = job.id

    def get_job(self, job_id: str) -> NotificationJob | None:
        return self._jobs.get(job_id)

    def find_by_idempotency_key(self, user_id: str, key: str) -> NotificationJob | None:
        job_id = self._keys.get((user_id, key))
        return self._jobs.get(job_id) if job_id else None

    def list_jobs(
        self, *, user_id: str | None = None, status: str | None = None
    ) -> list[NotificationJob]:
        return [
            job
            for job in self._jobs.values()
            if (user_id is None or job.user_id == user_id)
            and (status is None or job.status == status)
        ]

    def append_delivery(self, delivery: NotificationDelivery) -> None:
        self._deliveries.setdefault(delivery.job_id, []).append(delivery)

    def list_deliveries(self, job_id: str) -> list[NotificationDelivery]:
        return sorted(self._deliveries.get(job_id, []), key=lambda item: item.attempt_no)
