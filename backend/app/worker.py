"""Portable, one-shot worker entry points for an OS scheduler or service timer."""

import argparse
import asyncio
import json
import logging
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.config import load_settings
from app.contracts.models import DailyGenerateRequest
from app.database import Database
from app.models import User
from app.server import configure_event_loop
from app.services.ai_runtime import extract_pending
from app.services.common import utcnow
from app.services.learning import generate_batch
from app.services.notion import sync_pending


logger = logging.getLogger(__name__)


async def generate_daily_tasks(db, settings):
    async with db.transaction() as session:
        users = list((await session.scalars(select(User).where(User.is_active.is_(True)))).all())
    count = failures = 0
    for user in users:
        try:
            local_date = utcnow().astimezone(ZoneInfo(user.timezone)).date()
            batch = await generate_batch(
                db,
                settings,
                user.id,
                DailyGenerateRequest(
                    local_date=local_date,
                    timezone=user.timezone,
                    daily_limit=settings.daily_review_limit,
                ),
                f"daily-{local_date.isoformat()}-{user.timezone}-{settings.daily_review_limit}",
                refresh=True,
            )
        except Exception as error:  # keep other accounts moving when one account fails
            failures += 1
            logger.warning("Daily review generation failed type=%s", type(error).__name__)
            continue
        count += len(batch.tasks)
    return {
        "status": "failed" if failures else "succeeded",
        "users": len(users),
        "count": count,
        "failures": failures,
    }


async def execute(job):
    settings = load_settings()
    if not settings.background_tasks_enabled:
        return {"status": "paused", "job": job}
    db = Database(settings)
    try:
        if job == "sync-notion":
            return await sync_pending(db, settings)
        if job == "extract-chapters":
            return await extract_pending(db, settings)
        if job == "send-daily-digest":
            from app.services.mail import send_daily_digest

            return await send_daily_digest(db, settings)
        return await generate_daily_tasks(db, settings)
    finally:
        await db.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "job",
        choices=["sync-notion", "extract-chapters", "generate-daily-tasks", "send-daily-digest"],
    )
    args = parser.parse_args()
    configure_event_loop()
    result = asyncio.run(execute(args.job))
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] in ("succeeded", "paused") else 1


if __name__ == "__main__":
    raise SystemExit(main())
