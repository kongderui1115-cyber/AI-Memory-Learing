"""Database-backed authentication, revocation, throttling and audit."""

import asyncio
import hashlib
import hmac
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID, uuid4

import jwt
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.models import AuditEvent, LoginThrottle, User, UserSession
from app.security import decode_claims, hash_password, issue_token, verify_password
from app.services.common import ServiceError, lock_owner, utcnow

_dummy_hash = hash_password("timing-only-unused-password")


@dataclass
class Principal:
    user: User
    session: UserSession

    @property
    def user_id(self):
        return self.user.id


def audit(
    session,
    actor,
    action,
    resource,
    outcome,
    ip,
    request_id=None,
    target_user_id=None,
    severity="info",
):
    session.add(
        AuditEvent(
            actor_id=actor.id if actor else None,
            actor_label=actor.email if actor else "unknown",
            target_user_id=target_user_id,
            action=action,
            resource=resource[:300],
            outcome=outcome,
            ip_address=ip[:64],
            request_id=request_id,
            severity=severity,
        )
    )


async def _throttle(session, key, now, window_minutes):
    await session.execute(
        insert(LoginThrottle)
        .values(key=key, failures=0, window_started_at=now)
        .on_conflict_do_nothing()
    )
    row = await session.scalar(
        select(LoginThrottle).where(LoginThrottle.key == key).with_for_update()
    )
    if row.locked_until and row.locked_until > now:
        return row, True
    if now - row.window_started_at >= timedelta(minutes=window_minutes):
        row.failures = 0
        row.locked_until = None
        row.window_started_at = now
    return row, False


async def login(database, settings, email, password, ip, agent, request_id=None):
    now = utcnow()
    email = email.strip().casefold()
    account_key = "account:" + hashlib.sha256(email.encode()).hexdigest()
    ip_key = "ip:" + hashlib.sha256(ip.encode()).hexdigest()
    async with database.transaction() as session:
        ip_row, ip_locked = await _throttle(session, ip_key, now, settings.login_lock_minutes)
        row, account_locked = await _throttle(
            session, account_key, now, settings.login_lock_minutes
        )
        user = await session.scalar(select(User).where(User.email == email).with_for_update())
        if ip_locked or account_locked:
            audit(
                session,
                user,
                "login_blocked",
                "auth",
                "blocked",
                ip,
                request_id,
                target_user_id=user.id if user else None,
                severity="warning",
            )
            return None, "RATE_LIMITED"
        encoded = user.password_hash if user else _dummy_hash
        valid = await asyncio.to_thread(verify_password, encoded, password)
        if user is None or not valid or not user.is_active:
            row.failures += 1
            ip_row.failures += 1
            limited = row.failures >= settings.login_failure_limit
            if limited:
                row.locked_until = now + timedelta(minutes=settings.login_lock_minutes)
            if ip_row.failures >= settings.login_ip_failure_limit:
                ip_row.locked_until = now + timedelta(minutes=settings.login_lock_minutes)
                limited = True
            audit(
                session,
                user,
                "login_failed",
                "auth",
                "rate_limited" if limited else "invalid",
                ip,
                request_id,
                target_user_id=user.id if user else None,
                severity="warning",
            )
            return None, "RATE_LIMITED" if limited else "AUTH_INVALID"
        row.failures = 0
        row.locked_until = None
        row.window_started_at = now
        session_id = uuid4()
        token = issue_token(user.id, settings, session_id=session_id)
        session.add(
            UserSession(
                id=session_id,
                user_id=user.id,
                token_digest=hashlib.sha256(token.encode()).hexdigest(),
                created_at=now,
                last_seen_at=now,
                expires_at=now + timedelta(minutes=settings.access_token_expire_minutes),
                ip_address=ip[:64],
                user_agent=agent[:500],
            )
        )
        audit(session, user, "login_success", "auth", "allowed", ip, request_id, user.id)
        return token, None


async def principal(database, settings, token):
    try:
        claims = decode_claims(token, settings)
        user_id, session_id = UUID(claims["sub"]), UUID(claims["sid"])
    except (jwt.InvalidTokenError, ValueError, KeyError, TypeError):
        raise ServiceError("AUTH_INVALID", "登录凭据无效或已过期") from None
    now = utcnow()
    async with database.transaction() as session:
        row = await session.scalar(
            select(UserSession).where(UserSession.id == session_id, UserSession.user_id == user_id)
        )
        user = await session.get(User, user_id)
        valid = row is not None and user is not None and user.is_active
        if not valid or row.logged_out_at is not None or row.expires_at <= now:
            raise ServiceError("AUTH_INVALID", "登录会话已失效")
        digest = hashlib.sha256(token.encode()).hexdigest()
        if not hmac.compare_digest(row.token_digest, digest):
            raise ServiceError("AUTH_INVALID", "登录凭据无效")
        if (now - row.last_seen_at).total_seconds() >= 30:
            row.last_seen_at = now
        return Principal(user, row)


async def require_admin(database, actor, ip, request_id):
    if actor.user.role == "admin":
        return actor
    async with database.transaction() as session:
        audit(
            session,
            actor.user,
            "admin_access",
            "admin",
            "forbidden",
            ip,
            request_id,
            severity="warning",
        )
    raise ServiceError("FORBIDDEN", "需要管理员权限")


async def heartbeat(database, actor):
    async with database.transaction() as session:
        row = await session.scalar(
            select(UserSession).where(UserSession.id == actor.session.id).with_for_update()
        )
        if row.logged_out_at is not None or row.expires_at <= utcnow():
            raise ServiceError("AUTH_INVALID", "登录会话已失效")
        row.last_seen_at = utcnow()
        return row.last_seen_at


async def logout(database, actor, ip, request_id):
    async with database.transaction() as session:
        row = await session.scalar(
            select(UserSession).where(UserSession.id == actor.session.id).with_for_update()
        )
        row.logged_out_at = utcnow()
        audit(session, actor.user, "logout", "auth", "allowed", ip, request_id, actor.user_id)


async def change_password(database, actor, body, ip, request_id):
    async with database.transaction() as session:
        user = await lock_owner(session, actor.user_id)
        if not await asyncio.to_thread(verify_password, user.password_hash, body.current_password):
            raise ServiceError("AUTH_INVALID", "当前密码错误")
        user.password_hash = await asyncio.to_thread(hash_password, body.new_password)
        user.version += 1
        rows = await session.scalars(
            select(UserSession).where(
                UserSession.user_id == user.id, UserSession.logged_out_at.is_(None)
            )
        )
        for row in rows:
            row.logged_out_at = utcnow()
        audit(session, user, "password_changed", "account", "allowed", ip, request_id, user.id)
