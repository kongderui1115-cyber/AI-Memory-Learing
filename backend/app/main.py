"""FastAPI application with persistent user-scoped APIs and database readiness."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Any
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.database import Database
from app.services.common import ServiceError
from app.services.reviews import ReviewError
from app.api.errors import error_response, get_request_id, HTTP_STATUS_BY_CODE

from fastapi import FastAPI

from app.api import build_health_router, install_request_context
from app.config import ConfigMissingError, Settings, load_settings
from app.telemetry import ApiTelemetryMiddleware, Telemetry

API_VERSION = "1.0.0"


def create_app(settings: Settings | None = None, *, load_env: bool = True) -> FastAPI:
    """构建并返回 FastAPI 应用；``settings`` 显式传入时用于确定性测试。"""
    config_error: BaseException | None = None
    if settings is None and load_env:
        try:
            settings = load_settings()
        except (ConfigMissingError, ValueError) as exc:
            # 明确报错，但不静默降级：保存后由 readiness 端点暴露 CONFIG_MISSING。
            config_error = exc
            settings = None

    db = Database(settings) if settings is not None else None

    @asynccontextmanager
    async def lifespan(application):
        task = None
        if db is not None and settings.background_tasks_enabled:
            from app.services.background import run_loop
            task = asyncio.create_task(run_loop(db, settings))
        application.state.background_worker = task
        try:
            yield
        finally:
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            if db is not None:
                await db.close()

    app = FastAPI(
        lifespan=lifespan,
        title="AI Learning Memory OS",
        version=API_VERSION,
        description="AI 学习记忆与复习系统 API v1",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    app.state.database = db
    app.state.settings = settings
    app.state.config_error = config_error
    app.state.background_worker = None
    app.state.telemetry = Telemetry()

    if settings is not None:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=[
                "Authorization",
                "Content-Type",
                "Idempotency-Key",
                "If-Match",
                "X-Request-ID",
                "X-Memory-Client",
            ],
            expose_headers=["X-Request-ID"],
        )
    install_request_context(app)
    app.add_middleware(ApiTelemetryMiddleware, telemetry=app.state.telemetry)

    async def service_error(request, exc):
        body = error_response(
            exc.code,
            str(exc),
            request_id=get_request_id(request),
            retryable=exc.code == "RATE_LIMITED",
        )
        headers = (
            {"Retry-After": str(settings.login_lock_minutes * 60)}
            if exc.code == "RATE_LIMITED" and settings
            else None
        )
        return JSONResponse(
            status_code=HTTP_STATUS_BY_CODE.get(exc.code, 500),
            content=body.model_dump(mode="json"),
            headers=headers,
        )

    from app.ai.errors import AIIntegrationError
    app.add_exception_handler(AIIntegrationError, service_error)
    app.add_exception_handler(ServiceError, service_error)
    app.add_exception_handler(ReviewError, service_error)
    from app.api.auth import router as auth_router

    app.include_router(auth_router, prefix="/api/v1")
    from app.api.learning import router as learning_router
    from app.api.admin import router as admin_router
    from app.api.admin_connectors import router as admin_connectors_router
    from app.api.admin_operations import router as admin_operations_router
    from app.api.admin_policies import router as admin_policies_router
    from app.api.notion import router as notion_router
    from app.api.ai_runtime import router as ai_router
    from app.api.workspace import router as workspace_router

    app.include_router(learning_router, prefix="/api/v1")
    app.include_router(admin_router, prefix="/api/v1")
    app.include_router(admin_connectors_router, prefix="/api/v1")
    app.include_router(admin_operations_router, prefix="/api/v1")
    app.include_router(admin_policies_router, prefix="/api/v1")
    app.include_router(notion_router, prefix="/api/v1")
    app.include_router(ai_router, prefix="/api/v1")
    app.include_router(workspace_router, prefix="/api/v1")
    from sqlalchemy.exc import IntegrityError

    async def integrity_error(request, exc):
        code = (
            "DUPLICATE_RESOURCE"
            if getattr(exc.orig, "sqlstate", None) == "23505"
            else "VALIDATION_ERROR"
        )
        body = error_response(code, "数据重复或关联约束不满足", request_id=get_request_id(request))
        return JSONResponse(
            status_code=HTTP_STATUS_BY_CODE[code], content=body.model_dump(mode="json")
        )

    app.add_exception_handler(IntegrityError, integrity_error)

    health_router = build_health_router(
        get_settings=lambda: app.state.settings,
        get_config_error=lambda: app.state.config_error,
        get_database=lambda: app.state.database,
    )
    # 裸路径（探针 / BE-01 要求）与契约基路径 /api/v1 均可用。
    app.include_router(health_router)
    app.include_router(health_router, prefix="/api/v1")

    return app


app: Any = create_app()
