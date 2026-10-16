"""Research Core 的数据库装配。

`bootstrap/` 是服务唯一的 composition root：它读配置、建引擎、把适配器装进应用服务。
这里只做"建对象"，不读环境变量——HTTP 入口进来时由入站层/启动脚本把 URL 传进来
（本地取值见 `backend/.env.example` 的 `PAPER_HELPER_RESEARCH_CORE_DATABASE_URL`）。
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def build_engine(database_url: str) -> AsyncEngine:
    """建服务自己的引擎；URL 必须是 `postgresql+asyncpg`（`migrations/env.py` 同规则）。"""
    return create_async_engine(database_url, pool_pre_ping=True)


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """建会话工厂。

    `expire_on_commit=False`：提交之后应用层仍要读聚合根来拼返回体，让属性在提交后失效会再打
    一次数据库——而那时读到的已经是另一条快照了。
    """
    return async_sessionmaker(engine, expire_on_commit=False)
