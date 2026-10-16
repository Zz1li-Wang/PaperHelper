"""应用层的输入 / 输出视图。

这些类型只在应用层与入站层之间使用；领域层不认识它们（聚合根只收发自己的字段与事件）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from research_core.workspace.domain.enums import (
    Relation,
    Visibility,
    WorkspaceAction,
    WorkspaceStatus,
    WorkspaceType,
)
from research_core.workspace.domain.events import WorkspaceEvent
from research_core.workspace.domain.workspace import UNSET, Unset, Workspace


@dataclass(frozen=True, slots=True)
class WorkspacePatch:
    """UpdateWorkspace 的 patch：只接受 `title` / `description` / `visibility`（§6.1）。

    未提供的字段保持原值，与"显式置空"是两种不同意图，所以用 `UNSET` 而不是 `None` 表示前者。
    """

    title: str | Unset = UNSET
    description: str | Unset | None = UNSET
    visibility: Visibility | Unset = UNSET


@dataclass(frozen=True, slots=True)
class WorkspaceView:
    """工作空间的读模型。"""

    id: UUID
    type: WorkspaceType
    title: str
    description: str | None
    version: int
    context_version: int
    owner_id: str
    visibility: Visibility
    status: WorkspaceStatus
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, workspace: Workspace) -> WorkspaceView:
        return cls(
            id=workspace.id,
            type=workspace.type,
            title=workspace.title,
            description=workspace.description,
            version=workspace.version,
            context_version=workspace.context_version,
            owner_id=workspace.owner_id,
            visibility=workspace.visibility,
            status=workspace.status,
            archived_at=workspace.archived_at,
            created_at=workspace.created_at,
            updated_at=workspace.updated_at,
        )


@dataclass(frozen=True, slots=True)
class ActorView:
    """当前操作者视图：前端用它渲染按钮，不自行推导权限（§3.6）。"""

    actor_id: str
    relation: Relation
    permissions: tuple[WorkspaceAction, ...]


@dataclass(frozen=True, slots=True)
class WorkspaceSnapshot:
    """`GetWorkspaceSnapshot` 与全部工作空间类命令的返回体（§3.6）。

    三个版本号各有用途，不能互相替代：

    - `version`：工作空间**自身字段**的乐观锁基准；
    - `context_version`：**引用集合**的变化（无删除盲区）；
    - `composition_version`：会话与产出登记的变化（**有删除盲区**）。

    `refs` / `sessions` / `produced_resources` 三个列表本轮为 `None`：它们各自的聚合尚未实现，
    随各自切片补上（§3.6 里这三个字段本就是可选的）。`composition_version` 同理——还没有会话与
    产出，它等于 `version`。
    """

    workspace: WorkspaceView
    actor: ActorView
    available_actions: tuple[WorkspaceAction, ...]
    version: int
    context_version: int
    composition_version: int
    refs: None = None
    sessions: None = None
    produced_resources: None = None


@dataclass(frozen=True, slots=True)
class WorkspacePage:
    """列表接口的分页信封。

    设计要求"响应含 `total`"（§7.3），裸数组装不下它——信封是被逼出来的，这里只定键名。
    `page` / `page_size` 回带是为了让客户端知道自己拿的是哪一页（`page_size` 可能被上限夹过）。
    """

    items: tuple[WorkspaceView, ...]
    total: int
    page: int
    page_size: int


@dataclass(frozen=True, slots=True)
class WorkspaceCommandResult:
    """一个写命令的结果。

    `events` 是本命令产生的领域事件，**已经与业务写同事务落进 `outbox_event`**（§4）。它仍随
    结果返回，是为了让应用层单测能直接断言"哪个命令发了哪条事件"，不必再写一个假 outbox；
    调用方不需要消费它。DeleteWorkspace 按 §7.4 只回 200，所以 `snapshot` 为 `None`。
    """

    snapshot: WorkspaceSnapshot | None
    events: tuple[WorkspaceEvent, ...]
