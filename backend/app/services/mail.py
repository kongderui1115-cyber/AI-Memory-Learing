"""Persistent email test and review digest jobs using the channel transport port."""

import asyncio
import hashlib
import logging
from datetime import timedelta
from urllib.parse import urlencode, urlsplit
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select

from app.contracts.core import KnowledgeRead
from app.models import (
    ChapterJob,
    DailyReviewTask,
    KnowledgePoint,
    NotificationChannelConfig,
    NotificationDelivery,
    NotificationJob,
    NotificationTemplate,
    Subject,
    User,
    WorkspaceProfile,
)
from app.notifications.links import is_http_link
from app.notifications.template import char_sizer, truncate
from app.notifications.transports import SmtpEnvelope, SmtplibTransport
from app.services.common import ServiceError, lock_owner, owned, utcnow
from app.services.credentials import user_settings
from app.services.learning import task_contents

logger = logging.getLogger(__name__)


def schedule_lines(state, timezone: ZoneInfo) -> list[str]:
    if not state:
        return ["已复习 0 次 · 待调度", "当前阶段 待调度", "下次复习 暂未安排"]
    strategy = "FSRS" if state.strategy == "fsrs" else "固定间隔"
    if state.strategy == "fsrs":
        card = state.last_calculation.get("card")
        card_stage = card.get("state") if isinstance(card, dict) else None
        phase = {1: "学习中", 2: "复习中", 3: "重新学习"}.get(card_stage, "已安排")
    else:
        phase = f"第 {state.interval_index + 1} 阶段"
    return [
        f"已复习 {state.review_count} 次 · {strategy}",
        f"当前阶段 {phase}",
        "下次复习（当前计划）" + state.due_at.astimezone(timezone).strftime("%Y-%m-%d %H:%M %z"),
    ]


async def _digest_pitfalls(session, user_id, tasks) -> dict[str, list[str]]:
    chapters = select(KnowledgePoint.chapter_id).where(
        KnowledgePoint.user_id == user_id,
        KnowledgePoint.id.in_([task.knowledge_point_id for task in tasks]),
        KnowledgePoint.manual_revision.is_(False),
    )
    jobs = (
        select(
            ChapterJob.status,
            ChapterJob.result["analysis"]["knowledge_points"].label("points"),
            func.row_number().over(
                partition_by=ChapterJob.chapter_id,
                order_by=(ChapterJob.created_at.desc(), ChapterJob.id.desc()),
            ).label("position"),
        )
        .where(ChapterJob.user_id == user_id, ChapterJob.chapter_id.in_(chapters))
        .subquery()
    )
    rows = await session.scalars(
        select(jobs.c.points).where(jobs.c.position == 1, jobs.c.status == "succeeded")
    )
    result = {}
    for points in rows:
        if not isinstance(points, list):
            continue
        for point in points:
            if not isinstance(point, dict):
                continue
            point_id, pitfalls = point.get("knowledge_point_id"), point.get("pitfalls")
            if isinstance(point_id, str) and isinstance(pitfalls, list):
                result[point_id] = [
                    truncate(line, 220, char_sizer)
                    for line in pitfalls[:5]
                    if isinstance(line, str) and line.strip()
                ]
    return result


async def queue_email(db, settings, user_id, title, body, key, purpose):
    async with db.transaction() as session:
        await lock_owner(session, user_id)
        profile = await session.scalar(
            select(WorkspaceProfile).where(WorkspaceProfile.user_id == user_id)
        )
        channel = await session.scalar(
            select(NotificationChannelConfig).where(
                NotificationChannelConfig.user_id == user_id,
                NotificationChannelConfig.channel_type == "smtp",
                NotificationChannelConfig.is_enabled.is_(True),
            )
        )
        if not profile or not profile.email_enabled or channel is None:
            raise ServiceError("CONFIG_MISSING", "请先在设置中启用邮箱通知")
        existing = await session.scalar(
            select(NotificationJob).where(
                NotificationJob.user_id == user_id, NotificationJob.idempotency_key == key
            )
        )
        if existing:
            return {"id": existing.id, "status": existing.status}
        template = await session.scalar(
            select(NotificationTemplate).where(
                NotificationTemplate.user_id == user_id,
                NotificationTemplate.template_key == "email-review-v1",
            )
        )
        if template is None:
            template = NotificationTemplate(
                user_id=user_id,
                channel_type="smtp",
                template_key="email-review-v1",
                title_template="{title}",
                body_template="{body}",
                schema_variables=["title", "body"],
            )
            session.add(template)
            await session.flush()
        job = NotificationJob(
            user_id=user_id,
            task_id=None,
            channel_config_id=channel.id,
            template_id=template.id,
            purpose=purpose,
            idempotency_key=key,
            rendered_title=title,
            rendered_body=body,
            max_attempts=3,
        )
        session.add(job)
        await session.flush()
        return {"id": job.id, "status": job.status}


async def queue_test(db, settings, user_id, key):
    return await queue_email(
        db,
        settings,
        user_id,
        "AI 学习记忆系统 · 邮箱测试",
        "这是一封由你在邮箱设置中主动触发的测试邮件。\n\n后续复习邮件会包含知识点正文、解析、主动回忆问题、Notion来源及复习入口。",
        hashlib.sha256(("test:" + key).encode()).hexdigest(),
        "test",
    )


async def queue_digest(db, settings, user_id):
    async with db.transaction() as session:
        user = await session.get(User, user_id)
        profile = await session.scalar(
            select(WorkspaceProfile).where(WorkspaceProfile.user_id == user_id)
        )
        if not user or not user.is_active or not profile or not profile.email_enabled:
            return None
        timezone = ZoneInfo(user.timezone)
        snapshot = utcnow()
        now = snapshot.astimezone(timezone)
        if now.strftime("%H:%M") < profile.reminder_time:
            return None
        tasks = list(
            (
                await session.scalars(
                    select(DailyReviewTask)
                    .where(
                        DailyReviewTask.user_id == user_id,
                        DailyReviewTask.status.in_(["pending", "in_progress"]),
                        DailyReviewTask.scheduled_due_at <= snapshot,
                    )
                    .order_by(DailyReviewTask.scheduled_due_at)
                    .limit(100)
                )
            ).all()
        )
        if not tasks:
            return None
        subjects = {
            str(row.id): row.name
            for row in (
                await session.scalars(select(Subject).where(Subject.user_id == user_id))
            ).all()
        }
        pitfalls = await _digest_pitfalls(session, user_id, tasks)
        contents = await task_contents(session, user_id, tasks)
    public_url = settings.get("PUBLIC_APP_URL", "http://127.0.0.1:3030").rstrip("/")
    if not is_http_link(public_url) or urlsplit(public_url).query or urlsplit(public_url).fragment:
        raise ServiceError("CONFIG_MISSING", "PUBLIC_APP_URL 没有配置有效的学习系统入口")
    lines = [f"{user.display_name}，今天有 {len(tasks)} 个知识点等待复习。", ""]
    for task, content in zip(tasks, contents, strict=True):
        point = KnowledgeRead.model_validate(content["knowledge"])
        card, state = content["review_item"], content["schedule"]
        lines.extend(
            [
                point.title,
                "学科 " + subjects.get(str(point.subject_id), "未分类"),
                *schedule_lines(state, timezone),
                "",
                "知识正文（节选，全文见复习入口）" if len(point.body) > 1500 else "知识正文",
                truncate(point.body, 1500, char_sizer),
            ]
        )
        if card:
            lines.extend(
                [
                    "",
                    "主动回忆",
                    truncate(card.question, 500, char_sizer),
                    "",
                    "参考答案",
                    truncate(card.answer, 800, char_sizer),
                    "",
                    "解析",
                    truncate(card.explanation, 800, char_sizer),
                ]
            )
        if not point.manual_revision and pitfalls.get(str(point.id)):
            lines.extend(["", "易错点", *(f"• {line}" for line in pitfalls[str(point.id)])])
        if point.source_url and is_http_link(point.source_url):
            lines.extend(["", "Notion原始笔记", point.source_url])
        review_url = public_url + "/app?" + urlencode({"view": "review", "task": str(task.id)})
        lines.extend(
            ["", "进入复习", review_url, "", "─" * 40, ""]
        )
    return await queue_email(
        db,
        settings,
        user_id,
        f"今日复习 · {len(tasks)} 个知识点",
        "\n".join(lines),
        "digest:" + now.date().isoformat(),
        "digest",
    )


async def process_mail(db, settings, job_id, *, transport=None):
    now = utcnow()
    async with db.transaction() as session:
        job = await session.scalar(
            select(NotificationJob).where(NotificationJob.id == job_id).with_for_update()
        )
        if job is None or job.status not in {"pending", "processing"}:
            return {"status": "skipped"}
        if job.status == "processing" and job.locked_until and job.locked_until > now:
            return {"status": "busy"}
        if job.next_attempt_at and job.next_attempt_at > now:
            return {"status": "deferred"}
        channel = await owned(
            session, NotificationChannelConfig, job.channel_config_id, job.user_id
        )
        if channel.channel_type != "smtp":
            return {"status": "unsupported"}
        user = await session.get(User, job.user_id)
        profile = await session.scalar(
            select(WorkspaceProfile).where(WorkspaceProfile.user_id == job.user_id)
        )
        if not user.is_active or not channel.is_enabled or not profile or not profile.email_enabled:
            job.status, job.locked_until = "cancelled", None
            return {"status": "cancelled"}
        if job.status == "processing":
            previous = await session.scalar(
                select(NotificationDelivery)
                .where(
                    NotificationDelivery.job_id == job.id,
                    NotificationDelivery.attempt_no == job.attempt_count,
                    NotificationDelivery.status == "sending",
                )
                .with_for_update()
            )
            if previous:
                previous.status = "failed"
                previous.error_code = "DELIVERY_UNCERTAIN"
                previous.error_message = "发送进程中断，邮件服务器接收结果待核对"
        if job.attempt_count >= job.max_attempts:
            job.status, job.locked_until, job.next_attempt_at = "failed", None, None
            job.last_error_code = "RETRY_EXHAUSTED"
            job.last_error_message = "已达到邮件发送尝试上限，请检查发送记录"
            return {"status": "failed"}
        job.status, job.locked_until = "processing", now + timedelta(minutes=2)
        job.attempt_count += 1
        attempt = job.attempt_count
        delivery = NotificationDelivery(
            user_id=job.user_id,
            job_id=job.id,
            attempt_no=attempt,
            status="sending",
            attempted_at=now,
        )
        session.add(delivery)
        await session.flush()
        delivery_id, user_id, credential_ref = delivery.id, job.user_id, channel.credential_ref
        config, recipient = dict(profile.email_settings), profile.recipient_email
        title, body = job.rendered_title, job.rendered_body
    try:
        effective = await user_settings(db, settings, user_id)
        password = effective.get(credential_ref)
        if not password:
            raise ServiceError("CONFIG_MISSING", "邮箱凭据尚未配置")
        from app.services.workspace import SMTP_PRESETS

        allowed = {value[0] for value in SMTP_PRESETS.values()}
        allowed.update(
            value.strip().lower() for value in settings.get("SMTP_ALLOWED_HOSTS").split(",")
        )
        if config["host"].lower() not in allowed:
            raise ServiceError("FORBIDDEN", "SMTP服务器尚未获准")
        envelope = SmtpEnvelope(
            host=config["host"],
            port=config["port"],
            user=config["username"],
            password=password,
            from_addr=config["username"],
            to_addrs=[recipient],
            subject=title,
            body=body,
            message_id=f"<{job_id}@memory-os.local>",
            use_tls=config["security"] == "starttls",
            use_ssl=config["security"] == "ssl",
            timeout=20,
        )
        result = await asyncio.to_thread((transport or SmtplibTransport()).send, envelope)
        ok, retryable = result.ok, result.retryable
        code = None if ok else (result.error_code or "EXTERNAL_SERVICE_ERROR")
        message_id = result.provider_message_id
    except Exception as error:  # noqa: BLE001 - preserve retry state and keep the worker running
        ok, retryable, code, message_id = (
            False,
            False,
            getattr(error, "code", "EXTERNAL_SERVICE_ERROR"),
            None,
        )
    async with db.transaction() as session:
        job = await owned(session, NotificationJob, job_id, user_id, lock=True)
        delivery = await owned(session, NotificationDelivery, delivery_id, user_id, lock=True)
        delivery.status = "sent" if ok else "failed"
        delivery.duration_ms = int((utcnow() - now).total_seconds() * 1000)
        delivery.error_code, delivery.provider_message_id = code, message_id
        delivery.response_metadata = {
            "transport": "smtp",
            "provider_accepted": True if ok else None,
            "final_delivery": "unconfirmed",
        }
        delivery.error_message = None if ok else "邮件发送失败，请检查授权码、邮箱设置和网络"
        # A delayed worker may finish after a newer lease has already claimed this job.
        if job.attempt_count != attempt or job.status != "processing":
            return {"status": "superseded"}
        job.locked_until = None
        if ok:
            job.status, job.sent_at = "sent", utcnow()
            job.last_error_code, job.last_error_message, job.next_attempt_at = None, None, None
        else:
            job.last_error_code, job.last_error_message = code, delivery.error_message
            job.status = "pending" if retryable and attempt < job.max_attempts else "failed"
            job.next_attempt_at = (
                utcnow() + timedelta(seconds=30 * 2**attempt) if job.status == "pending" else None
            )
    return {"status": "sent" if ok else "failed"}


async def send_pending(db, settings):
    async with db.transaction() as session:
        ids = list(
            (
                await session.scalars(
                    select(NotificationJob.id)
                    .join(
                        NotificationChannelConfig,
                        NotificationChannelConfig.id == NotificationJob.channel_config_id,
                    )
                    .where(
                        NotificationChannelConfig.channel_type == "smtp",
                        or_(
                            (NotificationJob.status == "pending")
                            & or_(
                                NotificationJob.next_attempt_at.is_(None),
                                NotificationJob.next_attempt_at <= utcnow(),
                            ),
                            (NotificationJob.status == "processing")
                            & (NotificationJob.locked_until <= utcnow()),
                        ),
                    )
                    .order_by(NotificationJob.created_at)
                    .limit(100)
                )
            ).all()
        )
    return [await process_mail(db, settings, job_id) for job_id in ids]


async def send_daily_digest(db, settings):
    async with db.transaction() as session:
        ids = list(
            (
                await session.scalars(
                    select(WorkspaceProfile.user_id)
                    .join(User, User.id == WorkspaceProfile.user_id)
                    .where(WorkspaceProfile.email_enabled.is_(True), User.is_active.is_(True))
                )
            ).all()
        )
    failures = 0
    for user_id in ids:
        try:
            await queue_digest(db, settings, user_id)
        except Exception as error:  # noqa: BLE001 - one account must not block the others
            failures += 1
            logger.warning(
                "Digest queue failure user_id=%s type=%s",
                user_id,
                type(error).__name__,
            )
    outcomes = await send_pending(db, settings)
    return {
        "status": "failed"
        if failures or any(result["status"] == "failed" for result in outcomes)
        else "succeeded",
        "count": sum(result["status"] == "sent" for result in outcomes),
    }
