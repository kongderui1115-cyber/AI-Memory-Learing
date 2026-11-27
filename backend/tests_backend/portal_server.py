"""Explicit browser-test server. Uses PostgreSQL and isolated external transports."""

import asyncio
import os
from dataclasses import replace
from ipaddress import ip_address, ip_network
from zoneinfo import ZoneInfo

import uvicorn
from fastapi import Depends
from sqlalchemy import select
from test_ai_runtime import ModelFixture
from test_guided_setup import FakeSmtp
from test_notion_runtime import FixtureTransport, notion_page

from app.api.dependencies import current_user, database
from app.config import load_settings
from app.contracts.models import DailyGenerateRequest
from app.database import Database
from app.main import create_app
from app.models import ChapterJob, NotificationJob, SyncRun, User
from app.security import hash_password
from app.server import configure_event_loop
from app.services import ai_runtime, learning, mail, notion, workspace
from app.services.common import utcnow

SOURCE_ID = "4f143627-e534-43b3-b1fc-8ad83bb375af"
PAGE_ID = "7bb456fa-70e0-4504-9fa9-f67cb041123d"
settings = load_settings()
if settings.app_env != "test" or settings.background_tasks_enabled:
    raise RuntimeError("Browser test server requires APP_ENV=test and background tasks disabled")
app = create_app(settings)
original_discover = workspace.discover_sources


@app.get("/api/v1/testing/identity")
async def browser_test_identity():
    return {"environment": "isolated-browser-test"}


@app.middleware("http")
async def isolated_browser_client(request, call_next):
    # This server is guarded by APP_ENV=test above and is never imported by app.main.
    # Each browser context models a distinct documentation-range test client.
    client = request.headers.get("X-Memory-Test-Client", "")
    if client:
        try:
            address = ip_address(client)
            if address in ip_network("2001:db8::/32"):
                request.scope["client"] = (str(address), request.client.port if request.client else 0)
        except ValueError:
            pass
    return await call_next(request)


async def discover_fixture(db, config, user_id, query=""):
    transport = FixtureTransport(
        callback=lambda *_: {
            "results": [
                {
                    "id": SOURCE_ID,
                    "title": [{"plain_text": "浏览器测试知识库"}],
                    "properties": {
                        "状态": {
                            "type": "status",
                            "status": {
                                "options": [
                                    {"name": "未开始"},
                                    {"name": "进行中"},
                                    {"name": "已完成"},
                                ]
                            },
                        }
                    },
                }
            ]
        }
    )
    return await original_discover(db, config, user_id, query, transport=transport)


workspace.discover_sources = discover_fixture


ActorDependency = Depends(current_user)
DatabaseDependency = Depends(database)


@app.post("/api/v1/testing/drain")
async def drain(actor=ActorDependency, db=DatabaseDependency):
    async with db.transaction() as session:
        runs = list(
            (
                await session.scalars(
                    select(SyncRun.id).where(
                        SyncRun.user_id == actor.user_id, SyncRun.status == "pending"
                    )
                )
            ).all()
        )
    for run_id in runs:
        await notion.process_run(
            db,
            settings,
            run_id,
            transport=FixtureTransport([notion_page(PAGE_ID, status="已完成")]),
        )
    async with db.transaction() as session:
        jobs = list(
            (
                await session.scalars(
                    select(ChapterJob.id).where(
                        ChapterJob.user_id == actor.user_id, ChapterJob.status == "pending"
                    )
                )
            ).all()
        )
    for job_id in jobs:
        await ai_runtime.process_chapter_job(
            db, replace(settings, ai_billing_approved=True), job_id, transport=ModelFixture()
        )
    await learning.generate_batch(
        db,
        settings,
        actor.user_id,
        DailyGenerateRequest(
            local_date=utcnow().astimezone(ZoneInfo(actor.user.timezone)).date(),
            timezone=actor.user.timezone,
        ),
        "browser-daily",
        refresh=True,
    )
    await mail.queue_digest(db, settings, actor.user_id)
    async with db.transaction() as session:
        jobs = list(
            (
                await session.scalars(
                    select(NotificationJob.id).where(
                        NotificationJob.user_id == actor.user_id,
                        NotificationJob.status == "pending",
                    )
                )
            ).all()
        )
    for job_id in jobs:
        await mail.process_mail(db, settings, job_id, transport=FakeSmtp())
    return {"processed": True}


async def seed_admin():
    db = Database(settings)
    try:
        async with db.transaction() as session:
            if not await session.scalar(
                select(User.id).where(User.email == "portal-admin@example.com")
            ):
                session.add(
                    User(
                        email="portal-admin@example.com",
                        display_name="验收管理员",
                        role="admin",
                        timezone="Asia/Shanghai",
                        password_hash=hash_password("Browser-admin-pass-123"),
                    )
                )
    finally:
        await db.close()


if __name__ == "__main__":
    configure_event_loop()
    asyncio.run(seed_admin())
    uvicorn.run(
        app, host="127.0.0.1", port=int(os.environ.get("PORTAL_TEST_PORT", "8000")), loop="none"
    )
