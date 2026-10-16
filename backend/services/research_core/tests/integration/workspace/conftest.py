"""workspace 集成测试的共用装置。

需要一个**一次性数据库**：这里会 `DROP SCHEMA public CASCADE`，并在每个用例前清表。所以整组测试
只在 `PAPER_HELPER_RESEARCH_CORE_TEST_DATABASE_URL` 指向该库时才运行，未配置就整体跳过——与
`platform_messaging` 的 RabbitMQ 集成测试同一写法。

```bash
export PAPER_HELPER_RESEARCH_CORE_TEST_DATABASE_URL=postgresql+asyncpg://user:pw@127.0.0.1:5432/paper_helper_research_test
uv run pytest services/research_core/tests/integration
```
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from research_core.bootstrap.database import build_engine, build_session_factory
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

SERVICE_ROOT = Path(__file__).resolve().parents[3]
TEST_DATABASE_URL = os.getenv("PAPER_HELPER_RESEARCH_CORE_TEST_DATABASE_URL")

#: 每个用例开头清空的表。加表时一起加进来，否则用例之间会互相看见对方的行。
TABLES = ("workspace", "outbox_event")


def pytest_collection_modifyitems(config: Config, items: list[pytest.Item]) -> None:
    if TEST_DATABASE_URL:
        return
    skip = pytest.mark.skip(
        reason="PAPER_HELPER_RESEARCH_CORE_TEST_DATABASE_URL is not configured"
    )
    for item in items:
        item.add_marker(skip)


async def _reset_schema(database_url: str) -> None:
    engine = build_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(sa.text("DROP SCHEMA public CASCADE"))
            await connection.execute(sa.text("CREATE SCHEMA public"))
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def alembic_config() -> Config:
    """Alembic 环境读的是服务自己的环境变量，这里把它指向一次性测试库。"""
    os.environ["PAPER_HELPER_RESEARCH_CORE_DATABASE_URL"] = TEST_DATABASE_URL or ""
    return Config(SERVICE_ROOT / "alembic.ini")


@pytest.fixture(scope="module")
def migrated_database(alembic_config: Config) -> str:
    database_url = TEST_DATABASE_URL or ""
    asyncio.run(_reset_schema(database_url))
    command.upgrade(alembic_config, "head")
    return database_url


@pytest.fixture(autouse=True)
async def _empty_tables(migrated_database: str) -> AsyncIterator[None]:
    """每个用例从空表开始：整个目录共用一个库，用例之间不能互相看到对方的行。"""
    engine = build_engine(migrated_database)
    try:
        async with engine.begin() as connection:
            await connection.execute(sa.text(f"TRUNCATE TABLE {', '.join(TABLES)}"))
        yield
    finally:
        await engine.dispose()


@pytest.fixture
async def session_factory(
    migrated_database: str,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = build_engine(migrated_database)
    try:
        yield build_session_factory(engine)
    finally:
        await engine.dispose()


@pytest.fixture
def database_url(migrated_database: str) -> str:
    return migrated_database


@pytest.fixture
def workspace_id() -> str:
    return "3f1c2b8a-9d4e-4a17-8b52-0c6f7e1d2a35"


@pytest.fixture
def request_id() -> str:
    return "b57a9b8f-2312-48f7-a360-19e40121dd91"


@pytest.fixture
def authorization() -> Iterator[dict[str, str]]:
    return {"Authorization": "Bearer user-1"}
