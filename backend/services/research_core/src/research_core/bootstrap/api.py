"""Research Core 的 HTTP 装配：服务唯一的 composition root。

装配顺序就是依赖方向：settings → engine/session → UnitOfWork → application service → 路由；
反过来 application 与 domain 谁都不认识 FastAPI（架构测试会守住这条）。

**不建模块级 `app`**：那会让"导入即读环境变量"，测试与工具一 import 就炸。启动用

    uvicorn --factory research_core.bootstrap.api:create_app
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI

from research_core.adapters.outbound.identity.dev_stub import DevActorResolver
from research_core.bootstrap.database import build_engine, build_session_factory
from research_core.bootstrap.settings import Settings
from research_core.workspace.adapters.inbound.http.errors import install_error_handlers
from research_core.workspace.adapters.inbound.http.middleware import (
    install_request_context_middleware,
)
from research_core.workspace.adapters.inbound.http.router import router
from research_core.workspace.adapters.outbound.persistence.unit_of_work import (
    SqlAlchemyUnitOfWork,
)
from research_core.workspace.application.actors import ActorResolver
from research_core.workspace.application.workspace_service import WorkspaceService

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = Settings.from_environment() if settings is None else settings
    engine = build_engine(resolved.database_url)
    session_factory = build_session_factory(engine)

    app = FastAPI(
        title="Paper Helper Research Core",
        version="1.0.0",
        lifespan=_lifespan,
    )
    app.state.engine = engine
    app.state.workspace_service = WorkspaceService(
        unit_of_work=lambda: SqlAlchemyUnitOfWork(session_factory)
    )
    # 关闭时保持 None：认证依赖会让每个请求 401，而不是静默放行（§7.3）。
    app.state.actor_resolver = _build_actor_resolver(resolved)

    install_request_context_middleware(app)
    install_error_handlers(app)
    app.include_router(router)
    return app


def _build_actor_resolver(settings: Settings) -> ActorResolver | None:
    if settings.allow_dev_identity:
        return DevActorResolver()
    return None


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    try:
        yield
    finally:
        await app.state.engine.dispose()
