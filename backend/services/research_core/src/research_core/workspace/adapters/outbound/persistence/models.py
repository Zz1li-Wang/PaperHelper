"""Workspace 模块的 ORM 模型。

表结构来自设计 §5 的表草案。三条实现约束直接来自它：

1. **枚举值域用 `text` + 显式命名 CHECK**，不用 PG 原生 enum——P2 扩大值域是一次
   `ALTER … CHECK`，而不是一次类型迁移；
2. **CHECK 与索引都显式命名**：`migrations/env.py` 开着 `compare_check_constraints`，
   匿名约束会让 `alembic check` 产生伪 diff；CHECK 的最终名字由 `OrmBase` 的命名约定
   `ck_%(table_name)s_%(constraint_name)s` 拼成（`name="type"` → `ck_workspace_type`）；
3. **不设 server_default**：`created_at` 取事务开始时间、由领域层传入，与 outbox 的
   `occurred_at` 同一来源。

`context_version` 是**引用行的变更序列号**，不是本表自身字段的变化：仓储的自身字段 UPDATE
绝不写这一列（§5.2）。
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from research_core.adapters.outbound.persistence.database import OrmBase

WORKSPACE_TABLE_NAME = "workspace"

TITLE_MIN_LENGTH = 1
TITLE_MAX_LENGTH = 500
DESCRIPTION_MAX_LENGTH = 10_000
IDENTIFIER_MAX_LENGTH = 128


class WorkspaceModel(OrmBase):
    """`workspace` 表：工作空间聚合根，一张表一个聚合。"""

    __tablename__ = WORKSPACE_TABLE_NAME
    __table_args__ = (
        # P2 把值域扩为 ('workspace','replica')，届时是一次 ALTER。
        sa.CheckConstraint("type IN ('workspace')", name="type"),
        sa.CheckConstraint(
            f"char_length(btrim(title)) BETWEEN {TITLE_MIN_LENGTH} AND {TITLE_MAX_LENGTH}",
            name="title_length",
        ),
        sa.CheckConstraint(
            f"description IS NULL OR char_length(description) <= {DESCRIPTION_MAX_LENGTH}",
            name="description_length",
        ),
        sa.CheckConstraint(
            f"char_length(owner_id) BETWEEN 1 AND {IDENTIFIER_MAX_LENGTH}",
            name="owner_id_length",
        ),
        sa.CheckConstraint("visibility IN ('private', 'shared', 'public')", name="visibility"),
        sa.CheckConstraint("status IN ('active', 'archived', 'deleted')", name="status"),
        # ListWorkspaces：按 owner 过滤 + 状态 / 类型筛选。
        sa.Index("ix_workspace_owner_id_status_type", "owner_id", "status", "type"),
    )

    id: Mapped[UUID] = mapped_column(sa.Uuid, primary_key=True)
    type: Mapped[str] = mapped_column(sa.Text, nullable=False)
    title: Mapped[str] = mapped_column(sa.Text, nullable=False)
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    version: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    context_version: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    owner_id: Mapped[str] = mapped_column(sa.Text, nullable=False)
    visibility: Mapped[str] = mapped_column(sa.Text, nullable=False)
    status: Mapped[str] = mapped_column(sa.Text, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )
