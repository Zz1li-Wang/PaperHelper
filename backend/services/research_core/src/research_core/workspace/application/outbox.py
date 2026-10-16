"""领域事件 → outbox 行。

这是**唯一**的映射点：领域事件长什么样、wire 上的 `message_type` 是什么、payload 里放哪些字段，
都在这里汇合。应用服务只负责把结果交给 `UnitOfWork.outbox`，与业务写同事务落库（§4 固定动作
序列的第 ③ 步）。

三条通则（§7）：

- **payload 只放事件特有的业务字段**，不重复 envelope 已有的键——所以没有 `workspace_id`
  （它就是 envelope 的 `workspace_id`）、没有 `occurred_at`、没有版本号。
- **`aggregate_version` 只取所属聚合根的 `version`**，`context_version` 永不出现（§7.2 硬规则）。
- payload 的值必须是 **JSON 可序列化**的，所以时间在这里就转成 ISO 8601 字符串。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID, uuid4

from research_core.workspace.application.actors import Actor
from research_core.workspace.domain.events import (
    WorkspaceArchived,
    WorkspaceCreated,
    WorkspaceDeleted,
    WorkspaceEvent,
    WorkspaceOwnershipTransferred,
    WorkspaceRestored,
    WorkspaceUpdated,
)

#: 发布方标识：哪个部署单元发出这条消息（AMQP 的 app_id 也用它）。与内部用例的主体标识
#: `actor_id = research_core` 拼写不同是有意的——一个是服务，一个是主体。
PRODUCER = "research-core"

SCHEMA_VERSION = 1
MESSAGE_KIND = "event"


@dataclass(frozen=True, slots=True)
class OutboxRecord:
    """一条待发布事件。字段与 `contracts/events/v1/envelope.schema.json` 对齐（除 `seq`）。"""

    message_id: UUID
    message_type: str
    message_kind: str
    schema_version: int
    occurred_at: datetime
    producer: str
    correlation_id: UUID
    causation_id: UUID | None
    workspace_id: UUID
    aggregate_type: str
    aggregate_id: UUID
    aggregate_version: int
    actor_type: str
    actor_id: str
    payload: dict[str, object]


class OutboxRepository(Protocol):
    """outbox 的写入端口（实现见 `adapters/outbound/persistence/outbox.py`）。

    只写不读：P1 没有发布器，读的是 P3 的事。
    """

    async def add(self, records: list[OutboxRecord]) -> None: ...


def build_outbox_records(
    events: tuple[WorkspaceEvent, ...],
    *,
    workspace_id: UUID,
    aggregate_version: int,
    actor: Actor,
    occurred_at: datetime,
    correlation_id: UUID,
) -> list[OutboxRecord]:
    """把一次命令产生的事件翻成 outbox 行。

    `aggregate_version` 是变更**之后**的 `Workspace.version`（调用方在领域方法返回后再传）。
    时间也用命令里那一个 `now`——聚合变更与事件不能取两次时间。

    目前每个命令最多产生一条事件；多于一条时这里直接报错，而不是让两条事件共享同一个
    `aggregate_version`：那会让按"聚合 + 版本"去重的消费方**静默丢事件**（§7.2）。真出现
    多事件的命令时，要改成每条事件携带自己的版本。
    """
    if len(events) > 1:
        raise ValueError(
            "one command produced several events; per-event aggregate versions are required "
            "before they can share a single outbox flush (§7.2)"
        )
    return [
        OutboxRecord(
            message_id=uuid4(),
            message_type=event.message_type,
            message_kind=MESSAGE_KIND,
            schema_version=SCHEMA_VERSION,
            occurred_at=occurred_at,
            producer=PRODUCER,
            correlation_id=correlation_id,
            causation_id=None,
            workspace_id=workspace_id,
            aggregate_type=event.aggregate_type,
            aggregate_id=workspace_id,
            aggregate_version=aggregate_version,
            actor_type=actor.type.value,
            actor_id=actor.id,
            payload=_payload(event),
        )
        for event in events
    ]


def _payload(event: WorkspaceEvent) -> dict[str, object]:
    """payload 的字段清单见设计 §7.3；命名用 snake_case（团队取舍，见 §12 登记项）。"""
    match event:
        case WorkspaceCreated():
            return {
                "title": event.title,
                "description": event.description,
                "visibility": event.visibility,
                "owner_id": event.owner_id,
            }
        case WorkspaceUpdated():
            return {"changes": dict(event.changes)}
        case WorkspaceArchived():
            return {"archived_at": event.archived_at.isoformat(), "reason": event.reason}
        case WorkspaceOwnershipTransferred():
            return {
                "from_owner_id": event.from_owner_id,
                "to_owner_id": event.to_owner_id,
            }
        case WorkspaceRestored() | WorkspaceDeleted():
            # 无 payload 字段：occurred_at 即时刻本身（§7.3）。
            return {}
        case _:  # pragma: no cover - 新增事件类型时这里会先炸，而不是静默丢字段
            raise ValueError(f"no payload mapping for {type(event).__title__}")
