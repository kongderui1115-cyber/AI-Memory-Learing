"""NOTIF-05 通知编排：创建任务、渲染、发送、指数退避重试、失败记录、历史追踪。

本编排层是纯领域逻辑 + 注入的端口（registry / transports / repository / clock），
不依赖 FastAPI / SQLAlchemy / 数据库；按 BLK-05 不连接任何数据库。
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Callable

from .config import ChannelConfig
from .contract_values import JobStatus
from .content import (
    DEFAULT_BODY_TEMPLATE,
    DEFAULT_TITLE_TEMPLATE,
    KnowledgeContent,
    assert_concrete,
    build_context,
    validate_rendered_content,
)
from .errors import (
    ChannelDeliveryError,
    ConfigMissingError,
    EmptyContentError,
    NotificationError,
    TemplateRenderError,
)
from .jobs import (
    InMemoryJobRepository,
    JobRepository,
    NotificationDelivery,
    NotificationJob,
)
from .ports import SendResult
from .registry import ChannelRegistry
from .retry import RetryPolicy, next_attempt_at, should_retry
from .template import TemplateRenderer


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class NotificationTemplate:
    """notification_templates 行的轻量领域对象（字段名与契约一致）。"""

    channel_type: str
    template_key: str
    title_template: str = DEFAULT_TITLE_TEMPLATE
    body_template: str = DEFAULT_BODY_TEMPLATE
    schema_variables: list[str] = field(default_factory=list)
    max_length: int | None = None
    length_unit: str = "char"
    adaptive_mode: str = "segment"
    is_active: bool = True
    subject_id: str | None = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


def _effective_limit(template: NotificationTemplate, channel) -> int | None:
    """取模板与渠道中更严格的长度上限；单位以渠道 length_unit 为准。"""
    limits = [x for x in (template.max_length, channel.max_length) if x is not None]
    return min(limits) if limits else None


class NotificationWorker:
    """通知任务编排器。"""

    def __init__(
        self,
        *,
        registry: ChannelRegistry,
        http,
        smtp,
        repository: JobRepository | None = None,
        retry_policy: RetryPolicy | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.registry = registry
        self.http = http
        self.smtp = smtp
        self.repository: JobRepository = repository or InMemoryJobRepository()
        self.retry_policy = retry_policy or RetryPolicy()
        self.clock: Callable[[], datetime] = clock or _utcnow
        self._configs: dict[str, ChannelConfig] = {}

    def register_config(self, config: ChannelConfig) -> None:
        self._configs[config.id] = config

    def create_job(
        self,
        *,
        user_id: str,
        task_id: str,
        channel_config: ChannelConfig,
        template: NotificationTemplate,
        content: KnowledgeContent,
        idempotency_key: str | None = None,
    ) -> NotificationJob:
        """渲染具体知识点内容并创建 pending job（幂等）。"""
        self.register_config(channel_config)
        if not template.is_active:
            raise NotificationError("模板已停用", code="INVALID_STATE")

        # FR-07 两道防线：先校验内容具体性，再校验渲染结果确实含具体内容
        assert_concrete(content)
        renderer = TemplateRenderer(
            title_template=template.title_template,
            body_template=template.body_template,
            max_length=None,
            length_unit=template.length_unit,
            adaptive_mode="none",
        )
        rendered = renderer.render(build_context(content))
        validate_rendered_content(rendered.body, content)

        channel = self.registry.resolve(channel_config.channel_type)
        adapt_renderer = TemplateRenderer(
            title_template=template.title_template,
            body_template=template.body_template,
            max_length=_effective_limit(template, channel),
            length_unit=channel.length_unit,
            adaptive_mode=template.adaptive_mode,
        )
        segments = [
            replace(segment, review_url=content.review_url)
            for segment in adapt_renderer.adapt(rendered)
        ]

        key = idempotency_key or f"{user_id}:{task_id}:{channel_config.id}:{template.id}"
        existing = self.repository.find_by_idempotency_key(user_id, key)
        if existing is not None:
            return existing

        now = self.clock()
        job = NotificationJob(
            user_id=user_id,
            task_id=task_id,
            channel_config_id=channel_config.id,
            template_id=template.id,
            idempotency_key=key,
            rendered_title=rendered.title,
            rendered_body=rendered.body,
            max_attempts=self.retry_policy.max_attempts,
            next_attempt_at=now,
            created_at=now,
            updated_at=now,
            segments=segments,
            channel_type=channel_config.channel_type,
        )
        self.repository.save_job(job)
        return job

    def process(
        self,
        job: NotificationJob,
        *,
        now: datetime | None = None,
        channel_config: ChannelConfig | None = None,
    ) -> NotificationJob:
        """执行一次投递尝试；含状态机、delivery 追加、失败记录与退避。"""
        now = now or self.clock()
        config = channel_config or self._configs.get(job.channel_config_id)
        if config is None:
            raise NotificationError(
                f"找不到 job 对应的渠道配置 {job.channel_config_id}",
                code="CONFIG_MISSING",
            )
        if job.status != JobStatus.PENDING:
            raise NotificationError(f"job 状态 {job.status} 不可处理", code="INVALID_STATE")
        if job.next_attempt_at and now < job.next_attempt_at:
            return job  # 未到退避时间，保持 pending

        job.mark_processing(now)
        attempt_no = job.attempt_count + 1
        job.attempt_count = attempt_no
        channel = self.registry.resolve(config.channel_type)
        base_meta = {
            "job_id": job.id,
            "attempt_no": attempt_no,
            "channel_type": config.channel_type,
            "segments_count": len(job.segments),
        }
        delivery = NotificationDelivery.start(job, attempt_no, now, base_meta)
        started = time.monotonic()

        def elapsed_ms() -> int:
            return int((time.monotonic() - started) * 1000)

        try:
            last_result: SendResult | None = None
            for segment in job.segments:
                last_result = channel.send(segment, config, self.http, self.smtp)
                if not last_result.ok:
                    raise ChannelDeliveryError(
                        "渠道返回 ok=false",
                        retryable=True,
                        response_metadata=last_result.response_metadata,
                    )
            delivery.mark_sent(
                last_result.provider_message_id if last_result else None,
                last_result.response_metadata if last_result else {},
                elapsed_ms(),
            )
            job.mark_sent(now)
        except ConfigMissingError as exc:
            # 缺凭据：不可重试，直接 failed（绝不假推送）
            delivery.mark_failed(exc.code, str(exc), {}, elapsed_ms())
            job.mark_failed(exc.code, str(exc), now)
        except (EmptyContentError, TemplateRenderError) as exc:
            delivery.mark_failed(exc.code, str(exc), {}, elapsed_ms())
            job.mark_failed(exc.code, str(exc), now)
        except ChannelDeliveryError as exc:
            delivery.mark_failed(
                exc.error_code, str(exc), exc.response_metadata, elapsed_ms()
            )
            if should_retry(attempt_no, self.retry_policy, error_retryable=exc.retryable):
                nxt = next_attempt_at(now, attempt_no, self.retry_policy) or now
                job.mark_retry(nxt, exc.error_code, str(exc), now)
            else:
                job.mark_failed(exc.error_code, str(exc), now)
        except NotificationError as exc:
            delivery.mark_failed(exc.code, str(exc), {}, elapsed_ms())
            job.mark_failed(exc.code, str(exc), now)
        finally:
            self.repository.save_job(job)
            self.repository.append_delivery(delivery)
        return job

    def run_pending(self, *, now: datetime | None = None) -> list[NotificationJob]:
        now = now or self.clock()
        return [
            self.process(job, now=now)
            for job in self.repository.list_jobs(status=JobStatus.PENDING)
        ]

    def retry_failed(self, job_id: str, *, now: datetime | None = None) -> NotificationJob:
        """对应 POST /notification/jobs/{id}/retry：仅 failed 可重试。"""
        job = self.repository.get_job(job_id)
        if job is None:
            raise NotificationError("job 不存在", code="RESOURCE_NOT_FOUND")
        job.requeue(now or self.clock())
        self.repository.save_job(job)
        return job

    def history(self, job_id: str) -> dict:
        """推送历史与状态追踪：job 当前状态 + 全部 delivery 时间线。"""
        return {
            "job": self.repository.get_job(job_id),
            "deliveries": self.repository.list_deliveries(job_id),
        }
