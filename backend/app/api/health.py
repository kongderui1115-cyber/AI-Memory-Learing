"""Process liveness and actual PostgreSQL/schema readiness checks."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Response
from starlette.responses import JSONResponse

from app.config import ConfigMissingError, Settings, assert_database_configured


REQUIRED_SCHEMA_REVISION = "0006_notion_lifecycle"


def build_health_router(
    get_settings: Callable[[], Settings | None],
    get_config_error: Callable[[], BaseException | None],
    get_database: Callable[[], Any] | None = None,
) -> APIRouter:
    router = APIRouter(tags=["health"])

    @router.get("/health")
    @router.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/health/ready")
    async def ready(response: Response) -> Any:
        checks: dict[str, Any] = {}
        error = get_config_error()
        settings = get_settings()

        if error is not None or settings is None:
            checks["config"] = {
                "status": "error",
                "code": "CONFIG_MISSING",
                "detail": str(error) if error is not None else "配置未加载",
            }
            body = {"status": "unavailable", "checks": checks}
            return JSONResponse(status_code=503, content=body)

        checks["config"] = {"status": "ok"}
        try:
            assert_database_configured(settings)
            from sqlalchemy import text

            database = get_database() if get_database else None
            if database is None:
                raise ConfigMissingError(["DATABASE_URL"])
            async with database.transaction() as session:
                await session.execute(text("SELECT 1"))
                revisions = tuple(await session.scalars(text("SELECT version_num FROM alembic_version")))
                await session.execute(text("SELECT role FROM users LIMIT 0"))
            database_ok = revisions == (REQUIRED_SCHEMA_REVISION,)
            if database_ok:
                checks["database"] = {"status": "ok", "migration": revisions[0]}
            else:
                checks["database"] = {
                    "status": "error",
                    "code": "SCHEMA_VERSION_MISMATCH",
                    "expected_migration": REQUIRED_SCHEMA_REVISION,
                }
        except Exception:
            checks["database"] = {
                "status": "error",
                "code": "SERVICE_UNAVAILABLE",
                "detail": "数据库连接或迁移未就绪",
            }
            database_ok = False

        is_ready = database_ok
        response.status_code = 200 if is_ready else 503
        return {"status": "ready" if is_ready else "unavailable", "checks": checks}

    return router


__all__ = ["build_health_router"]
