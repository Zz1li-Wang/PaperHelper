"""Explicit model registry for Research Core migrations."""

from __future__ import annotations

from importlib import import_module

#: ORM 模块清单。模块被 import 的那一刻，表就注册进 `OrmBase.metadata`——Alembic autogenerate
#: 只看得见注册过的表，所以**每新增一个模型模块都要在这里加一行**，否则迁移会以为那张表不存在，
#: 而 `alembic check` 又会把它当作多余的漂移。
ORM_MODULES: tuple[str, ...] = (
    "research_core.adapters.outbound.persistence.outbox",
    "research_core.workspace.adapters.outbound.persistence.models",
)


def import_orm_models() -> None:
    """Import Research Core ORM models as they are introduced."""
    for module in ORM_MODULES:
        import_module(module)
