"""事务边界端口（§4）。

一次命令 = 一个 `UnitOfWork` = 一个本地事务。跨聚合的「读-判-写」由应用服务在这个边界内编排，
领域层只收结论。

业务写与 `outbox_event` 追加共用同一个事务（§4 的固定动作序列）：应用服务先写业务行、再
`outbox.add(...)`、最后 `commit()`；任何一步失败都一起回滚，不做补偿。
"""

from __future__ import annotations

from types import TracebackType
from typing import Protocol, Self

from research_core.workspace.application.outbox import OutboxRepository
from research_core.workspace.domain.repositories import WorkspaceRepository


class UnitOfWork(Protocol):
    """事务作用域：进入即开始，`commit()` 提交，未提交即回滚。"""

    @property
    def workspaces(self) -> WorkspaceRepository:
        """工作空间聚合的仓储入口。"""

    @property
    def outbox(self) -> OutboxRepository:
        """待发布事件的写入入口；与业务写共用本事务。"""

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None:
        """提交本次事务。"""
