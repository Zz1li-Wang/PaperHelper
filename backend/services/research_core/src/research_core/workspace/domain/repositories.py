"""Workspace 聚合的持久化端口。

端口声明在领域层、实现在 outbound adapter（§4 分层职责）。这里只描述"应用层需要什么"，
不出现任何 ORM 类型——所以它是纯 Protocol，可以被 fake 实现替换进单测。
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from research_core.workspace.domain.enums import WorkspaceStatus
from research_core.workspace.domain.workspace import Workspace


class WorkspaceRepository(Protocol):
    """工作空间聚合的读写。"""

    async def add(self, workspace: Workspace) -> None:
        """插入新工作空间（`CreateWorkspace`）。"""

    async def get(self, workspace_id: UUID) -> Workspace | None:
        """按 id 读取；不存在时返回 `None`。

        "不存在"（404）与"存在但不满足约束"（409 / 422）由应用层区分，端口不做错误映射。
        """

    async def list_by_owner(
        self,
        *,
        owner_id: str,
        status: WorkspaceStatus | None,
        include_deleted: bool,
        limit: int,
        offset: int,
    ) -> tuple[list[Workspace], int]:
        """按 owner 列出工作空间，返回 `(当页行, 总行数)`。

        过滤口径（§7.3 的列表通则）：

        - 给了 `status` → 精确匹配该状态，`include_deleted` 不再参与；
        - 没给 → 默认只返回 `active`；`include_deleted=True` 则放开为**全部状态**（含 archived
          与 deleted）。

        排序键固定为 `(created_at DESC, id ASC)`：`id` 是 tiebreaker，**不是可选项**——同一事务
        写入的多行 `created_at` 完全相同，只按时间排序在 OFFSET 分页下会重复或漏项。
        """

    async def save(self, workspace: Workspace, *, expected_version: int) -> None:
        """按 `WHERE id = ? AND version = ?` 写入聚合自身字段。

        `expected_version` 是**变更前**的版本；不匹配抛
        `research_core.workspace.domain.errors.VersionConflictError`，并带上数据库里的当前版本。

        实现必须遵守 §5.2 的列集合互斥：这条 UPDATE **不写 `context_version`**（也不写 `type` /
        `created_at`）。引用变更只走另一条无条件自增的 UPDATE——把 `context_version` 混进自身字段的
        写里，会在并发场景下把序列号写回旧值，副本静默漏同步。
        """
