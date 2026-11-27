"""Alembic 环境配置（BE-02）。

- 连接串从 :func:`app.config.load_settings` + ``assert_database_configured`` 读取，
  未配置 / 占位符 / 非 PostgreSQL 时明确报 ``ConfigMissingError``（不静默降级）；
- ``target_metadata`` 指向 ORM ``Base.metadata``，支持 autogenerate 对比；
- 本机依赖未安装、数据库凭据未确认，**迁移脚本尚未执行**（如实标注）。

运行（依赖与授权齐备后，在 backend/ 目录）：
    alembic upgrade head
"""
from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# 保证能从 backend/ 或项目根运行 alembic 时导入 app 包。
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import assert_database_configured, load_settings  # noqa: E402
from app.models import target_metadata  # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def get_url() -> str:
    settings = load_settings()
    return assert_database_configured(settings)


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        url=get_url(),
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
