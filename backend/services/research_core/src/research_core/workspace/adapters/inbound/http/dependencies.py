"""入站依赖：谁在操作、这次请求的两个 id、装配好的应用服务。

**认证在这里终结**：凭据缺失 / 无效时 `ActorResolver` 抛 `UnauthenticatedError`，请求根本不会进入
application / domain（§7.3 的 401 语义）。`ALLOW_DEV_IDENTITY` 关闭时 `actor_resolver` 为 `None`，
于是每个请求都 401——这就是"用户系统还没落地"时最诚实的行为，而不是假装放行。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request

from research_core.workspace.application.actors import Actor, ActorResolver, UnauthenticatedError
from research_core.workspace.application.workspace_service import WorkspaceService


@dataclass(frozen=True, slots=True)
class RequestContext:
    """一次请求的两个关联 id：`request_id` 进事件（`correlation_id`），`trace_id` 只进日志。"""

    request_id: UUID
    trace_id: str


async def require_actor(request: Request) -> Actor:
    resolver: ActorResolver | None = getattr(request.app.state, "actor_resolver", None)
    if resolver is None:
        raise UnauthenticatedError("no actor resolver is configured")
    return await resolver.resolve(request.headers.get("Authorization"))


def request_context(request: Request) -> RequestContext:
    return RequestContext(request_id=request.state.request_id, trace_id=request.state.trace_id)


def workspace_service(request: Request) -> WorkspaceService:
    service: WorkspaceService | None = getattr(request.app.state, "workspace_service", None)
    if service is None:  # pragma: no cover - 只有装配漏了才会发生
        raise RuntimeError("workspace service is not wired into the application")
    return service


ActorDep = Annotated[Actor, Depends(require_actor)]
ContextDep = Annotated[RequestContext, Depends(request_context)]
ServiceDep = Annotated[WorkspaceService, Depends(workspace_service)]
