"""Administrator operations over existing model and subject configuration."""

from datetime import datetime, timezone
from urllib.parse import urlsplit

from sqlalchemy import select, tuple_

from app.ai.errors import AIIntegrationError
from app.domain import memory
from app.models import AIProviderConfig, Subject, SubjectStrategy, User, UserSecret, WorkspaceProfile
from app.services import ai_runtime
from app.services.accounts import audit
from app.services.admin import staff, target_user
from app.services.common import ServiceError, check_version, owned, page
from app.services.credentials import load_user_settings


SIMULATION_START = datetime(2026, 1, 1, tzinfo=timezone.utc)


async def resource_owner(session, model, resource_id, *, lock=False):
    owner_id = await session.scalar(select(model.user_id).where(model.id == resource_id))
    if owner_id is None:
        raise ServiceError("RESOURCE_NOT_FOUND", "配置不存在")
    query = select(User).where(User.id == owner_id)
    return await session.scalar(query.with_for_update() if lock else query)


def provider_view(row, owner, consent, settings, key_configured, *, invalid=None):
    endpoint = ai_runtime.model_destination(row.provider, row.base_url)[1]
    endpoint_host = None
    try:
        endpoint_host = urlsplit(endpoint).hostname
        if invalid is None:
            ai_runtime.provider_settings(row, settings).validate()
    except (AIIntegrationError, ServiceError, ValueError, TypeError):
        invalid = True

    if not owner.is_active:
        status = "owner_inactive"
    elif not row.is_enabled:
        status = "disabled"
    elif invalid:
        status = "configuration_invalid"
    elif not key_configured:
        status = "key_missing"
    elif not consent or not settings.ai_billing_approved:
        status = "billing_paused"
    else:
        status = "configured"

    return {
        "id": row.id,
        "user_id": owner.id,
        "user_name": owner.display_name,
        "name": row.name,
        "provider": row.provider,
        "model_name": row.model_name,
        "endpoint_host": endpoint_host,
        "is_enabled": row.is_enabled,
        "is_default": row.is_default,
        "version": row.version,
        "key_configured": key_configured,
        "user_billing_approved": bool(consent),
        "global_billing_approved": settings.ai_billing_approved,
        "configuration_status": status,
        "connection_tested": False,
    }


async def model_providers(db, settings, actor, ip, request_id, user_id, limit, cursor):
    async with db.transaction() as session:
        admin = await staff(session, actor)
        query = select(AIProviderConfig)
        if user_id is not None:
            await target_user(session, user_id)
            query = query.where(AIProviderConfig.user_id == user_id)
        rows, cursor, more = await page(session, query, AIProviderConfig, limit, cursor)
        owners = {
            user.id: (user, consent)
            for user, consent in await session.execute(
                select(User, WorkspaceProfile.ai_billing_approved)
                .outerjoin(WorkspaceProfile, WorkspaceProfile.user_id == User.id)
                .where(User.id.in_({row.user_id for row in rows}))
            )
        }
        configured = set(await session.execute(
            select(UserSecret.user_id, UserSecret.name).where(
                tuple_(UserSecret.user_id, UserSecret.name).in_(
                    {(row.user_id, row.credential_ref) for row in rows}
                )
            )
        ))
        items = [
            provider_view(
                row, *owners[row.user_id], settings,
                (row.user_id, row.credential_ref) in configured or settings.is_set(row.credential_ref),
            )
            for row in rows
        ]
        audit(session, admin, "admin_model_providers_read", "model-providers", "allowed", ip, request_id, user_id)
        return {"items": items, "next_cursor": cursor, "has_more": more}


async def model_readiness(session, settings, row, owner):
    consent = await session.scalar(
        select(WorkspaceProfile.ai_billing_approved).where(WorkspaceProfile.user_id == owner.id)
    )
    try:
        config = ai_runtime.provider_settings(row, settings)
        config.validate()
        await ai_runtime.check_destination_binding(session, owner.id, config)
        scoped = await load_user_settings(session, settings, owner.id, credential_ref=row.credential_ref)
    except (AIIntegrationError, ServiceError, ValueError, TypeError):
        return provider_view(row, owner, consent, settings, False, invalid=True)
    return provider_view(row, owner, consent, settings, scoped.is_set(row.credential_ref), invalid=False)


async def read_model(db, settings, actor, ip, request_id, resource_id):
    async with db.transaction() as session:
        admin = await staff(session, actor)
        owner = await resource_owner(session, AIProviderConfig, resource_id)
        row = await owned(session, AIProviderConfig, resource_id, owner.id)
        result = await model_readiness(session, settings, row, owner)
        audit(session, admin, "admin_model_readiness", str(row.id), "allowed", ip, request_id, owner.id)
        return result


async def update_model(db, settings, actor, ip, request_id, resource_id, body, version):
    async with db.transaction() as session:
        admin = await staff(session, actor)
        owner = await resource_owner(session, AIProviderConfig, resource_id, lock=True)
        row = await owned(session, AIProviderConfig, resource_id, owner.id, lock=True)
        check_version(row, version)
        enabled = row.is_enabled if body.is_enabled is None else body.is_enabled
        default = enabled and (row.is_default if body.is_default is None else body.is_default)
        if body.is_default is True and not enabled:
            raise ServiceError("INVALID_STATE", "请先启用模型，再设为默认")
        if enabled and (not row.is_enabled or default and not row.is_default):
            if not owner.is_active:
                raise ServiceError("INVALID_STATE", "所属用户已禁用")
            config = ai_runtime.provider_settings(row, settings)
            config.validate()
            await ai_runtime.check_destination_binding(session, owner.id, config)
        if default and not row.is_default:
            await ai_runtime.set_default_provider(session, row)
        if (enabled, default) != (row.is_enabled, row.is_default):
            row.is_enabled = enabled
            row.is_default = default
            row.version += 1
        audit(session, admin, "admin_model_policy_updated", str(row.id), "allowed", ip, request_id, owner.id)
        return await model_readiness(session, settings, row, owner)


def policy_defaults(settings):
    return {
        "strategy": settings.scheduler_strategy,
        "intervals_days": list(settings.ebbinghaus_intervals_days),
        "target_retention": settings.fsrs_target_retention,
    }


def policy_values(settings, preferences, overrides):
    defaults = policy_defaults(settings)
    defaults.update({name: preferences[name] for name in ("strategy", "intervals_days") if name in preferences})
    defaults.update({name: overrides[name] for name in defaults if name in overrides})
    return defaults


def policy_view(row, owner, subject, preferences, settings):
    return {
        "id": row.id,
        "user_id": owner.id,
        "user_name": owner.display_name,
        "subject_id": subject.id,
        "subject_name": subject.name,
        "version": row.version,
        "is_active": row.is_active,
        **policy_values(settings, preferences, row.scheduler_overrides),
    }


async def memory_policies(db, settings, actor, ip, request_id, user_id, limit, cursor):
    async with db.transaction() as session:
        admin = await staff(session, actor)
        query = select(SubjectStrategy)
        if user_id is not None:
            await target_user(session, user_id)
            query = query.where(SubjectStrategy.user_id == user_id)
        rows, cursor, more = await page(session, query, SubjectStrategy, limit, cursor)
        owners = {
            user.id: (user, preferences or {})
            for user, preferences in await session.execute(
                select(User, WorkspaceProfile.review_preferences)
                .outerjoin(WorkspaceProfile, WorkspaceProfile.user_id == User.id)
                .where(User.id.in_({row.user_id for row in rows}))
            )
        }
        subjects = {
            subject.id: subject
            for subject in await session.scalars(select(Subject).where(Subject.id.in_({row.subject_id for row in rows})))
        }
        items = []
        for row in rows:
            owner, preferences = owners[row.user_id]
            items.append(policy_view(row, owner, subjects[row.subject_id], preferences, settings))
        audit(session, admin, "admin_memory_policies_read", "memory-policies", "allowed", ip, request_id, user_id)
        return {"defaults": policy_defaults(settings), "items": items, "next_cursor": cursor, "has_more": more}


async def update_memory_policy(db, settings, actor, ip, request_id, resource_id, body, version):
    async with db.transaction() as session:
        admin = await staff(session, actor)
        owner = await resource_owner(session, SubjectStrategy, resource_id, lock=True)
        row = await owned(session, SubjectStrategy, resource_id, owner.id, lock=True)
        check_version(row, version)
        if not owner.is_active or not row.is_active:
            raise ServiceError("INVALID_STATE", "只能修改已启用的学科策略")
        subject = await owned(session, Subject, row.subject_id, owner.id)
        preferences = await session.scalar(
            select(WorkspaceProfile.review_preferences).where(WorkspaceProfile.user_id == owner.id)
        ) or {}
        overrides = {**row.scheduler_overrides, **body.model_dump(mode="json", exclude_unset=True)}
        values = policy_values(settings, preferences, overrides)
        try:
            memory.initial_state(values["strategy"], SIMULATION_START, {**values, **overrides})
        except (TypeError, ValueError, OverflowError):
            raise ServiceError("VALIDATION_ERROR", "记忆策略参数不适用") from None
        if overrides != row.scheduler_overrides:
            row.scheduler_overrides = overrides
            row.version += 1
        audit(session, admin, "admin_memory_policy_updated", str(row.id), "allowed", ip, request_id, owner.id)
        return policy_view(row, owner, subject, preferences, settings)


def simulate_memory(settings, body):
    parameters = policy_defaults(settings)
    parameters.update(body.model_dump(mode="json", exclude={"strategy", "ratings"}, exclude_none=True))
    try:
        state = memory.initial_state(body.strategy.value, SIMULATION_START, parameters)
        steps = []
        for rating in body.ratings:
            reviewed_at = state.due_at
            prediction = memory.retrievability_at(state, reviewed_at)
            state = memory.review(state, rating.value, reviewed_at)
            steps.append({
                "review_count": state.review_count,
                "rating": rating,
                "reviewed_at": reviewed_at,
                "due_at": state.due_at,
                "interval_days": state.interval_days,
                "stability": state.stability,
                "difficulty": state.difficulty,
                "retrievability": prediction,
            })
    except (TypeError, ValueError, OverflowError):
        raise ServiceError("VALIDATION_ERROR", "模拟参数不适用") from None
    return {
        "strategy": body.strategy,
        "algorithm_version": state.algorithm_version,
        "steps": steps,
        "simulation": True,
    }
