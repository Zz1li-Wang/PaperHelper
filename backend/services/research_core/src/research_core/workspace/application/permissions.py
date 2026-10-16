"""权限：动作表 × 状态约束（§8）。

```text
实际允许 = 动作表(action, relation) ∩ 状态约束(status, action)
```

两张表都是数据，判定是查表——P2 引入副本时只加行、不加结构。`CheckPermission` 是应用层内部
函数，不暴露 HTTP（§7.1）；401 由入站层判定，这里只回答"这个 actor 能不能对这个对象做这个动作"。

`type` 由动作名前缀表达，**不单独作为矩阵维度**（§8）。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from research_core.workspace.application.actors import Actor
from research_core.workspace.domain.enums import (
    Relation,
    WorkspaceAction,
    WorkspaceStatus,
)
from research_core.workspace.domain.errors import (
    PermissionDeniedError,
    WorkspaceArchivedError,
    WorkspaceDeletedError,
    WorkspaceDomainError,
)
from research_core.workspace.domain.workspace import Workspace

ALL_ACTIONS: frozenset[WorkspaceAction] = frozenset(WorkspaceAction)

#: 关系 → 允许的动作。P1 只可能产出 `OWNER`（没有分享入口），另外两个值随 P2 的分享与副本落地。
RELATION_ACTIONS: Mapping[Relation, frozenset[WorkspaceAction]] = {
    Relation.OWNER: ALL_ACTIONS,
}

#: 状态 → 允许的动作。`archived` 是**只读封存**：读路径 +
#: `restore` / `delete` / `transfer_ownership`，其余写动作一律拒绝（§8）。
#: `deleted` 对全部动作拒绝——包括读，子对象因此语义不可达（§3.2）。
STATUS_ACTIONS: Mapping[WorkspaceStatus, frozenset[WorkspaceAction]] = {
    WorkspaceStatus.ACTIVE: ALL_ACTIONS,
    WorkspaceStatus.ARCHIVED: frozenset(
        {
            WorkspaceAction.WORKSPACE_READ,
            WorkspaceAction.WORKSPACE_LIST,
            WorkspaceAction.SESSION_READ,
            WorkspaceAction.SESSION_LIST,
            WorkspaceAction.WORKSPACE_RESTORE,
            WorkspaceAction.WORKSPACE_DELETE,
            WorkspaceAction.WORKSPACE_TRANSFER_OWNERSHIP,
        }
    ),
    WorkspaceStatus.DELETED: frozenset(),
}

_STATUS_ERRORS: Mapping[WorkspaceStatus, type[WorkspaceDomainError]] = {
    WorkspaceStatus.ARCHIVED: WorkspaceArchivedError,
    WorkspaceStatus.DELETED: WorkspaceDeletedError,
}


@dataclass(frozen=True, slots=True)
class PermissionDecision:
    """`CheckPermission` 的返回（§6.5）：是否允许、依据哪种关系、拒绝的原因。"""

    allowed: bool
    relation: Relation | None
    reason: str | None = None


def resolve_relation(*, workspace: Workspace, actor: Actor) -> Relation | None:
    """解析 actor 对工作空间的关系。

    P1 只产出 `owner`：没有分享入口，也没有成员模型（原则 8）。`ownerId` 只与 `actorId` 比较
    字符串，不校验存在性。
    """
    if actor.id == workspace.owner_id:
        return Relation.OWNER
    return None


def check_permission(
    *, workspace: Workspace, actor: Actor, action: WorkspaceAction
) -> PermissionDecision:
    """查表判定，不抛错——需要"拒绝即失败"的调用方用 `require_permission`。"""
    relation = resolve_relation(workspace=workspace, actor=actor)
    if relation is None or action not in RELATION_ACTIONS[relation]:
        return PermissionDecision(
            allowed=False,
            relation=relation,
            reason="action is not allowed for the actor's relation",
        )
    if action not in STATUS_ACTIONS[workspace.status]:
        return PermissionDecision(
            allowed=False,
            relation=relation,
            reason=f"action is not allowed while the workspace is {workspace.status}",
        )
    return PermissionDecision(allowed=True, relation=relation)


def require_permission(
    *, workspace: Workspace, actor: Actor, action: WorkspaceAction
) -> Relation:
    """判定并返回关系；不允许时抛带错误码语义的领域错误。

    判定顺序是**关系优先、状态其次**：先说清"你是谁、你能不能碰这个对象"，再说"这个对象当前
    允许什么"。工作空间 id 全局可寻址、且 P2 存在合法的访客路径，所以非归属返回 403 而不是 404
    （§9.1 的边界）。
    """
    decision = check_permission(workspace=workspace, actor=actor, action=action)
    if decision.allowed:
        assert decision.relation is not None  # 允许即意味着关系已解析出来
        return decision.relation
    if decision.relation is None or action not in RELATION_ACTIONS[decision.relation]:
        raise PermissionDeniedError(str(decision.reason))
    raise _STATUS_ERRORS[workspace.status](str(decision.reason))


def available_actions(*, workspace: Workspace, actor: Actor) -> frozenset[WorkspaceAction]:
    """当前 actor 在这个工作空间上可做的动作；前端直接用它渲染按钮（§3.6）。"""
    relation = resolve_relation(workspace=workspace, actor=actor)
    if relation is None:
        return frozenset()
    return RELATION_ACTIONS[relation] & STATUS_ACTIONS[workspace.status]
