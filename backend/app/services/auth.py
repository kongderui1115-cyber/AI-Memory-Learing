"""Backward-compatible authentication entry using persistent sessions."""

from app.services.accounts import login


async def authenticate(database, settings, email, password):
    token, error = await login(
        database, settings, email, password, "127.0.0.1", "internal-authenticate"
    )
    return token
