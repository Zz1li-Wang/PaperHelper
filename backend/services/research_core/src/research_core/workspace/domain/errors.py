"""Workspace 上下文的领域错误。

**这里不含 HTTP 语义**：错误码与状态码的对应关系在 `application/error_mapping.py`（§9），
入站层再把它翻成响应体。领域层只回答"哪条不变量被违反了"。
"""

from __future__ import annotations


class WorkspaceDomainError(ValueError):
    """Workspace 上下文的错误基类。"""


class ValidationError(WorkspaceDomainError):
    """字段级约束被违反（§3.9）：`title` / `title` 去空白后 1–500、`description` ≤ 10000 等。"""


class WorkspaceNotFoundError(WorkspaceDomainError):
    """工作空间不存在。"""


class WorkspaceArchivedError(WorkspaceDomainError):
    """工作空间处于 `archived`（只读封存），该动作被拒绝（§8）。

    注意这是**工作空间**的归档；会话的 `archived` 是"收起"，不限制任何动作（§3.8）。
    """


class WorkspaceDeletedError(WorkspaceDomainError):
    """工作空间处于 `deleted`（终态），该动作被拒绝（§8）。"""


class PermissionDeniedError(WorkspaceDomainError):
    """actor 与目标工作空间没有允许该动作的关系（§8 动作表）。

    归在领域错误里是为了让"抛错 → 错误码"只有一张表；判定本身由应用层的
    `application/permissions.py` 做（§4 分层职责）。
    """


class InvalidWorkspaceTypeError(WorkspaceDomainError):
    """动作与聚合根的 `type` 不匹配。P1 只有一种 type，不可达（§9.1）。"""


class VersionConflictError(WorkspaceDomainError):
    """乐观锁失败：`expectedVersion` 与当前 `version` 不一致（§5.3）。

    409 响应体必须回带 `currentVersion`，所以这个错误携带它——`currentVersion` 取自数据库的
    当前值，未必等于调用方"以为"的那个版本。
    """

    def __init__(self, current_version: int) -> None:
        super().__init__(f"expected version does not match current version {current_version}")
        self.current_version = current_version
