"""Workspace 聚合根（设计基线 §3.2 / §5.2 / §3.8 / §3.9）。

这个类只做一件事：**在工作空间自身的字段与状态上守住不变量**。它不查仓储、不查其他聚合
（跨聚合事实由应用层先查、作为参数传进来，§4 分层职责），也不碰时间——时间一律由调用方传入，
这样单测不需要冻结时钟。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final
from uuid import UUID, uuid4

from research_core.workspace.domain.enums import Visibility, WorkspaceStatus, WorkspaceType
from research_core.workspace.domain.errors import (
    InvalidWorkspaceTypeError,
    ValidationError,
    WorkspaceArchivedError,
    WorkspaceDeletedError,
)
from research_core.workspace.domain.events import (
    WorkspaceArchived,
    WorkspaceCreated,
    WorkspaceDeleted,
    WorkspaceEvent,
    WorkspaceOwnershipTransferred,
    WorkspaceRestored,
    WorkspaceUpdated,
)

TITLE_MAX_LENGTH: Final = 500
DESCRIPTION_MAX_LENGTH: Final = 10_000
IDENTIFIER_MAX_LENGTH: Final = 128

INITIAL_VERSION: Final = 1
INITIAL_CONTEXT_VERSION: Final = 1


class _Unset:
    """`update` 的"未提供"哨兵。

    没有它就无法区分"这次不改 description"与"把 description 置空"——两者都是合法的不同意图，
    用 `None` 兼任会丢掉后者。
    """

    __slots__ = ()

    def __repr__(self) -> str:
        return "UNSET"


UNSET: Final = _Unset()
Unset = _Unset


@dataclass(slots=True)
class Workspace:
    """研究工作空间：权限与生命周期边界。

    **根上没有任何指向内容的指针**：只有身份与生命周期字段，加上一个引用变更序列号
    `context_version`。"这个项目当前在看什么"由会话承载（`Session.focusRefId`），不在根上，
    也不在引用行上。

    字段类型对照：设计文档写作 `id: string`，承载层展开为 `uuid.UUID`（与
    `contracts/events/v1/envelope.schema.json` 的 `format: uuid` 一致）；`type` 在 P1 恒为
    `WorkspaceType.WORKSPACE`，`replica` 分支随 P2 的副本表一起进来。
    """

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

    def __post_init__(self) -> None:
        if self.type is not WorkspaceType.WORKSPACE:
            # P1 只落 workspace 分支（§4.1）；副本行不属于本聚合，读到就是类型错误。
            raise InvalidWorkspaceTypeError(f"unsupported workspace type: {self.type}")
        if self.version < INITIAL_VERSION:
            raise ValidationError("version must be at least 1")
        if self.context_version < INITIAL_CONTEXT_VERSION:
            raise ValidationError("context_version must be at least 1")

    @classmethod
    def create(
        cls,
        *,
        title: str,
        owner_id: str,
        occurred_at: datetime,
        description: str | None = None,
        visibility: Visibility = Visibility.PRIVATE,
        workspace_id: UUID | None = None,
    ) -> tuple[Workspace, WorkspaceCreated]:
        """CreateWorkspace：从 `active`、`version = context_version = 1` 开始（§7.4）。"""
        timestamp = _require_aware(occurred_at, "occurredAt")
        workspace = cls(
            id=workspace_id if workspace_id is not None else uuid4(),
            type=WorkspaceType.WORKSPACE,
            title=_clean_title(title),
            description=_clean_description(description),
            version=INITIAL_VERSION,
            context_version=INITIAL_CONTEXT_VERSION,
            owner_id=_clean_identifier(owner_id, "ownerId"),
            visibility=_clean_visibility(visibility),
            status=WorkspaceStatus.ACTIVE,
            archived_at=None,
            created_at=timestamp,
            updated_at=timestamp,
        )
        event = WorkspaceCreated(
            title=workspace.title,
            description=workspace.description,
            visibility=workspace.visibility.value,
            owner_id=workspace.owner_id,
        )
        return workspace, event

    def update(
        self,
        *,
        occurred_at: datetime,
        title: str | Unset = UNSET,
        description: str | Unset | None = UNSET,
        visibility: Visibility | Unset = UNSET,
    ) -> tuple[WorkspaceEvent, ...]:
        """UpdateWorkspace：`patch` 只接受 `title` / `description` / `visibility`（§6.1）。

        没有任何字段真正变化时是**无操作**：不递增 `version`、不发事件（没有可丢失的更新）。
        """
        self._require_active()
        # 时间戳与取值先校验、再落字段：校验失败时聚合不能停在"改了一半、版本没动"的状态。
        timestamp = _require_aware(occurred_at, "occurredAt")
        cleaned_title = UNSET if isinstance(title, _Unset) else _clean_title(title)
        cleaned_description = (
            UNSET if isinstance(description, _Unset) else _clean_description(description)
        )
        cleaned_visibility = (
            UNSET if isinstance(visibility, _Unset) else _clean_visibility(visibility)
        )
        changes: dict[str, str | None] = {}
        if not isinstance(cleaned_title, _Unset) and cleaned_title != self.title:
            self.title = cleaned_title
            changes["title"] = cleaned_title
        if not isinstance(cleaned_description, _Unset) and cleaned_description != self.description:
            self.description = cleaned_description
            changes["description"] = cleaned_description
        if not isinstance(cleaned_visibility, _Unset) and cleaned_visibility is not self.visibility:
            self.visibility = cleaned_visibility
            changes["visibility"] = cleaned_visibility.value
        if not changes:
            return ()
        self._bump(timestamp)
        return (WorkspaceUpdated(changes=changes),)

    def archive(
        self, *, occurred_at: datetime, reason: str | None = None
    ) -> tuple[WorkspaceEvent, ...]:
        """ArchiveWorkspace：只读封存（§3.8）。

        对**已归档**的工作空间重复触发**不是**幂等无操作，而是按 §8 的状态约束拒绝——归档
        限制写动作，`archive` 不在"归档态允许的动作"里。这是有意的不对称：会话的"收起"才幂等。
        """
        self._require_not_deleted()
        if self.status is WorkspaceStatus.ARCHIVED:
            raise WorkspaceArchivedError("workspace is already archived")
        timestamp = _require_aware(occurred_at, "occurredAt")
        self.status = WorkspaceStatus.ARCHIVED
        self.archived_at = timestamp
        self._bump(timestamp)
        return (WorkspaceArchived(archived_at=timestamp, reason=reason),)

    def restore(self, *, occurred_at: datetime) -> tuple[WorkspaceEvent, ...]:
        """RestoreWorkspace：取消封存（§3.8）。

        对**已 active** 的工作空间是幂等无操作：返回空事件、不递增 `version`。
        `archived_at` **不清空**——它是"最近一次归档时间"，不表示当前状态（§3.2）。
        """
        self._require_not_deleted()
        if self.status is WorkspaceStatus.ACTIVE:
            return ()
        timestamp = _require_aware(occurred_at, "occurredAt")
        self.status = WorkspaceStatus.ACTIVE
        self._bump(timestamp)
        return (WorkspaceRestored(),)

    def delete(self, *, occurred_at: datetime) -> tuple[WorkspaceEvent, ...]:
        """DeleteWorkspace：终态，**单行写、不级联**（§3.2）。

        会话 / 引用 / 产出登记的状态一行都不动：`deleted` 已对子对象的一切动作拒绝，批量改写
        子状态只是没有可观测效果的簿记，却会让事务规模随会话数线性增长。
        """
        self._require_not_deleted()
        timestamp = _require_aware(occurred_at, "occurredAt")
        self.status = WorkspaceStatus.DELETED
        self._bump(timestamp)
        return (WorkspaceDeleted(),)

    def transfer_ownership(
        self, *, new_owner_id: str, occurred_at: datetime
    ) -> tuple[WorkspaceEvent, ...]:
        """TransferOwnership：`archived` 也允许（§8）；转给当前 owner 是无操作。"""
        self._require_not_deleted()
        cleaned_owner_id = _clean_identifier(new_owner_id, "newOwnerId")
        if cleaned_owner_id == self.owner_id:
            return ()
        previous_owner_id = self.owner_id
        timestamp = _require_aware(occurred_at, "occurredAt")
        self.owner_id = cleaned_owner_id
        self._bump(timestamp)
        return (
            WorkspaceOwnershipTransferred(
                from_owner_id=previous_owner_id,
                to_owner_id=cleaned_owner_id,
            ),
        )

    def apply_ref_change(self) -> None:
        """引用行的变更序列号 +1：§4「一次引用写的固定动作序列」的第 ② 步。

        本轮没有调用方（引用聚合尚未实现），先把递增入口钉死在一处，避免下一轮各用例各自
        `context_version += 1`：

        - 无条件自增，**禁止**作 CAS 依据；
        - 不动 `version`、不动 `updated_at`——"这个工作空间自己变没变"由 `version` / `updated_at`
          回答，引用变更不算（§5.2）。仓储侧因此必须把两类 UPDATE 的列集合分开写。
        """
        self._require_active()
        self.context_version += 1

    def _bump(self, occurred_at: datetime) -> None:
        """版本递增的唯一入口（§5.1）：每个命令最多 +1，同一命令内多字段变更不叠加。"""
        self.version += 1
        self.updated_at = occurred_at

    def _require_not_deleted(self) -> None:
        if self.status is WorkspaceStatus.DELETED:
            raise WorkspaceDeletedError("workspace is deleted")

    def _require_active(self) -> None:
        """写路径的状态约束兜底：归档是只读封存（§8）。

        应用层已经按同一张表判过一次；这里再判一次是有意的——领域不变量必须自洽，不能靠
        调用方守规矩。
        """
        self._require_not_deleted()
        if self.status is WorkspaceStatus.ARCHIVED:
            raise WorkspaceArchivedError("workspace is archived")


def _clean_title(value: str) -> str:
    trimmed = value.strip()
    if not 1 <= len(trimmed) <= TITLE_MAX_LENGTH:
        raise ValidationError(f"title must be 1-{TITLE_MAX_LENGTH} characters after trimming")
    return trimmed


def _clean_description(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    if not trimmed:
        # §3.9：`description` 允许为 null，不允许"空白字符串"——空白即视为未提供。
        return None
    if len(trimmed) > DESCRIPTION_MAX_LENGTH:
        raise ValidationError(f"description must be at most {DESCRIPTION_MAX_LENGTH} characters")
    return trimmed


def _clean_visibility(value: Visibility) -> Visibility:
    """把值收敛成枚举成员。

    `Visibility` 是 `StrEnum`，裸字符串 `"shared"` 与成员在运行期"看起来"兼容，却会在
    `visibility.value` 上炸出 `AttributeError`——那会被入站层当成 500，而不是 400。这里统一
    收敛，非法取值给 `ValidationError`。
    """
    try:
        return Visibility(value)
    except ValueError as error:
        allowed = ", ".join(member.value for member in Visibility)
        raise ValidationError(f"visibility must be one of: {allowed}") from error


def _clean_identifier(value: str, field: str) -> str:
    """标识符类字段（§3.9）：长度 1–128。

    与 `title` 不同，**不做 trim 后回写**：`ownerId` 是不透明标识，来自外部用户系统，改写它等于
    改写身份。空白串在这里被拒，而不是被规整。
    """
    if not value or not value.strip():
        raise ValidationError(f"{field} must not be blank")
    if len(value) > IDENTIFIER_MAX_LENGTH:
        raise ValidationError(f"{field} must be at most {IDENTIFIER_MAX_LENGTH} characters")
    return value


def _require_aware(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValidationError(f"{field} must be timezone-aware")
    return value
