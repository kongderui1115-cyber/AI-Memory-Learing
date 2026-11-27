"""Password verification and signed access tokens."""

from datetime import datetime, timedelta, timezone
from uuid import UUID
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from app.config import Settings, ConfigMissingError, is_blank_or_placeholder

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    if len(password) < 8 or len(password) > 256:
        raise ValueError("Password length must be 8 through 256")
    return _hasher.hash(password)


def verify_password(encoded: str, password: str) -> bool:
    try:
        return _hasher.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False


def _secret(settings: Settings) -> str:
    if is_blank_or_placeholder(settings.secret_key) or len(settings.secret_key) < 32:
        raise ConfigMissingError(["SECRET_KEY (minimum 32 characters)"])
    return settings.secret_key


def issue_token(user_id: UUID, settings: Settings, *, session_id: UUID | None = None) -> str:
    now = datetime.now(timezone.utc)
    if settings.access_token_expire_minutes <= 0:
        raise ConfigMissingError(["ACCESS_TOKEN_EXPIRE_MINUTES"])
    return jwt.encode(
        {
            "sub": str(user_id),
            "iat": now,
            "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
            "iss": "ai-learning-memory-os",
            "aud": "learning-api",
            **({"sid": str(session_id)} if session_id else {}),
        },
        _secret(settings),
        algorithm="HS256",
    )


def decode_token(token: str, settings: Settings) -> UUID:
    payload = jwt.decode(
        token,
        _secret(settings),
        algorithms=["HS256"],
        issuer="ai-learning-memory-os",
        audience="learning-api",
        options={"require": ["sub", "iat", "exp", "iss", "aud"]},
    )
    return UUID(payload["sub"])


def decode_claims(token: str, settings: Settings) -> dict:
    return jwt.decode(
        token,
        _secret(settings),
        algorithms=["HS256"],
        issuer="ai-learning-memory-os",
        audience="learning-api",
        options={"require": ["sub", "sid", "iat", "exp", "iss", "aud"]},
    )
