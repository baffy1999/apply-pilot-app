from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from config import DATABASE_URL
from database import Base
from models.certification import Certification  # noqa: F401
from models.education import Education  # noqa: F401
from models.experience import Experience  # noqa: F401
from models.project import Project  # noqa: F401
from models.resume import Resume  # noqa: F401
from models.skill import Skill  # noqa: F401
from models.user_info import UserInfo  # noqa: F401


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not configured")

config.set_main_option("sqlalchemy.url", DATABASE_URL)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
