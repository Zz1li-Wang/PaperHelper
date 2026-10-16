"""Research Core 的 outbox 表与写入。

这是**服务级**设施，不是 workspace 私有的：research / artifacts 模块写自己的业务行时同样要追加
事件。表结构见 `workspace_1.md` §5，与 `contracts/events/v1/envelope.schema.json` 除三处之外
一一对应——`seq`（内部有序键）、`published_at`（发布状态）、以及把 envelope 的嵌套 `actor`
摊平成 `actor_type` / `actor_id` 两列。

P1 **不发布**：本文件只负责"与业务写同事务落库"，`published_at` 恒为 `NULL`。发布器（按 `seq`
排序、发完回填）是 P3 的事，那时不需要改表结构。
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from research_core.adapters.outbound.persistence.database import OrmBase
from research_core.workspace.application.outbox import OutboxRecord

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

OUTBOX_TABLE_NAME = "outbox_event"
ACTOR_ID_MAX_LENGTH = 128


class OutboxEventModel(OrmBase):
    """`outbox_event` 表：待发布的领域事件，一行一条消息。

    `seq` 是 P1 唯一"现在不用、以后必须"的列：同一事务内多条事件的 `occurred_at` 完全相同，
    `message_id` 又是随机 UUID，二者都不构成可排序键；P3 的发布器要靠它按聚合有序发布。
    """

    __tablename__ = OUTBOX_TABLE_NAME
    __table_args__ = (
        sa.CheckConstraint("message_kind IN ('command', 'event')", name="message_kind"),
        sa.CheckConstraint(
            f"char_length(actor_id) BETWEEN 1 AND {ACTOR_ID_MAX_LENGTH}", name="actor_id_length"
        ),
        # P3 发布器拉取未发布的行：部分索引只覆盖 published_at IS NULL 的那部分。
        sa.Index(
            "ix_outbox_event_unpublished",
            "published_at",
            postgresql_where=sa.text("published_at IS NULL"),
        ),
        # 按聚合排序 / 去重，也支撑消费方"聚合 + 版本"的去重口径。
        sa.Index(
            "ix_outbox_event_aggregate",
            "aggregate_type",
            "aggregate_id",
            "aggregate_version",
        ),
        # 按工作空间审计（§7.4：P1 的历史只能直接查这张表）。
        sa.Index("ix_outbox_event_workspace", "workspace_id", "occurred_at"),
    )

    seq: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    message_id: Mapped[UUID] = mapped_column(sa.Uuid, nullable=False, unique=True)
    message_type: Mapped[str] = mapped_column(sa.Text, nullable=False)
    message_kind: Mapped[str] = mapped_column(sa.Text, nullable=False)
    schema_version: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    producer: Mapped[str] = mapped_column(sa.Text, nullable=False)
    correlation_id: Mapped[UUID] = mapped_column(sa.Uuid, nullable=False)
    causation_id: Mapped[UUID | None] = mapped_column(sa.Uuid, nullable=True)
    workspace_id: Mapped[UUID] = mapped_column(sa.Uuid, nullable=False)
    aggregate_type: Mapped[str] = mapped_column(sa.Text, nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(sa.Uuid, nullable=False)
    aggregate_version: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    actor_type: Mapped[str] = mapped_column(sa.Text, nullable=False)
    actor_id: Mapped[str] = mapped_column(sa.Text, nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )


def to_row(record: OutboxRecord) -> dict[str, object]:
    """`OutboxRecord` → 表列。列名与 envelope 的对应关系见模块顶部说明。"""
    return {
        "message_id": record.message_id,
        "message_type": record.message_type,
        "message_kind": record.message_kind,
        "schema_version": record.schema_version,
        "occurred_at": record.occurred_at,
        "producer": record.producer,
        "correlation_id": record.correlation_id,
        "causation_id": record.causation_id,
        "workspace_id": record.workspace_id,
        "aggregate_type": record.aggregate_type,
        "aggregate_id": record.aggregate_id,
        "aggregate_version": record.aggregate_version,
        "actor_type": record.actor_type,
        "actor_id": record.actor_id,
        "payload": record.payload,
    }


class SqlAlchemyOutboxRepository:
    """把待发布事件写进 outbox。

    用调用方给的会话，**不自己开事务**：它必须与业务写在同一个事务里提交，失败一起回滚。
    `seq` 交给数据库生成（`Identity`），应用层不碰。
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, records: Sequence[OutboxRecord]) -> None:
        if not records:
            return
        await self._session.execute(
            sa.insert(OutboxEventModel).values([to_row(record) for record in records])
        )
