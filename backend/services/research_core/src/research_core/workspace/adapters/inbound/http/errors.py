"""领域 / 应用错误 → HTTP 响应（§9.2）。

状态码与错误码**只查** `application/error_mapping.py`：那是唯一一张表，入站层只做翻译，不自己
判断"哪种错误该回几"——否则同一件事就有了两处真相，改一处必然漂移。
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from research_core.workspace.application.actors import ActorResolutionError
from research_core.workspace.application.error_mapping import ErrorCode, ErrorMapping, map_error
from research_core.workspace.domain.errors import VersionConflictError, WorkspaceDomainError

MAX_REPORTED_VALIDATION_ERRORS = 3


def install_error_handlers(app: FastAPI) -> None:
    """把已知错误类型挂上处理器；未登记的错误交给 FastAPI 兜成 500。"""
    for error_type in (WorkspaceDomainError, ActorResolutionError):
        app.add_exception_handler(error_type, _handle_known_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)


def error_response(error: Exception) -> JSONResponse:
    mapping = map_error(error)
    if mapping is None:  # pragma: no cover - 只可能来自未登记的错误子类
        raise error
    return JSONResponse(status_code=mapping.http_status, content=_content(error, mapping))


def validation_error_response(error: RequestValidationError) -> JSONResponse:
    """缺字段、类型不对这类**结构性**错误。

    不沿用 FastAPI 默认的 422 + 自有格式：契约里这类一律是 400 `VALIDATION_ERROR`（§7.3），
    而 422 在本模块另有含义（`INVALID_RESOURCE_REF`，语义非法），两者不能混。
    """
    details = "; ".join(
        f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
        for item in error.errors()[:MAX_REPORTED_VALIDATION_ERRORS]
    )
    return JSONResponse(
        status_code=400,
        content={"code": ErrorCode.VALIDATION_ERROR.value, "message": details or "invalid request"},
    )


def _content(error: Exception, mapping: ErrorMapping) -> dict[str, object]:
    content: dict[str, object] = {"code": mapping.code.value, "message": str(error)}
    if mapping.carries_current_version and isinstance(error, VersionConflictError):
        # §9.2：409 VERSION_CONFLICT 的响应体必须回带 currentVersion，值取自数据库当前版本。
        content["currentVersion"] = error.current_version
    return content


async def _handle_known_error(_request: Request, error: Exception) -> JSONResponse:
    return error_response(error)


async def _handle_validation_error(
    _request: Request, error: RequestValidationError
) -> JSONResponse:
    return validation_error_response(error)
