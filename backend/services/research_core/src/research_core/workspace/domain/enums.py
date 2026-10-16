"""Workspace 上下文的枚举值。

值域与 `docs/workspace_design/workspace_design_new.md` §3.1 逐项对齐。库层用 `text` + 显式命名
CHECK 落同一组值域（见 `workspace/adapters/outbound/persistence/models.py`）；P2 扩大值域是一次
`ALTER … CHECK`，不是一次类型迁移。
"""

from __future__ import annotations

from enum import StrEnum


class WorkspaceType(StrEnum):
    """聚合根的判别字段。

    P1 只落库 `WORKSPACE` 分支（`replica` 随 P2 的副本表一起启用）；值域先保留两值，
    避免 P2 变成破坏性变更。
    """

    WORKSPACE = "workspace"
    REPLICA = "replica"


class WorkspaceStatus(StrEnum):
    """工作空间状态：`ARCHIVED` 是**只读封存**（拒绝写动作），`DELETED` 是终态。"""

    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


class Visibility(StrEnum):
    """P1 只落列、无消费方；P2 接 Share 时生效。"""

    PRIVATE = "private"
    SHARED = "shared"
    PUBLIC = "public"


class Relation(StrEnum):
    """actor 对某个工作空间的关系。P1 只产出 `OWNER`，值域保留三值（§8）。"""

    OWNER = "owner"
    REPLICA_VISITOR = "replica_visitor"
    PUBLIC_VISITOR = "public_visitor"


class WorkspaceAction(StrEnum):
    """权限动作表的第一维（§8）。

    这里列的是 P1 契约里的全部动作，而不是本轮已实现的命令——状态约束表
    （`application/permissions.py`）是**整个模块**的规则，"归档拒一切写"这类判断必须能一次看全，
    否则读者无法对着 §8 核对完整性。会话 / 引用 / 产出的动作随各自切片落地。
    """

    WORKSPACE_CREATE = "workspace:create"
    WORKSPACE_READ = "workspace:read"
    WORKSPACE_LIST = "workspace:list"
    WORKSPACE_UPDATE = "workspace:update"
    WORKSPACE_ARCHIVE = "workspace:archive"
    WORKSPACE_RESTORE = "workspace:restore"
    WORKSPACE_DELETE = "workspace:delete"
    WORKSPACE_TRANSFER_OWNERSHIP = "workspace:transfer_ownership"

    WORKSPACE_ADD_REF = "workspace:add_ref"
    WORKSPACE_REMOVE_REF = "workspace:remove_ref"
    WORKSPACE_UPDATE_REF_REVISION = "workspace:update_ref_revision"

    WORKSPACE_PRODUCE = "workspace:produce"
    WORKSPACE_LIST_PRODUCED = "workspace:list_produced"
    WORKSPACE_UPDATE_PRODUCED = "workspace:update_produced"

    SESSION_CREATE = "session:create"
    SESSION_READ = "session:read"
    SESSION_LIST = "session:list"
    SESSION_UPDATE = "session:update"
    SESSION_ARCHIVE = "session:archive"
    SESSION_RESTORE = "session:restore"
    SESSION_DELETE = "session:delete"

    FOCUS_SET_SESSION = "focus:set_session"
    FOCUS_CLEAR_SESSION = "focus:clear_session"


class ActorType(StrEnum):
    """事件 envelope 的 `actor.type`，也是 outbox 落库时的取值（§7.2）。"""

    USER = "user"
    SERVICE = "service"
    SYSTEM = "system"
