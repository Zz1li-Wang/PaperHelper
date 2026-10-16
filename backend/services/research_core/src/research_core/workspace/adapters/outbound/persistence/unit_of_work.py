"""`UnitOfWork` 的 SQLAlchemy 实现：一次事务一个 `AsyncSession`。

会话在进入作用域时创建、退出时关闭；没有 `commit()` 就退出即回滚。加锁顺序
（`workspace → resource_ref → session`，§4）在只碰工作空间表时无从体现，引用与会话切片进来后
必须由应用层的编排顺序保证——这里不做任何跨聚合的隐式加锁。
"""

from __future__ import annotations

from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from research_core.adapters.outbound.persistence.outbox import SqlAlchemyOutboxRepository
from research_core.workspace.adapters.outbound.persistence.repositories import (
    SqlAlchemyWorkspaceRepository,
)


class SqlAlchemyUnitOfWork:
    """见 `application/unit_of_work.py` 的端口定义。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None
        self._workspaces: SqlAlchemyWorkspaceRepository | None = None
        self._outbox: SqlAlchemyOutboxRepository | None = None

    @property
    def workspaces(self) -> SqlAlchemyWorkspaceRepository:
        return self._require_repository()

    @property
    def outbox(self) -> SqlAlchemyOutboxRepository:
        if self._outbox is None:
            raise RuntimeError("unit of work is not active; use it as an async context manager")
        return self._outbox

    async def __aenter__(self) -> Self:
        self._session = self._session_factory()
        self._workspaces = SqlAlchemyWorkspaceRepository(self._session)
        # 与业务写共用一个会话：这就是"同事务"的实现方式，不额外开事务、不做补偿。
        self._outbox = SqlAlchemyOutboxRepository(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        session = self._require_session()
        try:
            if exc_type is not None:
                await session.rollback()
        finally:
            await session.close()
            self._session = None
            self._workspaces = None
            self._outbox = None

    async def commit(self) -> None:
        await self._require_session().commit()

    def _require_session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("unit of work is not active; use it as an async context manager")
        return self._session

    def _require_repository(self) -> SqlAlchemyWorkspaceRepository:
        if self._workspaces is None:
            raise RuntimeError("unit of work is not active; use it as an async context manager")
        return self._workspaces
