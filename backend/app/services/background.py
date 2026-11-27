"""Recoverable local orchestration shared by the web app and command line worker."""

import asyncio
import logging

from sqlalchemy import select

from app.models import User, WorkspaceProfile
from app.services.ai_runtime import extract_pending
from app.services.mail import queue_digest, send_pending
from app.services.notion import sync_pending
from app.worker import generate_daily_tasks

logger = logging.getLogger(__name__)


async def _queue_digests(db, settings):
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
    for user_id in ids:
        try:
            await queue_digest(db, settings, user_id)
        except Exception as error:  # noqa: BLE001 - preserve retry state and keep the worker running
            logger.warning(
                "Digest queue failure user_id=%s type=%s",
                user_id,
                type(error).__name__,
            )


async def run_once(db, settings):
    # Every stage can resume its own persisted work from earlier cycles.
    stages = (
        ("notion_sync", sync_pending),
        ("chapter_extraction", extract_pending),
        ("daily_review_generation", generate_daily_tasks),
        ("digest_enqueue", _queue_digests),
        ("mail_delivery", send_pending),
    )
    for name, operation in stages:
        try:
            await operation(db, settings)
        except Exception as error:  # noqa: BLE001 - keep unrelated persisted work flowing
            logger.warning("Background stage failure stage=%s type=%s", name, type(error).__name__)


async def run_loop(db, settings):
    while True:
        try:
            await run_once(db, settings)
        except Exception as error:  # noqa: BLE001 - preserve retry state and keep the worker running
            logger.warning("Background cycle failure type=%s", type(error).__name__)
        await asyncio.sleep(15)
