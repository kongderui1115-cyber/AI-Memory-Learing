"""Shared transaction, ownership, idempotency and pagination rules."""

import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, tuple_
from app.models import IdempotencyRecord, User


class ServiceError(ValueError):
    def __init__(self, code, message=None):
        super().__init__(message or code)
        self.code = code


def utcnow():
    return datetime.now(timezone.utc)


async def lock_owner(session, user_id):
    user = await session.scalar(select(User).where(User.id == user_id).with_for_update())
    if user is None or not user.is_active:
        raise ServiceError("AUTH_INVALID", "账号不可用")
    return user


async def owned(session, model, resource_id, user_id, *, lock=False):
    query = select(model).where(model.id == resource_id, model.user_id == user_id)
    if lock:
        query = query.with_for_update()
    result = await session.scalar(query)
    if result is None:
        raise ServiceError("RESOURCE_NOT_FOUND", "资源不存在")
    return result


def check_version(resource, expected):
    if expected is None or expected != resource.version:
        raise ServiceError("VERSION_CONFLICT", "资源已更新，请重新读取")


async def replay(session, user_id, operation, key, payload, secret):
    if not key or not key.strip() or len(key) > 128:
        raise ServiceError("VALIDATION_ERROR", "需要1至128字符的Idempotency-Key")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    digest = hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()
    record = await session.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.user_id == user_id,
            IdempotencyRecord.operation == operation,
            IdempotencyRecord.key == key,
        )
    )
    if record is not None and not hmac.compare_digest(record.request_hash, digest):
        raise ServiceError("IDEMPOTENCY_CONFLICT", "幂等键已用于其他请求内容")
    return record, digest


def remember(session, user_id, operation, key, digest, resource_id):
    session.add(
        IdempotencyRecord(
            user_id=user_id,
            operation=operation,
            key=key,
            request_hash=digest,
            resource_id=resource_id,
        )
    )


async def page(session, query, model, limit=20, cursor=None):
    if cursor:
        try:
            timestamp, resource_id = json.loads(base64.urlsafe_b64decode(cursor.encode()))
            timestamp = datetime.fromisoformat(timestamp)
            if timestamp.utcoffset() is None:
                raise ValueError("Timezone required")
            resource_id = UUID(resource_id)
        except (ValueError, TypeError, KeyError, UnicodeError) as exc:
            raise ServiceError("VALIDATION_ERROR", "无效的分页游标") from exc
        query = query.where(tuple_(model.created_at, model.id) < tuple_(timestamp, resource_id))
    rows = list(
        (
            await session.scalars(
                query.order_by(model.created_at.desc(), model.id.desc()).limit(limit + 1)
            )
        ).all()
    )
    more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = None
    if more:
        value = json.dumps([rows[-1].created_at.isoformat(), str(rows[-1].id)])
        next_cursor = base64.urlsafe_b64encode(value.encode()).decode()
    return rows, next_cursor, more
