"""Administrator-only inventory and creation of private PostgreSQL archives."""

import asyncio
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
from tempfile import NamedTemporaryFile
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.config import assert_database_configured
from app.secret_files import restrict_file
from app.services.accounts import audit
from app.services.admin import staff
from app.services.common import ServiceError

BACKUP_LOCK = 7310117
POSTGRES_QUERY_ENV = {
    "sslmode": "PGSSLMODE",
    "sslrootcert": "PGSSLROOTCERT",
    "sslcert": "PGSSLCERT",
    "sslkey": "PGSSLKEY",
    "connect_timeout": "PGCONNECT_TIMEOUT",
    "options": "PGOPTIONS",
}


def backup_location(settings):
    directory_value = settings.get("ADMIN_BACKUP_DIRECTORY") if settings else None
    tool_value = settings.get("ADMIN_PG_DUMP_PATH") if settings else None
    if not directory_value or not tool_value:
        return None
    directory, tool = Path(directory_value), Path(tool_value)
    directory_ready = directory.is_absolute() and directory.is_dir() and not directory.is_symlink()
    tool_ready = tool.is_absolute() and tool.is_file() and not tool.is_symlink()
    if not (directory_ready and tool_ready):
        return None
    return directory, tool


def _item(file):
    if file.is_symlink() or not file.is_file():
        return None
    try:
        identifier = UUID(file.stem.removeprefix("backup-"))
        metadata = file.stat()
    except (OSError, ValueError):
        return None
    if not metadata.st_size:
        return None
    return {
        "id": identifier,
        "filename": file.name,
        "created_at": datetime.fromtimestamp(metadata.st_mtime, timezone.utc),
        "size_bytes": metadata.st_size,
    }


def inventory(settings):
    location = backup_location(settings)
    if not location:
        return {"enabled": False, "items": []}
    try:
        records = [item for file in location[0].glob("backup-*.dump") if (item := _item(file))]
    except OSError:
        raise ServiceError("SERVICE_UNAVAILABLE", "无法读取备份目录") from None
    return {"enabled": True, "items": sorted(records, key=lambda row: row["created_at"], reverse=True)[:100]}


def _postgres_environment(settings):
    url = make_url(assert_database_configured(settings))
    if not (url.host and url.port and url.database and url.username):
        raise ServiceError("SERVICE_UNAVAILABLE", "备份连接必须显式指定数据库主机、端口、库名和用户")
    if url.query.keys() - POSTGRES_QUERY_ENV.keys():
        raise ServiceError("SERVICE_UNAVAILABLE", "备份连接包含未支持的参数")
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith("PG")}
    fields = {
        "PGHOST": url.host,
        "PGPORT": str(url.port) if url.port else None,
        "PGUSER": url.username,
        "PGPASSWORD": url.password,
        "PGDATABASE": url.database,
    }
    for key, value in url.query.items():
        if not isinstance(value, str):
            raise ServiceError("SERVICE_UNAVAILABLE", "备份连接参数必须为单值")
        fields[POSTGRES_QUERY_ENV[key]] = value
    env.update({key: value for key, value in fields.items() if value is not None})
    return env


def _dump(settings, tool, target):
    env = _postgres_environment(settings)
    with NamedTemporaryFile(dir=target.parent, prefix=".backup-", suffix=".partial", delete=False) as file:
        partial = Path(file.name)
    try:
        restrict_file(partial)
        result = subprocess.run(
            [str(tool), "--format=custom", "--no-owner", "--no-privileges", "--no-password", "--file", str(partial)],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=90,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            check=False,
        )
        if result.returncode or not partial.stat().st_size:
            raise ServiceError("SERVICE_UNAVAILABLE", "创建备份失败，请检查数据库权限和 pg_dump")
        partial.replace(target)
        return _item(target)
    except (OSError, subprocess.SubprocessError):
        raise ServiceError("SERVICE_UNAVAILABLE", "创建备份失败或已超时") from None
    finally:
        partial.unlink(missing_ok=True)


async def create(db, settings, actor, key, ip, request_id):
    location = backup_location(settings)
    if not location:
        raise ServiceError("SERVICE_UNAVAILABLE", "备份未配置")
    directory, tool = location
    identity = uuid5(NAMESPACE_URL, f"ailmos:admin:backup:{actor.user_id}:{key}")
    target = directory / f"backup-{identity}.dump"
    cancelled = False
    async with db.transaction() as session:
        user = await staff(session, actor)
        obtained = await session.scalar(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": BACKUP_LOCK})
        if not obtained:
            raise ServiceError("INVALID_STATE", "另一项数据库备份正在运行")
        item = _item(target)
        if item is not None:
            return item
        archive = asyncio.create_task(asyncio.to_thread(_dump, settings, tool, target))
        try:
            item = await asyncio.shield(archive)
        except asyncio.CancelledError:
            # Keep the database lock until the archive and its audit record are complete.
            cancelled = True
            item = await archive
        audit(session, user, "admin_backup_created", str(identity), "allowed", ip, request_id)
    if cancelled:
        raise asyncio.CancelledError
    return item
