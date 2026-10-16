"""Workspace 生命周期的领域事件。

**领域事件即对外契约**（§7）：`message_type` / `aggregate_type` 是 wire 上的取值，改字段等于改契约。
本模块的每个事件各有一份 JSON Schema（`contracts/events/v1/workspace/`），尚未落盘——见
`workspace_service.py` 顶部的说明。

payload 通则（§7.3）：**只放事件特有的业务字段**，不重复 envelope 已有的键——所以这里没有
`workspaceId`（它就是 `workspace_id`）、没有 `occurredAt`（envelope 的 `occurred_at`）、
没有 `version`（envelope 的 `aggregate_version`）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar


@dataclass(frozen=True, slots=True)
class WorkspaceEvent:
    """本上下文领域事件的基类：子类用 `ClassVar` 声明 `message_type`。"""

    message_type: ClassVar[str] = ""
    aggregate_type: ClassVar[str] = "workspace"


@dataclass(frozen=True, slots=True)
class WorkspaceCreated(WorkspaceEvent):
    """`workspace.created`：工作空间建立。"""

    message_type: ClassVar[str] = "workspace.created"

    title: str
    description: str | None
    visibility: str
    owner_id: str


@dataclass(frozen=True, slots=True)
class WorkspaceUpdated(WorkspaceEvent):
    """`workspace.updated`：只列出**本次实际变更**的字段（§7.3）。"""

    message_type: ClassVar[str] = "workspace.updated"

    changes: dict[str, str | None]


@dataclass(frozen=True, slots=True)
class WorkspaceArchived(WorkspaceEvent):
    """`workspace.archived`：只读封存。`archived_at` 是最近一次归档时间，恢复后不清空（§3.2）。"""

    message_type: ClassVar[str] = "workspace.archived"

    archived_at: datetime
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class WorkspaceRestored(WorkspaceEvent):
    """`workspace.restored`：恢复写权限；`occurred_at` 即恢复时刻。"""

    message_type: ClassVar[str] = "workspace.restored"


@dataclass(frozen=True, slots=True)
class WorkspaceDeleted(WorkspaceEvent):
    """`workspace.deleted`：终态，不级联改写子对象（§3.2）。"""

    message_type: ClassVar[str] = "workspace.deleted"


@dataclass(frozen=True, slots=True)
class WorkspaceOwnershipTransferred(WorkspaceEvent):
    """`workspace.ownership_transferred`：转移前后都记，消费方无需回查即可还原一步历史。"""

    message_type: ClassVar[str] = "workspace.ownership_transferred"

    from_owner_id: str
    to_owner_id: str
