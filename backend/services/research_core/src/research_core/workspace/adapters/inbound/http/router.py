"""工作空间生命周期路由（§7.2）。

路由只做三件事：把请求体翻译成应用层的命令、调用例、把结果翻成响应模型。**不含任何判定**——
权限、状态约束、版本比较全部在应用层，错误由 `errors.py` 按同一张表翻成响应。

本轮只挂已实现用例的 7 条。`GET /workspaces`（列表）与 `GET /workspaces/{id}/snapshot` 等
应用层用例落地后再加，契约同步增长。
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, status

from research_core.workspace.adapters.inbound.http.dependencies import (
    ActorDep,
    ContextDep,
    ServiceDep,
)
from research_core.workspace.adapters.inbound.http.schemas import (
    ArchiveWorkspaceRequest,
    CreateWorkspaceRequest,
    DeleteWorkspaceRequest,
    RestoreWorkspaceRequest,
    TransferOwnershipRequest,
    UpdateWorkspaceRequest,
    WorkspaceDeletedResponse,
    WorkspacePageResponse,
    WorkspaceSnapshotResponse,
)
from research_core.workspace.application.actors import Actor
from research_core.workspace.application.dto import WorkspaceCommandResult
from research_core.workspace.application.workspace_service import DEFAULT_PAGE_SIZE
from research_core.workspace.domain.enums import WorkspaceStatus

router = APIRouter(prefix="/api/v1", tags=["workspaces"])


@router.post(
    "/workspaces",
    status_code=status.HTTP_201_CREATED,
    response_model=WorkspaceSnapshotResponse,
    summary="CreateWorkspace",
)
async def create_workspace(
    payload: CreateWorkspaceRequest,
    actor: ActorDep,
    context: ContextDep,
    service: ServiceDep,
) -> WorkspaceSnapshotResponse:
    result = await service.create_workspace(
        actor=actor,
        title=payload.title,
        description=payload.description,
        visibility=payload.visibility,
        request_id=context.request_id,
    )
    return _snapshot(result, actor)


@router.get(
    "/workspaces",
    response_model=WorkspacePageResponse,
    summary="ListWorkspaces",
)
async def list_workspaces(
    actor: ActorDep,
    service: ServiceDep,
    status_filter: Annotated[WorkspaceStatus | None, Query(alias="status")] = None,
    include_deleted: Annotated[bool, Query(alias="includeDeleted")] = False,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1)] = DEFAULT_PAGE_SIZE,
) -> WorkspacePageResponse:
    """默认**只返回 active**；`status=` 查历史，`includeDeleted=true` 放开为全部状态（§7.3）。"""
    workspace_page = await service.list_workspaces(
        actor=actor,
        status=status_filter,
        include_deleted=include_deleted,
        page=page,
        page_size=page_size,
    )
    return WorkspacePageResponse.from_dto(workspace_page)


@router.get(
    "/workspaces/{workspace_id}",
    response_model=WorkspaceSnapshotResponse,
    summary="GetWorkspace",
)
async def get_workspace(
    workspace_id: UUID, actor: ActorDep, service: ServiceDep
) -> WorkspaceSnapshotResponse:
    snapshot = await service.get_workspace(actor=actor, workspace_id=workspace_id)
    return WorkspaceSnapshotResponse.from_dto(snapshot, actor_type=actor.type)


@router.get(
    "/workspaces/{workspace_id}/snapshot",
    response_model=WorkspaceSnapshotResponse,
    summary="GetWorkspaceSnapshot",
)
async def get_workspace_snapshot(
    workspace_id: UUID, actor: ActorDep, service: ServiceDep
) -> WorkspaceSnapshotResponse:
    """与 `GetWorkspace` 同体：`refs` / `sessions` / `producedResources` 随各自聚合落地。"""
    snapshot = await service.get_workspace_snapshot(actor=actor, workspace_id=workspace_id)
    return WorkspaceSnapshotResponse.from_dto(snapshot, actor_type=actor.type)


@router.patch(
    "/workspaces/{workspace_id}",
    response_model=WorkspaceSnapshotResponse,
    summary="UpdateWorkspace",
)
async def update_workspace(
    workspace_id: UUID,
    payload: UpdateWorkspaceRequest,
    actor: ActorDep,
    context: ContextDep,
    service: ServiceDep,
) -> WorkspaceSnapshotResponse:
    result = await service.update_workspace(
        actor=actor,
        workspace_id=workspace_id,
        patch=payload.to_patch(),
        expected_version=payload.expected_version,
        request_id=context.request_id,
    )
    return _snapshot(result, actor)


@router.post(
    "/workspaces/{workspace_id}/archive",
    response_model=WorkspaceSnapshotResponse,
    summary="ArchiveWorkspace",
)
async def archive_workspace(
    workspace_id: UUID,
    payload: ArchiveWorkspaceRequest,
    actor: ActorDep,
    context: ContextDep,
    service: ServiceDep,
) -> WorkspaceSnapshotResponse:
    result = await service.archive_workspace(
        actor=actor,
        workspace_id=workspace_id,
        expected_version=payload.expected_version,
        reason=payload.reason,
        request_id=context.request_id,
    )
    return _snapshot(result, actor)


@router.post(
    "/workspaces/{workspace_id}/restore",
    response_model=WorkspaceSnapshotResponse,
    summary="RestoreWorkspace",
)
async def restore_workspace(
    workspace_id: UUID,
    payload: RestoreWorkspaceRequest,
    actor: ActorDep,
    context: ContextDep,
    service: ServiceDep,
) -> WorkspaceSnapshotResponse:
    result = await service.restore_workspace(
        actor=actor,
        workspace_id=workspace_id,
        expected_version=payload.expected_version,
        request_id=context.request_id,
    )
    return _snapshot(result, actor)


@router.post(
    "/workspaces/{workspace_id}/transfer-ownership",
    response_model=WorkspaceSnapshotResponse,
    summary="TransferOwnership",
)
async def transfer_ownership(
    workspace_id: UUID,
    payload: TransferOwnershipRequest,
    actor: ActorDep,
    context: ContextDep,
    service: ServiceDep,
) -> WorkspaceSnapshotResponse:
    result = await service.transfer_ownership(
        actor=actor,
        workspace_id=workspace_id,
        new_owner_id=payload.new_owner_id,
        expected_version=payload.expected_version,
        request_id=context.request_id,
    )
    return _snapshot(result, actor)


@router.delete(
    "/workspaces/{workspace_id}",
    response_model=WorkspaceDeletedResponse,
    summary="DeleteWorkspace",
)
async def delete_workspace(
    workspace_id: UUID,
    payload: DeleteWorkspaceRequest,
    actor: ActorDep,
    context: ContextDep,
    service: ServiceDep,
) -> WorkspaceDeletedResponse:
    await service.delete_workspace(
        actor=actor,
        workspace_id=workspace_id,
        expected_version=payload.expected_version,
        request_id=context.request_id,
    )
    return WorkspaceDeletedResponse(id=workspace_id, status=WorkspaceStatus.DELETED)


def _snapshot(result: WorkspaceCommandResult, actor: Actor) -> WorkspaceSnapshotResponse:
    if result.snapshot is None:  # pragma: no cover - 只有 DeleteWorkspace 不带快照
        raise RuntimeError("this command returns no snapshot")
    return WorkspaceSnapshotResponse.from_dto(result.snapshot, actor_type=actor.type)
