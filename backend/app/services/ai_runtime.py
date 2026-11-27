"""Persistent model configuration, call audit and completed-chapter processing."""

import asyncio
import hashlib
import json
from collections import Counter
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import func, or_, select, update

from app.ai.config import AIProviderConfig as ProviderSettings
from app.ai.config import DEFAULT_BASE_URLS, assert_ready
from app.ai.extraction import (
    build_extraction_request,
    dedupe_knowledge_points,
    parse_extraction_output,
)
from app.ai.generation import build_generation_request, parse_generation_output
from app.ai.grounding import GROUNDED_SCHEMA_HINT, parse_grounding, request_grounding
from app.ai.ports import GenerationMeta
from app.ai.service import AIExecutionService
from app.ai.strategies import default_strategy, strategy_from_mapping
from app.contracts.core import ChapterJobRead
from app.contracts.models import AIProviderConfigRead, SubjectStrategyRead
from app.domain import memory
from app.models import (
    AICallLog,
    AIProviderConfig,
    Chapter,
    ChapterJob,
    DailyReviewTask,
    KnowledgePoint,
    KnowledgePointSource,
    RawNote,
    ReviewItem,
    Subject,
    SubjectStrategy,
    User,
    WorkspaceProfile,
)
from app.services.common import (
    ServiceError,
    check_version,
    lock_owner,
    owned,
    remember,
    replay,
    utcnow,
)
from app.services.credentials import load_user_settings
from app.services.learning import (
    chapter_content_hash,
    chapter_job_cancellation,
    initialize_schedule,
    knowledge_hash,
    refreshed,
)
from app.services.notion import check_credential_ref
from app.services.notion_knowledge import hold_missing_points, revision_points
from app.services.review_workload import OPEN_TASK_STATUSES

DEFAULT_ENDPOINTS = (
    "https://api.openai.com/v1",
    "https://api.deepseek.com/v1",
    "https://api.moonshot.cn/v1",
    "https://api.moonshot.ai/v1",
)

CONFIGURATION_CHECK_INTERVAL = timedelta(minutes=10)


def model_destination(provider, base_url):
    return provider, (base_url or DEFAULT_BASE_URLS.get(provider, "")).rstrip("/")


def model_secret_prefix(user_id, config):
    destination = json.dumps(model_destination(config.provider, config.base_url), separators=(",", ":"))
    digest = hashlib.sha256(destination.encode()).hexdigest().upper()
    return f"MEMORY_USER_{user_id.hex.upper()}_AI_DEST_{digest}_"


def provider_settings(row, settings):
    values = {
        name: getattr(row, name)
        for name in ProviderSettings.__dataclass_fields__
        if name != "config_id"
    }
    values["temperature"] = float(values["temperature"])
    config = ProviderSettings(config_id=str(row.id), **values)
    endpoint = config.resolved_base_url().rstrip("/")
    allowed = settings.get("AI_ALLOWED_BASE_URLS", ",".join(DEFAULT_ENDPOINTS)).split(",")
    if endpoint not in {value.strip().rstrip("/") for value in allowed}:
        raise ServiceError("FORBIDDEN", "模型地址需要由服务端 AI_ALLOWED_BASE_URLS 授权")
    check_credential_ref(row.user_id, config.credential_ref)
    suffix = config.credential_ref.removeprefix(f"MEMORY_USER_{row.user_id.hex.upper()}_")
    if suffix in {"NOTION_TOKEN", "SMTP_PASSWORD"}:
        raise ServiceError("FORBIDDEN", "模型必须使用专用凭据")
    if suffix.startswith("AI_DEST_") and not config.credential_ref.startswith(
        model_secret_prefix(row.user_id, config)
    ):
        raise ServiceError("FORBIDDEN", "模型凭据与服务地址不匹配，请重新配置")
    return config


async def set_default_provider(session, row):
    await session.execute(
        update(AIProviderConfig)
        .where(
            AIProviderConfig.user_id == row.user_id,
            AIProviderConfig.id != row.id,
            AIProviderConfig.is_default.is_(True),
        )
        .values(is_default=False, version=AIProviderConfig.version + 1)
    )


async def check_destination_binding(session, user_id, config):
    if config.credential_ref.startswith(model_secret_prefix(user_id, config)):
        return
    target = model_destination(config.provider, config.base_url)
    destinations = await session.execute(
        select(AIProviderConfig.provider, AIProviderConfig.base_url).where(
            AIProviderConfig.user_id == user_id,
            AIProviderConfig.credential_ref == config.credential_ref,
        )
    )
    if any(model_destination(provider, base_url) != target for provider, base_url in destinations):
        raise ServiceError("VALIDATION_ERROR", "模型凭据已用于不同的服务地址，请设置专用凭据")


async def save_provider(db, settings, user_id, body, key=None, *, resource_id=None, version=None):
    check_credential_ref(user_id, body.credential_ref)
    values = body.model_dump()
    values["provider"] = str(body.provider)
    values["base_url"] = str(body.base_url).rstrip("/") if body.base_url else None
    candidate = AIProviderConfig(id=resource_id or uuid4(), user_id=user_id, **values)
    config = provider_settings(candidate, settings)
    config.validate()
    if body.is_default and not body.is_enabled:
        raise ServiceError("VALIDATION_ERROR", "默认模型需要启用")
    async with db.transaction() as session:
        await lock_owner(session, user_id)
        if resource_id:
            row = await owned(session, AIProviderConfig, resource_id, user_id, lock=True)
            check_version(row, version)
        else:
            previous, digest = await replay(
                session,
                user_id,
                "ai:provider",
                key,
                body.model_dump(mode="json"),
                settings.secret_key,
            )
            if previous:
                return AIProviderConfigRead.model_validate(
                    await owned(session, AIProviderConfig, previous.resource_id, user_id)
                )
            row = candidate
        await check_destination_binding(session, user_id, config)
        if body.is_default:
            await set_default_provider(session, candidate)
        if resource_id:
            for name, value in values.items():
                setattr(row, name, value)
            row.version += 1
        else:
            session.add(row)
            await session.flush()
            remember(session, user_id, "ai:provider", key, digest, row.id)
        return await refreshed(session, row, AIProviderConfigRead)


async def save_strategy(db, user_id, subject_id, body, version):
    values = body.model_dump(mode="json")
    strategy_from_mapping({**values, "subject_id": str(subject_id)})
    overrides = values["scheduler_overrides"]
    try:
        memory.initial_state(overrides.get("strategy", "fsrs"), utcnow(), overrides)
        if "intervals_days" in overrides:
            memory.initial_state("ebbinghaus", utcnow(), overrides)
    except (ValueError, TypeError, OverflowError):
        raise ServiceError("VALIDATION_ERROR", "学科调度参数不正确") from None
    async with db.transaction() as session:
        await lock_owner(session, user_id)
        await owned(session, Subject, subject_id, user_id)
        row = await session.scalar(
            select(SubjectStrategy).where(
                SubjectStrategy.subject_id == subject_id, SubjectStrategy.is_active.is_(True)
            )
        )
        if row is None:
            if version is not None:
                raise ServiceError("VERSION_CONFLICT", "策略不存在，请重新读取")
            row = SubjectStrategy(user_id=user_id, subject_id=subject_id, **values)
            session.add(row)
        else:
            check_version(row, version)
            for name, value in values.items():
                setattr(row, name, value)
            row.version += 1
        return await refreshed(session, row, SubjectStrategyRead)


async def reanalyze_chapter(db, settings, user_id, chapter_id, key):
    operation = f"ai:chapter:{chapter_id}:reanalyze"
    async with db.transaction() as session:
        await lock_owner(session, user_id)
        previous, digest = await replay(
            session, user_id, operation, key, {}, settings.secret_key
        )
        if previous:
            job = await owned(session, ChapterJob, previous.resource_id, user_id)
            return ChapterJobRead.model_validate(job)
        chapter = await owned(session, Chapter, chapter_id, user_id, lock=True)
        if chapter.notion_archived_at is not None or chapter.status != "completed":
            raise ServiceError("INVALID_STATE", "只能重新分析有效且已完成的章节")
        content_hash = chapter_content_hash(chapter)
        job = await session.scalar(
            select(ChapterJob)
            .where(ChapterJob.chapter_id == chapter.id, ChapterJob.content_hash == content_hash)
            .with_for_update()
        )
        if job is None:
            job = ChapterJob(
                user_id=user_id, chapter_id=chapter.id, content_hash=content_hash
            )
            session.add(job)
        if job.status not in {"pending", "running"}:
            job.status, job.error_code, job.next_attempt_at = "pending", None, None
            job.attempt = 0
            # Explicit reanalysis should make a fresh request. Retries reuse its own result.
            job.result = {**(job.result or {}), "request_nonce": str(uuid4())}
        await session.flush()
        remember(session, user_id, operation, key, digest, job.id)
        return ChapterJobRead.model_validate(job)


async def call_model(
    db, settings, user_id, config, request, job_id, *, provider_version, transport=None,
    request_nonce=None,
):
    """Save success output before applying business writes, allowing recovery without another call."""
    payload = json.dumps(
        [
            request.operation,
            request.prompt_version,
            request.system,
            request.user,
            config.model_name,
            config.resolved_base_url(),
            config.temperature,
        ] + ([request_nonce] if request_nonce else []),
        ensure_ascii=False,
        sort_keys=True,
    )
    fingerprint = hashlib.sha256(payload.encode()).hexdigest()
    async with db.transaction() as session:
        provider = await owned(session, AIProviderConfig, config.config_id, user_id, lock=True)
        if not provider.is_enabled or provider.version != provider_version:
            raise ServiceError("VERSION_CONFLICT", "模型配置已变化，请重试")
        if provider_settings(provider, settings) != config:
            raise ServiceError("VERSION_CONFLICT", "模型地址或凭据已变化，请重试")
        await check_destination_binding(session, user_id, config)
        effective = await load_user_settings(
            session, settings, user_id, credential_ref=config.credential_ref
        )
        env = dict(effective.raw, AI_BILLING_APPROVED=str(effective.ai_billing_approved).lower())
        assert_ready(config, env)
        previous = await session.scalar(
            select(AICallLog)
            .where(
                AICallLog.user_id == user_id,
                AICallLog.provider_config_id == config.config_id,
                AICallLog.status == "succeeded",
                AICallLog.call_metadata["job_id"].astext == str(job_id),
                AICallLog.call_metadata["fingerprint"].astext == fingerprint,
            )
            .order_by(AICallLog.created_at.desc())
            .limit(1)
        )
        if previous and "parsed_result" in previous.call_metadata:
            return previous.call_metadata["parsed_result"], previous.id
        if config.rate_limit_per_minute:
            recent = await session.scalar(
                select(func.count(AICallLog.id)).where(
                    AICallLog.provider_config_id == config.config_id,
                    AICallLog.created_at >= utcnow() - timedelta(minutes=1),
                )
            )
            if recent >= config.rate_limit_per_minute:
                raise ServiceError("RATE_LIMITED", "模型调用达到每分钟限额")
        row = AICallLog(
            user_id=user_id,
            provider_config_id=config.config_id,
            operation=request.operation,
            provider=config.provider,
            model_name=config.model_name,
            prompt_version=request.prompt_version,
            request_id=uuid4(),
            status="running",
            started_at=utcnow(),
            call_metadata={"job_id": str(job_id), "fingerprint": fingerprint},
        )
        session.add(row)
        await session.flush()
        call_id, started = row.id, row.started_at
    completed = None
    try:
        execution = AIExecutionService(env=env, transport=transport)
        completed = await asyncio.to_thread(execution.complete, config, request)
        validate_result(completed.result.parsed, request)
    except Exception as error:
        log = getattr(error, "call_log", None)
        async with db.transaction() as session:
            row = await owned(session, AICallLog, call_id, user_id, lock=True)
            row.status, row.finished_at = "failed", utcnow()
            row.duration_ms = int((row.finished_at - started).total_seconds() * 1000)
            row.error_code = getattr(error, "code", "INTERNAL_ERROR")
            row.error_message = "模型调用失败，请检查配置和服务状态"
            row.attempt_count = log.attempt_count if log else 1
            if completed:
                row.input_tokens = completed.result.input_tokens
                row.output_tokens = completed.result.output_tokens
                row.total_tokens = completed.result.total_tokens
                row.attempt_count = completed.call_log.attempt_count
        raise
    async with db.transaction() as session:
        row = await owned(session, AICallLog, call_id, user_id, lock=True)
        result = completed.result
        row.status, row.finished_at = "succeeded", utcnow()
        row.input_tokens, row.output_tokens = result.input_tokens, result.output_tokens
        row.total_tokens, row.duration_ms = result.total_tokens, completed.call_log.duration_ms
        row.attempt_count = completed.call_log.attempt_count
        row.call_metadata = {**row.call_metadata, "parsed_result": result.parsed}
    return result.parsed, call_id


def validate_result(parsed, request):
    if request.operation == "extract_knowledge":
        note_text = request.metadata.get("grounding_note_text")
        if note_text is not None:
            analysis, _ = parse_grounding(parsed, note_text)
            if not analysis.information_sufficient:
                return
        result = parse_extraction_output(
            parsed,
            subject_id=request.metadata["subject_id"],
            source_raw_note_id=request.metadata["source_raw_note_id"],
        )
        points = dedupe_knowledge_points(result.points)
        if len(points) > 100 or len({point.title for point in points}) != len(points):
            raise ServiceError("VALIDATION_ERROR", "知识点应在100条以内且标题唯一")
    if request.operation == "generate_review_items":
        result = parse_generation_output(parsed, knowledge_point_id="")
        if len(result.items) != request.metadata["count"] or any(
            item.question_type not in request.metadata["question_types"] for item in result.items
        ):
            raise ServiceError("VALIDATION_ERROR", "生成题型和数量不符合请求")
        quote = request.metadata.get("grounding_source_quote")
        if quote and any(not item.answer.strip() or item.answer.strip() not in quote for item in result.items):
            raise ServiceError("VALIDATION_ERROR", "Notion 复习答案需逐字来自对应的原文摘录")


async def process_chapter_job(db, settings, job_id, *, transport=None):
    user_id = None
    try:
        async with db.transaction() as session:
            job = await session.get(ChapterJob, job_id)
            if job is None:
                raise ServiceError("RESOURCE_NOT_FOUND", "提取任务不存在")
            user_id = job.user_id
            locked = await session.scalar(
                select(
                    func.pg_try_advisory_xact_lock(func.hashtextextended(str(job.chapter_id), 732))
                )
            )
            if not locked:
                return {"status": "busy"}
            await session.refresh(job)
            if job.status not in {"pending", "running", "failed", "blocked"}:
                return {"status": job.status}
            if job.status == "failed" and (
                job.next_attempt_at is None or job.next_attempt_at > utcnow()
            ):
                return {"status": "deferred"}
            chapter = await owned(session, Chapter, job.chapter_id, user_id)
            user = await session.get(User, user_id)
            if not user.is_active:
                raise ServiceError("AUTH_INVALID", "账号不可用")
            cancellation = chapter_job_cancellation(chapter, job.content_hash)
            if cancellation:
                # Serialize the decision with chapter completion, which may revive this same hash.
                await lock_owner(session, user_id)
                await session.refresh(chapter)
                cancellation = chapter_job_cancellation(chapter, job.content_hash)
                if not cancellation:
                    return {"status": "deferred"}
                job.status = "cancelled"
                job.error_code = cancellation
                job.next_attempt_at = None
                return {"status": "cancelled"}
            subject = await owned(session, Subject, chapter.subject_id, user_id)
            if not subject.is_active:
                raise ServiceError("INVALID_STATE", "学科已停用")
            provider = await session.scalar(
                select(AIProviderConfig).where(
                    AIProviderConfig.user_id == user_id,
                    AIProviderConfig.is_default.is_(True),
                    AIProviderConfig.is_enabled.is_(True),
                )
            )
            if provider is None:
                raise ServiceError("CONFIG_MISSING", "请配置默认模型")
            config = provider_settings(provider, settings)
            provider_version = provider.version
            strategy_row = await session.scalar(
                select(SubjectStrategy).where(
                    SubjectStrategy.subject_id == subject.id, SubjectStrategy.is_active.is_(True)
                )
            )
            strategy = replace(
                default_strategy(),
                subject_id=str(subject.id),
                name=subject.name,
                slug=subject.slug,
                language_code=subject.language_code,
            )
            if strategy_row:
                strategy = strategy_from_mapping(
                    {
                        **strategy.to_config_mapping(),
                        **{
                            name: getattr(strategy_row, name)
                            for name in strategy.to_contract_dict()
                        },
                    }
                )
            raw = (
                await session.scalar(
                    select(RawNote)
                    .where(
                        RawNote.user_id == user_id,
                        RawNote.external_page_id == chapter.external_page_id,
                    )
                    .order_by(RawNote.last_edited_time.desc())
                    .limit(1)
                )
                if chapter.external_page_id
                else None
            )
            if raw and raw.content_markdown != chapter.content:
                raw = None
            if chapter.external_page_id and raw is None:
                raise ServiceError("INVALID_STATE", "保存的 Notion 原笔记版本与章节正文不一致")
            note = {
                "id": str(raw.id if raw else chapter.id),
                "title": chapter.title,
                "content_markdown": chapter.content,
            }
            strategy_version = strategy_row.version if strategy_row else None
            request = build_extraction_request(
                note,
                strategy,
                config,
                subject_name=subject.name,
                prompt_version=strategy.prompt_version,
                schema_hint=GROUNDED_SCHEMA_HINT if raw else None,
            )
            if raw:
                preferences = await session.scalar(
                    select(WorkspaceProfile.review_preferences).where(WorkspaceProfile.user_id == user_id)
                ) or {}
                related = await session.execute(
                    select(KnowledgePoint.title, KnowledgePoint.summary)
                    .where(
                        KnowledgePoint.user_id == user_id,
                        KnowledgePoint.subject_id == subject.id,
                        KnowledgePoint.status.in_(["draft", "active"]),
                    )
                    .order_by(KnowledgePoint.updated_at.desc(), KnowledgePoint.id)
                    .limit(12)
                )
                request = request_grounding(
                    request,
                    note["content_markdown"],
                    learning_context={
                        "subject_description": (subject.description or "")[:1000],
                        "language": subject.language_code,
                        "question_type_preferences": list(strategy.question_type_preferences),
                        "learning_goal": preferences.get("learning_goal", ""),
                        "learning_preference": preferences.get("learning_preference", ""),
                        "related_points": [
                            {"title": title, "summary": summary[:300]} for title, summary in related
                        ],
                    },
                )
            request_nonce = job.result.get("request_nonce")
            parsed, extract_log_id = await call_model(
                db, settings, user_id, config, request, job.id,
                provider_version=provider_version, transport=transport, request_nonce=request_nonce,
            )
            analysis, evidence = parse_grounding(parsed, note["content_markdown"]) if raw else (None, {})
            if analysis is None or analysis.information_sufficient:
                extracted = parse_extraction_output(
                    parsed, subject_id=str(subject.id), source_raw_note_id=note["id"]
                )
                drafts = dedupe_knowledge_points(extracted.points)
            else:
                drafts = []
            generated = []
            for draft in drafts:
                request = build_generation_request(
                    draft.to_contract_dict(),
                    strategy,
                    config,
                    question_types=None,
                    count=1,
                    subject_name=subject.name,
                )
                if raw:
                    quote = evidence[draft.title]["source_quote"]
                    request = replace(
                        request,
                        system=request.system + (
                            "请编写主动回忆题。参考答案必须逐字取自原文证据中的一段连续文字。"
                            "解析只依据这段原文证据。"
                        ),
                        user=request.user + "\n原文证据：\n" + quote,
                        metadata={**request.metadata, "grounding_source_quote": quote},
                    )
                output, call_id = await call_model(
                    db, settings, user_id, config, request, job.id,
                    provider_version=provider_version, transport=transport, request_nonce=request_nonce,
                )
                cards = parse_generation_output(
                    output,
                    knowledge_point_id="",
                    meta=GenerationMeta(
                        provider=config.provider,
                        model_name=config.model_name,
                        provider_config_id=config.config_id,
                        ai_call_log_id=str(call_id),
                        prompt_version=request.prompt_version,
                    ),
                )
                if len(cards.items) != 1:
                    raise ServiceError("VALIDATION_ERROR", "每个知识点应返回一张当前复习卡片")
                generated.append((draft, cards.items[0], call_id))
            await lock_owner(session, user_id)
            await session.refresh(chapter, with_for_update=True)
            await session.refresh(provider)
            await session.refresh(subject)
            if not subject.is_active:
                raise ServiceError("INVALID_STATE", "学科已停用")
            current_strategy = await session.scalar(
                select(SubjectStrategy)
                .where(
                    SubjectStrategy.subject_id == subject.id, SubjectStrategy.is_active.is_(True)
                )
                .execution_options(populate_existing=True)
            )
            if (current_strategy.version if current_strategy else None) != strategy_version:
                raise ServiceError("VERSION_CONFLICT", "学科策略已变化，请重试")
            cancellation = chapter_job_cancellation(chapter, job.content_hash)
            if cancellation:
                job.status = "cancelled"
                job.error_code = cancellation
                job.next_attempt_at = None
                return {"status": "cancelled"}
            if not provider.is_enabled or provider.version != provider_version:
                raise ServiceError("VERSION_CONFLICT", "模型配置已变化，请重试")
            point_ids, grounded_points = [], []
            touched_points = set()
            anchors, stale = await revision_points(session, chapter, raw) if raw else ({}, {})
            new_titles = {draft.title for draft in drafts}
            new_quotes = Counter(entry["source_quote"] for entry in evidence.values())
            for draft, card, call_id in generated:
                canonical = knowledge_hash(subject.id, draft.title, draft.body)
                point = await session.scalar(
                    select(KnowledgePoint).where(
                        KnowledgePoint.user_id == user_id,
                        KnowledgePoint.canonical_hash == canonical,
                        KnowledgePoint.status != "merged",
                    )
                )
                if point is None:
                    point = await session.scalar(
                        select(KnowledgePoint)
                        .where(
                            KnowledgePoint.chapter_id == chapter.id,
                            KnowledgePoint.title == draft.title,
                            KnowledgePoint.status != "merged",
                        )
                        .order_by(KnowledgePoint.created_at.desc())
                        .limit(1)
                    )
                if point is None and raw:
                    quote = evidence[draft.title]["source_quote"]
                    matching = anchors.get(quote, {})
                    if len(matching) == new_quotes[quote] == 1 and note["content_markdown"].count(quote) == 1:
                        anchored = next(iter(matching.values()))
                        if anchored.id not in touched_points and anchored.title not in new_titles:
                            point = anchored
                if point is None:
                    point = KnowledgePoint(
                        user_id=user_id,
                        chapter_id=chapter.id,
                        canonical_hash=canonical,
                        manual_revision=False,
                        **draft.to_contract_dict(),
                    )
                    session.add(point)
                    await session.flush()
                if raw:
                    link = await session.scalar(
                        select(KnowledgePointSource.id).where(
                            KnowledgePointSource.knowledge_point_id == point.id,
                            KnowledgePointSource.raw_note_id == raw.id,
                        )
                    )
                    if not link:
                        session.add(
                            KnowledgePointSource(
                                user_id=user_id,
                                knowledge_point_id=point.id,
                                raw_note_id=raw.id,
                                source_excerpt=evidence[draft.title]["source_quote"],
                            )
                        )
                    grounded_points.append(
                        {"knowledge_point_id": str(point.id), **evidence[draft.title]}
                    )
                point_ids.append(str(point.id))
                touched_points.add(point.id)
                if point.manual_revision or point.status in {"archived", "merged"}:
                    continue
                for name in ("title", "body", "summary", "difficulty", "keywords", "tags"):
                    setattr(point, name, getattr(draft, name))
                point.canonical_hash = canonical
                point.status, point.source_generated_at = "active", utcnow()
                point.version += 1
                current = await session.scalar(
                    select(ReviewItem).where(
                        ReviewItem.knowledge_point_id == point.id, ReviewItem.is_current.is_(True)
                    )
                )
                if not current or not current.manual_revision:
                    latest_version = (
                        await session.scalar(
                            select(func.max(ReviewItem.item_version)).where(
                                ReviewItem.knowledge_point_id == point.id
                            )
                        )
                        or 0
                    )
                    if current:
                        current.is_current = False
                        await session.flush()
                    replacement = ReviewItem(
                        user_id=user_id,
                        knowledge_point_id=point.id,
                        question_type=card.question_type,
                        question=card.question,
                        answer=card.answer,
                        explanation=card.explanation,
                        summary=card.summary,
                        options=card.options,
                        item_version=latest_version + 1,
                        manual_revision=False,
                        provider_config_id=provider.id,
                        model_name=config.model_name,
                        prompt_version=card.prompt_version,
                        ai_call_log_id=call_id,
                    )
                    session.add(replacement)
                    if raw:
                        await session.flush()
                        await session.execute(
                            update(DailyReviewTask)
                            .where(
                                DailyReviewTask.user_id == user_id,
                                DailyReviewTask.knowledge_point_id == point.id,
                                DailyReviewTask.status.in_(OPEN_TASK_STATUSES),
                            )
                            .values(review_item_id=replacement.id, version=DailyReviewTask.version + 1)
                        )
                await initialize_schedule(session, settings, point)
            review_required = await hold_missing_points(session, user_id, stale, touched_points)
            job.status, job.error_code, job.next_attempt_at = "succeeded", None, None
            job.attempt += 1
            job.result = {
                "knowledge_point_ids": point_ids,
                "extraction_call_id": str(extract_log_id),
                "origin": "ai_generated",
                "source_raw_note_id": str(raw.id) if raw else None,
                **({"request_nonce": request_nonce} if request_nonce else {}),
            }
            if analysis is not None:
                job.result = {
                    **job.result,
                    "analysis": {
                        "note_summary": analysis.note_summary,
                        "information_sufficient": analysis.information_sufficient,
                        "limitations": [
                            *analysis.limitations,
                            *(
                                ["部分旧知识点的当前证据未确认，已移入草稿并保留复习历史。"]
                                if review_required else []
                            ),
                        ],
                        "review_required_point_ids": review_required,
                        "knowledge_points": grounded_points,
                    },
                }
        return {"status": "succeeded", "count": len(point_ids)}
    except Exception as error:
        if user_id is None:
            raise
        code = getattr(error, "code", "INTERNAL_ERROR")
        async with db.transaction() as session:
            await session.scalar(select(User).where(User.id == user_id).with_for_update())
            job = await owned(session, ChapterJob, job_id, user_id, lock=True)
            if job.status not in {"succeeded", "cancelled"}:
                job.error_code = code
                if code == "CONFIG_MISSING":
                    job.status = "blocked"
                    job.next_attempt_at = utcnow() + CONFIGURATION_CHECK_INTERVAL
                else:
                    job.status = "failed"
                    job.attempt += 1
                    retryable = getattr(error, "retryable", False) or code in {
                        "VERSION_CONFLICT",
                        "INTERNAL_ERROR",
                        "RATE_LIMITED",
                    }
                    job.next_attempt_at = (
                        utcnow() + timedelta(seconds=min(3600, 30 * 2**job.attempt))
                        if retryable and job.attempt < 5
                        else None
                    )
            return {"status": job.status, "error_code": job.error_code}


async def extract_pending(db, settings, *, transport=None):
    now = utcnow()
    async with db.transaction() as session:
        ids = list(
            (
                await session.scalars(
                    select(ChapterJob.id)
                    .where(
                        or_(
                            ChapterJob.status.in_(["pending", "running"]),
                            (ChapterJob.status == "failed")
                            & (ChapterJob.next_attempt_at <= now),
                            (ChapterJob.status == "blocked")
                            & or_(ChapterJob.next_attempt_at.is_(None), ChapterJob.next_attempt_at <= now),
                        )
                    )
                    .order_by(
                        func.coalesce(ChapterJob.next_attempt_at, ChapterJob.created_at),
                        ChapterJob.id,
                    )
                    .limit(100)
                )
            ).all()
        )
    outcomes = [
        await process_chapter_job(db, settings, job_id, transport=transport) for job_id in ids
    ]
    return {
        "status": "failed" if any(o["status"] == "failed" for o in outcomes) else "succeeded",
        "count": sum(o.get("count", 0) for o in outcomes),
        "blocked": sum(o["status"] == "blocked" for o in outcomes),
        "jobs": outcomes,
    }
