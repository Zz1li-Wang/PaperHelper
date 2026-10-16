"""工作空间生命周期用例（§6.1）。

每个方法是一个命令：**开一个 `UnitOfWork`、在事务内完成「加载 → 权限 → 版本 → 领域方法 →
写业务行 → 追加 outbox → commit」**，跨聚合的读-判-写都编排在这一层（§4 分层职责）。领域层只收
结论。

写路径的固定动作序列（§4）：业务行与 `outbox_event` **同一事务**，任何一步失败一起回滚——所以
`outbox.add(...)` 必须在 `commit()` 之前、复用同一个事务作用域，不做补偿、不开第二个事务。

`request_id` 是命令契约的一部分（§6.1），它唯一的去处是 outbox 行的 `correlation_id`。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from research_core.workspace.application.actors import Actor
from research_core.workspace.application.dto import (
    ActorView,
    WorkspaceCommandResult,
    WorkspacePage,
    WorkspacePatch,
    WorkspaceSnapshot,
    WorkspaceView,
)
from research_core.workspace.application.outbox import build_outbox_records
from research_core.workspace.application.permissions import available_actions, require_permission
from research_core.workspace.application.unit_of_work import UnitOfWork
from research_core.workspace.domain.enums import (
    Relation,
    Visibility,
    WorkspaceAction,
    WorkspaceStatus,
)
from research_core.workspace.domain.errors import VersionConflictError, WorkspaceNotFoundError
from research_core.workspace.domain.events import WorkspaceEvent
from research_core.workspace.domain.workspace import Workspace


def utcnow() -> datetime:
    """默认时钟：领域方法都要求传入时间，这里只负责"现在"这一个取值。"""
    return datetime.now(UTC)


#: 分页默认值与上限（§7.3：默认 50、上限 200）。**契约常量**，不做成可配置项。
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


class WorkspaceService:
    """工作空间生命周期的六个命令 + 读路径。

    `unit_of_work` 是工厂而不是实例：每个命令各自开一个事务，命令之间不共享会话。
    """

    def __init__(
        self,
        *,
        unit_of_work: Callable[[], UnitOfWork],
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock

    async def create_workspace(
        self,
        *,
        actor: Actor,
        title: str,
        description: str | None = None,
        visibility: Visibility = Visibility.PRIVATE,
        request_id: UUID,
    ) -> WorkspaceCommandResult:
        """CreateWorkspace：`workspace:create` 没有目标对象，任何已认证 actor 都可以建。

        创建者即 owner——`workspaceMeta.ownerId` 取 `actor.id`。
        """
        now = self._clock()
        workspace, event = Workspace.create(
            title=title,
            owner_id=actor.id,
            description=description,
            visibility=visibility,
            occurred_at=now,
        )
        async with self._unit_of_work() as unit_of_work:
            await unit_of_work.workspaces.add(workspace)
            await self._append_events(
                unit_of_work,
                (event,),
                workspace=workspace,
                actor=actor,
                occurred_at=now,
                request_id=request_id,
            )
            await unit_of_work.commit()
        return WorkspaceCommandResult(
            snapshot=self._snapshot(workspace, actor, Relation.OWNER),
            events=(event,),
        )

    async def update_workspace(
        self,
        *,
        actor: Actor,
        workspace_id: UUID,
        patch: WorkspacePatch,
        expected_version: int,
        request_id: UUID,
    ) -> WorkspaceCommandResult:
        """UpdateWorkspace：修改 / 状态转移类命令，`expectedVersion` 必填（§5.3）。"""
        now = self._clock()
        async with self._unit_of_work() as unit_of_work:
            workspace = await self._load(unit_of_work, workspace_id)
            relation = require_permission(
                workspace=workspace, actor=actor, action=WorkspaceAction.WORKSPACE_UPDATE
            )
            self._require_expected_version(workspace, expected_version)
            events = workspace.update(
                occurred_at=now,
                title=patch.title,
                description=patch.description,
                visibility=patch.visibility,
            )
            if events:
                await unit_of_work.workspaces.save(workspace, expected_version=expected_version)
                await self._append_events(
                    unit_of_work,
                    events,
                    workspace=workspace,
                    actor=actor,
                    occurred_at=now,
                    request_id=request_id,
                )
                await unit_of_work.commit()
            return self._result(workspace, actor, relation, events)

    async def archive_workspace(
        self,
        *,
        actor: Actor,
        workspace_id: UUID,
        expected_version: int,
        reason: str | None = None,
        request_id: UUID,
    ) -> WorkspaceCommandResult:
        """ArchiveWorkspace：只读封存。对已归档的工作空间返回 409，不是幂等无操作（§3.8）。"""
        now = self._clock()
        async with self._unit_of_work() as unit_of_work:
            workspace = await self._load(unit_of_work, workspace_id)
            relation = require_permission(
                workspace=workspace, actor=actor, action=WorkspaceAction.WORKSPACE_ARCHIVE
            )
            self._require_expected_version(workspace, expected_version)
            events = workspace.archive(occurred_at=now, reason=reason)
            await unit_of_work.workspaces.save(workspace, expected_version=expected_version)
            await self._append_events(
                unit_of_work,
                events,
                workspace=workspace,
                actor=actor,
                occurred_at=now,
                request_id=request_id,
            )
            await unit_of_work.commit()
            return self._result(workspace, actor, relation, events)

    async def restore_workspace(
        self,
        *,
        actor: Actor,
        workspace_id: UUID,
        expected_version: int,
        request_id: UUID,
    ) -> WorkspaceCommandResult:
        """RestoreWorkspace：对已 active 的工作空间是幂等无操作（不写库、不发事件）。"""
        now = self._clock()
        async with self._unit_of_work() as unit_of_work:
            workspace = await self._load(unit_of_work, workspace_id)
            relation = require_permission(
                workspace=workspace, actor=actor, action=WorkspaceAction.WORKSPACE_RESTORE
            )
            self._require_expected_version(workspace, expected_version)
            events = workspace.restore(occurred_at=now)
            if events:
                await unit_of_work.workspaces.save(workspace, expected_version=expected_version)
                await self._append_events(
                    unit_of_work,
                    events,
                    workspace=workspace,
                    actor=actor,
                    occurred_at=now,
                    request_id=request_id,
                )
                await unit_of_work.commit()
            return self._result(workspace, actor, relation, events)

    async def transfer_ownership(
        self,
        *,
        actor: Actor,
        workspace_id: UUID,
        new_owner_id: str,
        expected_version: int,
        request_id: UUID,
    ) -> WorkspaceCommandResult:
        """TransferOwnership：`archived` 也允许（§8）；转给当前 owner 是无操作。"""
        now = self._clock()
        async with self._unit_of_work() as unit_of_work:
            workspace = await self._load(unit_of_work, workspace_id)
            relation = require_permission(
                workspace=workspace,
                actor=actor,
                action=WorkspaceAction.WORKSPACE_TRANSFER_OWNERSHIP,
            )
            self._require_expected_version(workspace, expected_version)
            events = workspace.transfer_ownership(new_owner_id=new_owner_id, occurred_at=now)
            if events:
                await unit_of_work.workspaces.save(workspace, expected_version=expected_version)
                await self._append_events(
                    unit_of_work,
                    events,
                    workspace=workspace,
                    actor=actor,
                    occurred_at=now,
                    request_id=request_id,
                )
                await unit_of_work.commit()
            return self._result(workspace, actor, relation, events)

    async def delete_workspace(
        self,
        *,
        actor: Actor,
        workspace_id: UUID,
        expected_version: int,
        request_id: UUID,
    ) -> WorkspaceCommandResult:
        """DeleteWorkspace：**单行写、不级联**（§3.2），响应按 §7.4 不带快照。"""
        now = self._clock()
        async with self._unit_of_work() as unit_of_work:
            workspace = await self._load(unit_of_work, workspace_id)
            require_permission(
                workspace=workspace, actor=actor, action=WorkspaceAction.WORKSPACE_DELETE
            )
            self._require_expected_version(workspace, expected_version)
            events = workspace.delete(occurred_at=now)
            await unit_of_work.workspaces.save(workspace, expected_version=expected_version)
            await self._append_events(
                unit_of_work,
                events,
                workspace=workspace,
                actor=actor,
                occurred_at=now,
                request_id=request_id,
            )
            await unit_of_work.commit()
            return WorkspaceCommandResult(snapshot=None, events=events)

    async def get_workspace(self, *, actor: Actor, workspace_id: UUID) -> WorkspaceSnapshot:
        """GetWorkspace：读路径。`archived` 允许读，`deleted` 一律 409（§8）。"""
        async with self._unit_of_work() as unit_of_work:
            return await self._readable_snapshot(
                unit_of_work, actor=actor, workspace_id=workspace_id
            )

    async def get_workspace_snapshot(
        self, *, actor: Actor, workspace_id: UUID
    ) -> WorkspaceSnapshot:
        """GetWorkspaceSnapshot（§3.6）。

        本轮它与 `GetWorkspace` 的返回体**完全相同**：三个列表随各自聚合落地，`compositionVersion`
        也还恒等于 `version`。路由先按设计挂上，否则契约里会缺一条已承诺的接口。
        """
        async with self._unit_of_work() as unit_of_work:
            return await self._readable_snapshot(
                unit_of_work, actor=actor, workspace_id=workspace_id
            )

    async def list_workspaces(
        self,
        *,
        actor: Actor,
        status: WorkspaceStatus | None = None,
        include_deleted: bool = False,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> WorkspacePage:
        """ListWorkspaces：只列 actor 自己的工作空间（§7.5）。

        `workspace:list` 没有目标工作空间，所以不查动作表——**过滤条件本身就是权限边界**：
        别人的工作空间不会出现在结果里。

        `pageSize` 超过上限**夹到 200 而不是报 400**：它是展示参数，不是业务约束，为此让客户端
        写一段错误处理不划算。夹后的值会回带在响应里。
        """
        resolved_page = max(page, 1)
        resolved_page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
        async with self._unit_of_work() as unit_of_work:
            workspaces, total = await unit_of_work.workspaces.list_by_owner(
                owner_id=actor.id,
                status=status,
                include_deleted=include_deleted,
                limit=resolved_page_size,
                offset=(resolved_page - 1) * resolved_page_size,
            )
        return WorkspacePage(
            items=tuple(WorkspaceView.from_domain(workspace) for workspace in workspaces),
            total=total,
            page=resolved_page,
            page_size=resolved_page_size,
        )

    async def _readable_snapshot(
        self, unit_of_work: UnitOfWork, *, actor: Actor, workspace_id: UUID
    ) -> WorkspaceSnapshot:
        """「加载 → 权限 → 状态约束」——GetWorkspace 与 GetWorkspaceSnapshot 共用这一段。"""
        workspace = await self._load(unit_of_work, workspace_id)
        relation = require_permission(
            workspace=workspace, actor=actor, action=WorkspaceAction.WORKSPACE_READ
        )
        return self._snapshot(workspace, actor, relation)

    @staticmethod
    async def _load(unit_of_work: UnitOfWork, workspace_id: UUID) -> Workspace:
        workspace = await unit_of_work.workspaces.get(workspace_id)
        if workspace is None:
            raise WorkspaceNotFoundError(f"workspace {workspace_id} does not exist")
        return workspace

    @staticmethod
    def _require_expected_version(workspace: Workspace, expected_version: int) -> None:
        if workspace.version != expected_version:
            raise VersionConflictError(current_version=workspace.version)

    @staticmethod
    async def _append_events(
        unit_of_work: UnitOfWork,
        events: tuple[WorkspaceEvent, ...],
        *,
        workspace: Workspace,
        actor: Actor,
        occurred_at: datetime,
        request_id: UUID,
    ) -> None:
        """把本命令的事件追加进 outbox——**必须在 `commit()` 之前**，否则就不是同事务了。

        `aggregate_version` 取领域方法执行后的 `workspace.version`；`occurred_at` 复用命令里那
        一个 `now`，不重新取时间。
        """
        await unit_of_work.outbox.add(
            build_outbox_records(
                events,
                workspace_id=workspace.id,
                aggregate_version=workspace.version,
                actor=actor,
                occurred_at=occurred_at,
                correlation_id=request_id,
            )
        )

    def _result(
        self,
        workspace: Workspace,
        actor: Actor,
        relation: Relation,
        events: tuple[WorkspaceEvent, ...],
    ) -> WorkspaceCommandResult:
        return WorkspaceCommandResult(
            snapshot=self._snapshot(workspace, actor, relation),
            events=events,
        )

    @staticmethod
    def _snapshot(workspace: Workspace, actor: Actor, relation: Relation) -> WorkspaceSnapshot:
        actions = tuple(
            sorted(available_actions(workspace=workspace, actor=actor), key=lambda a: a.value)
        )
        return WorkspaceSnapshot(
            workspace=WorkspaceView.from_domain(workspace),
            actor=ActorView(actor_id=actor.id, relation=relation, permissions=actions),
            available_actions=actions,
            version=workspace.version,
            context_version=workspace.context_version,
            # max(version, 会话最大 version, 产出最大 version)：会话与产出尚未实现，
            # 所以此刻恒等于 version（§3.6）。
            composition_version=workspace.version,
        )
