"""Guided configuration for a signed-in user. Secrets never appear in read responses."""

import asyncio
import hashlib
import re
from urllib.parse import urlparse
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import func, select

from app.ai.errors import AIIntegrationError
from app.contracts.ai_runtime import ProviderWrite
from app.contracts.core import UserAccount
from app.contracts.notion import IntegrationWrite, SourceWrite
from app.integrations.notion.client import NOTION_API_BASE
from app.integrations.notion.runtime import RuntimeNotionClient
from app.models import (
    AIProviderConfig,
    Chapter,
    ChapterJob,
    KnowledgePoint,
    NotificationChannelConfig,
    NotificationJob,
    NotionDataSource,
    NotionIntegration,
    Subject,
    SyncRun,
    User,
    UserSecret,
    WorkspaceProfile,
)
from app.security import hash_password
from app.services import accounts, ai_runtime, notion
from app.services.common import ServiceError, check_version, lock_owner, utcnow
from app.services.credentials import save_secret, user_settings

SMTP_PRESETS = {
    "qq": ("smtp.qq.com", 465, "ssl"),
    "163": ("smtp.163.com", 465, "ssl"),
    "gmail": ("smtp.gmail.com", 465, "ssl"),
    "outlook": ("smtp.office365.com", 587, "starttls"),
}


def reference(user_id, kind):
    return "MEMORY_USER_" + user_id.hex.upper() + "_" + kind


def validated_config(model, **values):
    try:
        return model(**values)
    except ValidationError:
        raise ServiceError(
            "VALIDATION_ERROR", "配置格式不正确，请检查资料库映射或模型字段"
        ) from None


async def profile_for(session, user_id):
    row = await session.scalar(select(WorkspaceProfile).where(WorkspaceProfile.user_id == user_id))
    if row is None:
        user = await session.get(User, user_id)
        row = WorkspaceProfile(user_id=user_id, recipient_email=user.email)
        session.add(row)
        await session.flush()
    return row


def profile_view(profile, user):
    return {
        "version": profile.version,
        "recipient_email": profile.recipient_email,
        "reminder_time": profile.reminder_time,
        "timezone": user.timezone,
        "email_enabled": profile.email_enabled,
        "email_settings": profile.email_settings,
        "review_preferences": profile.review_preferences,
        "ai_billing_approved": profile.ai_billing_approved,
        "onboarding_step": profile.onboarding_step,
        "onboarding_completed_at": profile.onboarding_completed_at,
    }


async def processing(db, settings, user_id):
    async with db.transaction() as session:
        runs = await session.scalars(
            select(SyncRun)
            .where(SyncRun.user_id == user_id)
            .order_by(SyncRun.created_at.desc(), SyncRun.id.desc())
            .limit(25)
        )
        latest_job = (
            select(ChapterJob.id)
            .where(ChapterJob.chapter_id == Chapter.id, ChapterJob.user_id == user_id)
            .order_by(ChapterJob.created_at.desc(), ChapterJob.id.desc())
            .limit(1)
            .correlate(Chapter)
            .scalar_subquery()
        )
        notes = await session.execute(
            select(Chapter, ChapterJob)
            .outerjoin(ChapterJob, ChapterJob.id == latest_job)
            .where(Chapter.user_id == user_id, Chapter.external_page_id.is_not(None))
            .order_by(Chapter.updated_at.desc(), Chapter.id.desc())
            .limit(25)
        )
        result = []
        for chapter, job in notes:
            row = {
                "chapter_id": chapter.id,
                "title": chapter.title,
                "source_url": chapter.source_url,
                "learning_status": chapter.status,
                "notion_archived_at": chapter.notion_archived_at,
            }
            if job:
                analysis = job.result.get("analysis") or {}
                row.update(
                    job_id=job.id, status=job.status, error_code=job.error_code,
                    next_attempt_at=job.next_attempt_at,
                    note_summary=analysis.get("note_summary"),
                    information_sufficient=analysis.get("information_sufficient"),
                    limitations=analysis.get("limitations", []),
                    knowledge_point_ids=job.result.get("knowledge_point_ids", []),
                    evidence=analysis.get("knowledge_points", []),
                )
            result.append(row)
        return {
            "automatic_processing_enabled": settings.background_tasks_enabled,
            "sync_runs": [
                {
                    "id": run.id, "source_id": run.data_source_id, "status": run.status,
                    "imported": run.items_imported, "attempt": run.attempt,
                    "finished_at": run.finished_at, "next_retry_at": run.next_retry_at,
                    "error_code": run.error_code,
                }
                for run in runs
            ],
            "notes": result,
        }


async def register(db, body, ip, request_id):
    encoded = await asyncio.to_thread(hash_password, body.password)
    async with db.transaction() as session:
        throttle, limited = await accounts._throttle(
            session, "register:" + hashlib.sha256(ip.encode()).hexdigest(), utcnow(), 60
        )
        if limited or throttle.failures >= 10:
            return None, "RATE_LIMITED"
        throttle.failures += 1
        email = str(body.email).casefold()
        await session.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(email, 733))))
        if await session.scalar(select(User.id).where(User.email == email)):
            return None, "DUPLICATE_RESOURCE"
        user = User(
            email=email,
            display_name=body.display_name.strip(),
            timezone="Asia/Shanghai",
            password_hash=encoded,
            role="user",
        )
        session.add(user)
        await session.flush()
        await profile_for(session, user.id)
        accounts.audit(session, user, "registration", "account", "created", ip, request_id, user.id)
    return user.id, None


async def settings_read(db, user_id):
    async with db.transaction() as session:
        user = await lock_owner(session, user_id)
        profile = await profile_for(session, user_id)
        secrets = set(
            (
                await session.scalars(select(UserSecret.name).where(UserSecret.user_id == user_id))
            ).all()
        )
        sources = list(
            (
                await session.scalars(
                    select(NotionDataSource)
                    .where(NotionDataSource.user_id == user_id)
                    .order_by(NotionDataSource.created_at)
                )
            ).all()
        )
        provider = await session.scalar(
            select(AIProviderConfig).where(
                AIProviderConfig.user_id == user_id, AIProviderConfig.is_default.is_(True)
            )
        )
        return {
            "user": UserAccount.model_validate(user),
            "profile": profile_view(profile, user),
            "notion_configured": reference(user_id, "NOTION_TOKEN") in secrets,
            "smtp_configured": reference(user_id, "SMTP_PASSWORD") in secrets,
            "model_key_configured": bool(provider and provider.credential_ref in secrets),
            "sources": [
                {
                    "id": row.id,
                    "name": row.name,
                    "subject_id": row.subject_id,
                    "external_source_id": row.external_source_id,
                    "source_type": row.source_type,
                    "status_property": row.status_property,
                    "status_mapping": row.status_mapping,
                    "last_sync_at": row.last_edited_watermark,
                    "enabled": row.is_enabled,
                }
                for row in sources
            ],
            "model": {
                "provider": provider.provider,
                "model_name": provider.model_name,
                "base_url": provider.base_url,
                "version": provider.version,
            }
            if provider
            else None,
            "channels": [
                {"id": "smtp", "name": "邮箱", "available": True},
                {"id": "wechat", "name": "微信", "available": False},
                {"id": "feishu", "name": "飞书", "available": False},
                {"id": "dingtalk", "name": "钉钉", "available": False},
            ],
        }


async def save_profile(db, user_id, body, version):
    async with db.transaction() as session:
        user = await lock_owner(session, user_id)
        profile = await profile_for(session, user_id)
        check_version(profile, version)
        profile.recipient_email, profile.reminder_time = (
            str(body.recipient_email),
            body.reminder_time,
        )
        profile.onboarding_step = max(profile.onboarding_step, body.onboarding_step)
        user.timezone = body.timezone
        profile.version += 1
        return profile_view(profile, user)


async def save_memory_preferences(db, user_id, body, version):
    async with db.transaction() as session:
        user = await lock_owner(session, user_id)
        profile = await profile_for(session, user_id)
        check_version(profile, version)
        profile.review_preferences = body.model_dump()
        profile.version += 1
        return profile_view(profile, user)


async def save_email(db, settings, user_id, body, version):
    if body.provider in SMTP_PRESETS:
        host, port, security = SMTP_PRESETS[body.provider]
    else:
        host, port, security = body.host, body.port, body.security
        allowed = {
            value.strip().lower()
            for value in settings.get("SMTP_ALLOWED_HOSTS").split(",")
            if value.strip()
        }
        if not host or host.lower() not in allowed:
            raise ServiceError("VALIDATION_ERROR", "请选择邮箱服务商，自定义服务器需由管理员启用")
    async with db.transaction() as session:
        await lock_owner(session, user_id)
        profile = await profile_for(session, user_id)
        check_version(profile, version)
        credential_ref = reference(user_id, "SMTP_PASSWORD")
        secret = await session.scalar(
            select(UserSecret.id).where(
                UserSecret.user_id == user_id, UserSecret.name == credential_ref
            )
        )
        if body.password:
            await save_secret(session, settings, user_id, credential_ref, body.password)
        elif not secret and body.enabled:
            raise ServiceError("VALIDATION_ERROR", "请填写邮箱授权码或SMTP密码")
        profile.email_settings = {
            "provider": body.provider,
            "host": host,
            "port": port,
            "security": security,
            "username": str(body.username),
        }
        profile.email_enabled = body.enabled
        profile.version += 1
        channel = await session.scalar(
            select(NotificationChannelConfig).where(
                NotificationChannelConfig.user_id == user_id,
                NotificationChannelConfig.channel_type == "smtp",
            )
        )
        if channel is None:
            channel = NotificationChannelConfig(
                user_id=user_id,
                name="邮箱复习通知",
                channel_type="smtp",
                credential_ref=credential_ref,
                is_default=True,
            )
            session.add(channel)
        channel.is_enabled, channel.settings = body.enabled, profile.email_settings
    return await settings_read(db, user_id)


async def save_notion_token(db, settings, user_id, token):
    credential_ref = reference(user_id, "NOTION_TOKEN")
    async with db.transaction() as session:
        await lock_owner(session, user_id)
        await save_secret(session, settings, user_id, credential_ref, token.strip())
        profile = await profile_for(session, user_id)
        profile.version += 1
        integration = await session.scalar(
            select(NotionIntegration).where(
                NotionIntegration.user_id == user_id,
                NotionIntegration.credential_ref == credential_ref,
            )
        )
        integration_id = integration.id if integration else None
        integration_version = integration.version if integration else None
    return await notion.save_integration(
        db,
        settings,
        user_id,
        IntegrationWrite(name="我的Notion", credential_ref=credential_ref),
        str(uuid4()),
        resource_id=integration_id,
        version=integration_version,
    )


async def discover_sources(db, settings, user_id, query="", transport=None):
    settings = await user_settings(db, settings, user_id)
    token = settings.get(reference(user_id, "NOTION_TOKEN"))
    if not token:
        raise ServiceError("CONFIG_MISSING", "请先保存Notion Token")
    client = RuntimeNotionClient(token=token, api_version="2026-03-11", transport=transport)
    try:
        response = await asyncio.to_thread(
            client._request_json,
            "POST",
            NOTION_API_BASE + "/search",
            {
                "query": query,
                "filter": {"value": "data_source", "property": "object"},
                "page_size": 100,
            },
        )
        rows = []
        for item in response.get("results", []):
            properties = []
            for name, prop in item.get("properties", {}).items():
                kind = prop.get("type")
                options = (
                    (prop.get(kind) or {}).get("options", [])
                    if kind in {"status", "select"}
                    else []
                )
                properties.append(
                    {"name": name, "type": kind, "options": [o["name"] for o in options]}
                )
            rows.append(
                {
                    "id": item["id"],
                    "name": "".join(
                        t.get("plain_text", t.get("text", {}).get("content", ""))
                        for t in item.get("title", [])
                    )
                    or "未命名资料库",
                    "properties": properties,
                }
            )
        return {"items": rows, "has_more": bool(response.get("has_more"))}
    except AIIntegrationError:
        raise ServiceError(
            "EXTERNAL_SERVICE_ERROR", "读取Notion失败，请检查Token并将资料库授权给连接"
        ) from None


def external_id(value):
    candidate = urlparse(value).path if "://" in value else value
    ids = re.findall(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|[0-9a-fA-F]{32}",
        candidate,
    )
    if not ids:
        raise ServiceError("VALIDATION_ERROR", "请粘贴Notion资料库链接或选择已授权资料库")
    return UUID(ids[-1])


async def connect_notion(db, settings, user_id, body):
    identifier = external_id(body.external_id)
    async with db.transaction() as session:
        await lock_owner(session, user_id)
        integration = await session.scalar(
            select(NotionIntegration).where(
                NotionIntegration.user_id == user_id,
                NotionIntegration.credential_ref == reference(user_id, "NOTION_TOKEN"),
            )
        )
        if integration is None:
            raise ServiceError("CONFIG_MISSING", "请先保存Notion Token")
        subject = await session.scalar(
            select(Subject).where(Subject.user_id == user_id, Subject.name == body.subject_name)
        )
        if subject is None:
            subject = Subject(
                user_id=user_id, name=body.subject_name, slug="subject-" + uuid4().hex[:16]
            )
            session.add(subject)
            await session.flush()
        existing = await session.scalar(
            select(NotionDataSource).where(
                NotionDataSource.integration_id == integration.id,
                NotionDataSource.external_source_id == str(identifier),
            )
        )
        source_id, version = (existing.id, existing.version) if existing else (None, None)
        request = validated_config(
            SourceWrite,
            integration_id=integration.id,
            subject_id=subject.id,
            external_source_id=identifier,
            source_type=body.source_type,
            name=body.name,
            status_property=body.status_property,
            status_mapping=body.status_mapping,
        )
    source = await notion.save_source(
        db, settings, user_id, request, str(uuid4()), resource_id=source_id, version=version
    )
    return await notion.enqueue_sync(db, settings, user_id, source.id, str(uuid4()))


async def save_model(db, settings, user_id, body):
    kind = "openai_compatible" if body.provider == "kimi" else body.provider
    base_url = "https://api.moonshot.cn/v1" if body.provider == "kimi" else body.base_url
    model_name = "我的学习模型"
    legacy_ref = reference(user_id, "AI_KEY")
    async with db.transaction() as session:
        await lock_owner(session, user_id)
        provider = await session.scalar(
            select(AIProviderConfig)
            .where(AIProviderConfig.user_id == user_id, AIProviderConfig.name == model_name)
            .with_for_update()
        )
        request = validated_config(
            ProviderWrite,
            name=model_name,
            provider=kind,
            model_name=body.model_name,
            base_url=base_url,
            credential_ref=legacy_ref,
            is_default=True,
        )
        values = request.model_dump()
        values["provider"] = str(request.provider)
        values["base_url"] = str(request.base_url).rstrip("/") if request.base_url else None
        candidate = AIProviderConfig(id=provider.id if provider else uuid4(), user_id=user_id, **values)
        target = ai_runtime.provider_settings(candidate, settings)
        target.validate()
        if body.api_key:
            ref = ai_runtime.model_secret_prefix(user_id, target) + uuid4().hex.upper()
            await save_secret(session, settings, user_id, ref, body.api_key)
        elif provider:
            current = ai_runtime.provider_settings(provider, settings)
            current_address = ai_runtime.model_destination(current.provider, current.base_url)
            target_address = ai_runtime.model_destination(target.provider, target.base_url)
            if current_address != target_address:
                raise ServiceError("VALIDATION_ERROR", "切换模型服务地址时，请填写对应的 API Key")
            ref = current.credential_ref
        else:
            ref = ai_runtime.model_secret_prefix(user_id, target) + uuid4().hex.upper()
        candidate.credential_ref = values["credential_ref"] = ref
        await ai_runtime.set_default_provider(session, candidate)
        if provider:
            for name, value in values.items():
                setattr(provider, name, value)
            provider.version += 1
        else:
            session.add(candidate)
        profile = await profile_for(session, user_id)
        profile.ai_billing_approved = body.billing_approved
        profile.version += 1
        if settings.ai_billing_approved and body.billing_approved:
            jobs = await session.scalars(
                select(ChapterJob).where(ChapterJob.user_id == user_id, ChapterJob.status == "blocked")
            )
            for job in jobs:
                job.status, job.error_code = "pending", None
    return await settings_read(db, user_id)


async def finish(db, user_id):
    async with db.transaction() as session:
        await lock_owner(session, user_id)
        profile = await profile_for(session, user_id)
        profile.onboarding_completed_at = profile.onboarding_completed_at or utcnow()
        profile.onboarding_step = 4
        profile.version += 1


async def overview(db, user_id):
    result = await settings_read(db, user_id)
    async with db.transaction() as session:
        subjects = list(
            (
                await session.scalars(
                    select(Subject).where(Subject.user_id == user_id).order_by(Subject.created_at)
                )
            ).all()
        )
        chapters = list(
            (
                await session.scalars(
                    select(Chapter)
                    .where(Chapter.user_id == user_id)
                    .order_by(Chapter.updated_at.desc())
                    .limit(100)
                )
            ).all()
        )
        counts = dict(
            (
                await session.execute(
                    select(KnowledgePoint.subject_id, func.count())
                    .where(KnowledgePoint.user_id == user_id, KnowledgePoint.status == "active")
                    .group_by(KnowledgePoint.subject_id)
                )
            ).all()
        )
        jobs = list(
            (
                await session.scalars(
                    select(NotificationJob)
                    .where(NotificationJob.user_id == user_id)
                    .order_by(NotificationJob.created_at.desc())
                    .limit(20)
                )
            ).all()
        )
        syncs = list(
            (
                await session.scalars(
                    select(SyncRun)
                    .where(SyncRun.user_id == user_id)
                    .order_by(SyncRun.created_at.desc())
                    .limit(10)
                )
            ).all()
        )
        result.update(
            {
                "subjects": [
                    {"id": s.id, "name": s.name, "count": counts.get(s.id, 0)} for s in subjects
                ],
                "chapters": [
                    {
                        "id": c.id,
                        "subject_id": c.subject_id,
                        "title": c.title,
                        "status": c.status,
                        "content": c.content,
                        "source_url": c.source_url,
                        "version": c.version,
                    }
                    for c in chapters
                ],
                "knowledge_total": sum(counts.values()),
                "mail_history": [
                    {
                        "id": j.id,
                        "title": j.rendered_title,
                        "status": j.status,
                        "attempts": j.attempt_count,
                        "error_code": j.last_error_code,
                        "sent_at": j.sent_at,
                        "created_at": j.created_at,
                    }
                    for j in jobs
                ],
                "sync_history": [
                    {
                        "id": s.id,
                        "status": s.status,
                        "imported": s.items_imported,
                        "created_at": s.created_at,
                        "error": s.error_message,
                    }
                    for s in syncs
                ],
            }
        )
    return result
