"""`WorkspaceRepository` 的 SQLAlchemy 实现。

写入规则来自 `workspace_1.md` W3.3：**自身字段的 UPDATE 与 `context_version` 的 UPDATE 列集合
互斥**。这条实现只做前者——它的列集合里没有 `context_version`，也没有 `type` / `created_at`
（它们不随命令变化）。引用变更走另一条无条件自增的语句（随引用切片加进来）。
"""

from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from research_core.workspace.adapters.outbound.persistence.models import WorkspaceModel
from research_core.workspace.domain.enums import Visibility, WorkspaceStatus, WorkspaceType
from research_core.workspace.domain.errors import VersionConflictError, WorkspaceNotFoundError
from research_core.workspace.domain.workspace import Workspace


def to_domain(row: WorkspaceModel) -> Workspace:
    """行 → 聚合根。枚举在这里还原成 StrEnum，聚合根随后自查不变量。"""
    return Workspace(
        id=row.id,
        type=WorkspaceType(row.type),
        title=row.title,
        description=row.description,
        version=row.version,
        context_version=row.context_version,
        owner_id=row.owner_id,
        visibility=Visibility(row.visibility),
        status=WorkspaceStatus(row.status),
        archived_at=row.archived_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def to_row(workspace: Workspace) -> WorkspaceModel:
    return WorkspaceModel(
        id=workspace.id,
        type=workspace.type.value,
        title=workspace.title,
        description=workspace.description,
        version=workspace.version,
        context_version=workspace.context_version,
        owner_id=workspace.owner_id,
        visibility=workspace.visibility.value,
        status=workspace.status.value,
        archived_at=workspace.archived_at,
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
    )


class SqlAlchemyWorkspaceRepository:
    """工作空间聚合的读写。事务由 `SqlAlchemyUnitOfWork` 持有，这里只用它的会话。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, workspace: Workspace) -> None:
        self._session.add(to_row(workspace))
        # 立即 flush：约束冲突（CHECK、主键）要在事务内、在调用方以为成功之前暴露出来。
        await self._session.flush()

    async def get(self, workspace_id: UUID) -> Workspace | None:
        row = await self._session.get(WorkspaceModel, workspace_id)
        return None if row is None else to_domain(row)

    async def list_by_owner(
        self,
        *,
        owner_id: str,
        status: WorkspaceStatus | None,
        include_deleted: bool,
        limit: int,
        offset: int,
    ) -> tuple[list[Workspace], int]:
        filters = [WorkspaceModel.owner_id == owner_id]
        if status is not None:
            filters.append(WorkspaceModel.status == status.value)
        elif not include_deleted:
            filters.append(WorkspaceModel.status == WorkspaceStatus.ACTIVE.value)

        rows = await self._session.scalars(
            sa.select(WorkspaceModel)
            .where(*filters)
            # id 不是可选的 tiebreaker：同一事务写入的多行 created_at 完全相同，
            # 只按时间排序在 OFFSET 分页下会重复或漏项（§7.3）。
            .order_by(WorkspaceModel.created_at.desc(), WorkspaceModel.id.asc())
            .limit(limit)
            .offset(offset)
        )
        # 计数与取数分两条语句，但同一个只读事务：total 是"当前过滤条件下的总数"，不是本页行数。
        total = await self._session.scalar(
            sa.select(sa.func.count()).select_from(WorkspaceModel).where(*filters)
        )
        return [to_domain(row) for row in rows], int(total or 0)

    async def save(self, workspace: Workspace, *, expected_version: int) -> None:
        result = await self._session.execute(
            sa.update(WorkspaceModel)
            .where(
                WorkspaceModel.id == workspace.id,
                # CAS：并发写者已经把版本推进了，我们这条 UPDATE 就匹配不到行。
                WorkspaceModel.version == expected_version,
            )
            .values(
                title=workspace.title,
                description=workspace.description,
                owner_id=workspace.owner_id,
                visibility=workspace.visibility.value,
                status=workspace.status.value,
                archived_at=workspace.archived_at,
                version=workspace.version,
                updated_at=workspace.updated_at,
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            raise VersionConflictError(current_version=await self._current_version(workspace.id))

    async def _current_version(self, workspace_id: UUID) -> int:
        """读数据库里的当前版本，供 409 响应回带 `currentVersion`（§9.2）。

        走标量 SELECT 而不是实体加载：实体加载会被 identity map 用同一个事务里读过的旧值喂回来。
        """
        version = await self._session.scalar(
            sa.select(WorkspaceModel.version).where(WorkspaceModel.id == workspace_id)
        )
        if version is None:
            raise WorkspaceNotFoundError(f"workspace {workspace_id} does not exist")
        return version
