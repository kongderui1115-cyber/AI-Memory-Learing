"""Credentials are encrypted with user- and reference-bound authenticated keys."""

import base64
import hashlib
import hmac
from dataclasses import replace

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select

from app.models import UserSecret, WorkspaceProfile
from app.services.common import ServiceError
from app.services.notion import check_credential_ref


def cipher(settings, user_id, name):
    context = f"memory-os-credentials-v1:{user_id}:{name}".encode()
    key = hmac.new(settings.secret_key.encode(), context, hashlib.sha256).digest()
    return Fernet(base64.urlsafe_b64encode(key))


async def save_secret(session, settings, user_id, name, value):
    check_credential_ref(user_id, name)
    row = await session.scalar(
        select(UserSecret).where(UserSecret.user_id == user_id, UserSecret.name == name)
    )
    encrypted = cipher(settings, user_id, name).encrypt(value.encode()).decode()
    if row:
        row.ciphertext = encrypted
    else:
        session.add(UserSecret(user_id=user_id, name=name, ciphertext=encrypted))


async def load_user_settings(session, settings, user_id, *, credential_ref=None):
    query = select(UserSecret).where(UserSecret.user_id == user_id)
    if credential_ref is not None:
        check_credential_ref(user_id, credential_ref)
        query = query.where(UserSecret.name == credential_ref)
    rows = (await session.scalars(query)).all()
    consent = await session.scalar(
        select(WorkspaceProfile.ai_billing_approved).where(WorkspaceProfile.user_id == user_id)
    )
    raw = dict(settings.raw)
    for row in rows:
        try:
            raw[row.name] = (
                cipher(settings, user_id, row.name).decrypt(row.ciphertext.encode()).decode()
            )
        except InvalidToken:
            raise ServiceError("CONFIG_MISSING", "凭据解密失败，请在设置中重新保存") from None
    return replace(
        settings,
        raw=raw,
        ai_billing_approved=settings.ai_billing_approved and consent is True,
    )


async def user_settings(db, settings, user_id, *, credential_ref=None):
    async with db.transaction() as session:
        return await load_user_settings(session, settings, user_id, credential_ref=credential_ref)
