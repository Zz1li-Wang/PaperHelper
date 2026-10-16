"""HTTP 请求 / 响应模型。

两处刻意的分工：

- **命名**：请求体里的 `expectedVersion`、响应里的 `contextVersion` / `availableActions` 都是
  camelCase——这是 **API 契约**的命名（设计 §6 / §7）。事件 payload 用 snake_case，两者是两套
  契约，不要互相"对齐"。
- **校验粒度**：这里只负责"字段在不在、类型对不对"。**内容级规则（长度、空白）一律交给领域层**
  （§3.9），否则同一件事会有两处判定、两套错误文案；缺字段这类结构性错误由 FastAPI 抛
  `RequestValidationError`，入站层统一翻成 400 `VALIDATION_ERROR`。
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from research_core.workspace.application.dto import (
    ActorView,
    WorkspacePage,
    WorkspacePatch,
    WorkspaceSnapshot,
    WorkspaceView,
)
from research_core.workspace.domain.enums import (
    ActorType,
    Relation,
    Visibility,
    WorkspaceAction,
    WorkspaceStatus,
    WorkspaceType,
)
from research_core.workspace.domain.errors import ValidationError
from research_core.workspace.domain.workspace import UNSET

_CAMEL_CONFIG = ConfigDict(alias_generator=to_camel, populate_by_name=True)


# --- 请求 ---------------------------------------------------------------------


class CreateWorkspaceRequest(BaseModel):
    model_config = _CAMEL_CONFIG

    title: str
    description: str | None = None
    visibility: Visibility = Visibility.PRIVATE


class UpdateWorkspaceRequest(BaseModel):
    """`patch` 只接受 `title` / `description` / `visibility`（§6.1）。

    用 `model_fields_set` 区分"没传这个字段"与"显式传了 null"：前者保持原值，后者对
    `description` 是"清空"，对 `title` / `visibility` 是非法（它们不可为空）。
    """

    model_config = _CAMEL_CONFIG

    title: str | None = None
    description: str | None = None
    visibility: Visibility | None = None
    expected_version: int

    def to_patch(self) -> WorkspacePatch:
        provided = self.model_fields_set
        if "title" in provided and self.title is None:
            raise ValidationError("title must not be null")
        if "visibility" in provided and self.visibility is None:
            raise ValidationError("visibility must not be null")
        return WorkspacePatch(
            title=self.title if "title" in provided else UNSET,
            description=self.description if "description" in provided else UNSET,
            visibility=self.visibility if "visibility" in provided else UNSET,
        )


class ArchiveWorkspaceRequest(BaseModel):
    model_config = _CAMEL_CONFIG

    expected_version: int
    reason: str | None = None


class RestoreWorkspaceRequest(BaseModel):
    model_config = _CAMEL_CONFIG

    expected_version: int


class TransferOwnershipRequest(BaseModel):
    model_config = _CAMEL_CONFIG

    expected_version: int
    new_owner_id: str


class DeleteWorkspaceRequest(BaseModel):
    """DeleteWorkspace 的 `expectedVersion` 也走请求体（§7.3：不用 `If-Match`，失败码 412）。"""

    model_config = _CAMEL_CONFIG

    expected_version: int


# --- 响应 ---------------------------------------------------------------------


class WorkspaceViewResponse(BaseModel):
    model_config = _CAMEL_CONFIG

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
    def from_dto(cls, view: WorkspaceView) -> WorkspaceViewResponse:
        return cls(**{field: getattr(view, field) for field in cls.model_fields})


class ActorViewResponse(BaseModel):
    model_config = _CAMEL_CONFIG

    actor_id: str
    type: ActorType
    relation: Relation
    permissions: tuple[WorkspaceAction, ...]

    @classmethod
    def from_dto(cls, view: ActorView, *, actor_type: ActorType) -> ActorViewResponse:
        return cls(
            actor_id=view.actor_id,
            type=actor_type,
            relation=view.relation,
            permissions=view.permissions,
        )


class WorkspaceSnapshotResponse(BaseModel):
    """工作空间类命令的返回体（§3.6）。

    `refs` / `sessions` / `producedResources` 三个列表**本轮不出现**：它们的聚合还没实现，设计
    里这三个字段本就是可选的（§3.6）。`compositionVersion` 同理，此刻恒等于 `version`。
    """

    model_config = _CAMEL_CONFIG

    workspace: WorkspaceViewResponse
    actor: ActorViewResponse
    available_actions: tuple[WorkspaceAction, ...]
    version: int
    context_version: int
    composition_version: int

    @classmethod
    def from_dto(
        cls, snapshot: WorkspaceSnapshot, *, actor_type: ActorType
    ) -> WorkspaceSnapshotResponse:
        return cls(
            workspace=WorkspaceViewResponse.from_dto(snapshot.workspace),
            actor=ActorViewResponse.from_dto(snapshot.actor, actor_type=actor_type),
            available_actions=snapshot.available_actions,
            version=snapshot.version,
            context_version=snapshot.context_version,
            composition_version=snapshot.composition_version,
        )


class WorkspacePageResponse(BaseModel):
    """列表接口的分页信封（§7.3：响应含 `total`）。

    `pageSize` 可能是被上限夹过的值，所以回带——客户端据此知道自己拿的是哪一页、每页多少。
    """

    model_config = _CAMEL_CONFIG

    items: tuple[WorkspaceViewResponse, ...]
    total: int
    page: int
    page_size: int

    @classmethod
    def from_dto(cls, page: WorkspacePage) -> WorkspacePageResponse:
        return cls(
            items=tuple(WorkspaceViewResponse.from_dto(item) for item in page.items),
            total=page.total,
            page=page.page,
            page_size=page.page_size,
        )


class WorkspaceDeletedResponse(BaseModel):
    """DeleteWorkspace 的 200 响应：设计只说"不带快照"（§7.4），这里给一个最小确认体。"""

    model_config = _CAMEL_CONFIG

    id: UUID
    status: WorkspaceStatus


class ErrorResponse(BaseModel):
    """§9.2：409 `VERSION_CONFLICT` 必须回带 `currentVersion`。"""

    model_config = _CAMEL_CONFIG

    code: str
    message: str
    current_version: int | None = None
