"""领域 / 应用错误 → 错误码与 HTTP 状态码（§9.2）。

这张表是**唯一**的错误码来源，入站层只做翻译，不自己判断。它只依赖标准库与领域错误，所以
应用层仍然与框架无关；HTTP 状态码在这里只是数据，不是行为。

本轮只登记本切片可能产出的错误码；`RESOURCE_REF_*` / `SESSION_*` / `PRODUCED_RESOURCE_*`
随各自的切片加行。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from research_core.workspace.application.actors import (
    ActorResolutionError,
    TokenExpiredError,
    UnauthenticatedError,
)
from research_core.workspace.domain.errors import (
    InvalidWorkspaceTypeError,
    PermissionDeniedError,
    ValidationError,
    VersionConflictError,
    WorkspaceArchivedError,
    WorkspaceDeletedError,
    WorkspaceNotFoundError,
)


class ErrorCode(StrEnum):
    """§9.1 的错误码子集。"""

    VALIDATION_ERROR = "VALIDATION_ERROR"
    WORKSPACE_NOT_FOUND = "WORKSPACE_NOT_FOUND"
    WORKSPACE_ARCHIVED = "WORKSPACE_ARCHIVED"
    WORKSPACE_DELETED = "WORKSPACE_DELETED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    VERSION_CONFLICT = "VERSION_CONFLICT"
    INVALID_WORKSPACE_TYPE = "INVALID_WORKSPACE_TYPE"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class ErrorMapping:
    """一个错误码的承载形态。

    `carries_current_version`：409 `VERSION_CONFLICT` 的响应体**必须**回带 `currentVersion`
    （§9.2），值来自 `VersionConflictError.current_version`。
    """

    code: ErrorCode
    http_status: int
    carries_current_version: bool = False


ERROR_MAPPINGS: Mapping[type[Exception], ErrorMapping] = {
    ValidationError: ErrorMapping(ErrorCode.VALIDATION_ERROR, 400),
    WorkspaceNotFoundError: ErrorMapping(ErrorCode.WORKSPACE_NOT_FOUND, 404),
    WorkspaceArchivedError: ErrorMapping(ErrorCode.WORKSPACE_ARCHIVED, 409),
    WorkspaceDeletedError: ErrorMapping(ErrorCode.WORKSPACE_DELETED, 409),
    PermissionDeniedError: ErrorMapping(ErrorCode.PERMISSION_DENIED, 403),
    VersionConflictError: ErrorMapping(
        ErrorCode.VERSION_CONFLICT, 409, carries_current_version=True
    ),
    # P1 只有一种 type，这个错误不可达；保留在契约里（§9.1）。
    InvalidWorkspaceTypeError: ErrorMapping(ErrorCode.INVALID_WORKSPACE_TYPE, 403),
    UnauthenticatedError: ErrorMapping(ErrorCode.UNAUTHENTICATED, 401),
    TokenExpiredError: ErrorMapping(ErrorCode.TOKEN_EXPIRED, 401),
}


def map_error(error: Exception) -> ErrorMapping | None:
    """按**精确类型**查表；未登记的错误返回 `None`，由入站层兜底成 500 `SERVICE_UNAVAILABLE`。"""
    return ERROR_MAPPINGS.get(type(error))


def is_authentication_error(error: Exception) -> bool:
    """认证错误由入站层终结（401），不进入 application / domain（§7.3）。"""
    return isinstance(error, ActorResolutionError)
