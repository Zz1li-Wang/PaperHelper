"""Alembic environment owned by Knowledge Service."""

import asyncio
import os
from collections.abc import Iterable
from logging.config import fileConfig

from alembic import context
from alembic.operations.ops import MigrationScript
from alembic.runtime.migration import MigrationContext
from knowledge_service.adapters.outbound.persistence.database import OrmBase
from knowledge_service.adapters.outbound.persistence.orm_registry import import_orm_models
from sqlalchemy import Connection, pool
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_engine_from_config

ENV_NAME = "PAPER_HELPER_KNOWLEDGE_DATABASE_URL"
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _database_url() -> str:
    database_url = os.getenv(ENV_NAME)
    if not database_url:
        raise RuntimeError(f"{ENV_NAME} is required when running Alembic commands")
    if make_url(database_url).drivername != "postgresql+asyncpg":
        raise RuntimeError(f"{ENV_NAME} must use the postgresql+asyncpg driver")
    return database_url


config.set_main_option("sqlalchemy.url", _database_url().replace("%", "%%"))
import_orm_models()
target_metadata = OrmBase.metadata


def _process_revision_directives(
    _migration_context: MigrationContext,
    _revision: str | Iterable[str | None] | Iterable[str],
    directives: list[MigrationScript],
) -> None:
    if not directives:
        return
    command = getattr(config.cmd_opts, "cmd", None)
    command_function = command[0] if isinstance(command, tuple) and command else None
    if (
        not callable(command_function)
        or command_function.__name__ != "revision"
        or not getattr(config.cmd_opts, "autogenerate", False)
    ):
        return
    script = directives[0]
    if script.upgrade_ops is not None and script.upgrade_ops.is_empty():
        directives.clear()


def _context_options() -> dict[str, object]:
    return {
        "target_metadata": target_metadata,
        "compare_type": True,
        "compare_server_default": True,
        "compare_check_constraints": True,
        "process_revision_directives": _process_revision_directives,
    }


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **_context_options(),
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, **_context_options())
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    try:
        async with connectable.connect() as connection:
            await connection.run_sync(_run_migrations)
    finally:
        await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
