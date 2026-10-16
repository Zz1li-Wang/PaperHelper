"""请求上下文中间件：`X-Request-Id` 与 W3C `traceparent`（§7.3）。

- `request_id` 取 `X-Request-Id`，**仅当它是合法 UUID 时采纳**，否则生成新值；响应一律回带该头。
- `trace_id` 取 `traceparent` 的 trace-id 段，缺失则回落为 `request_id`。
- `trace_id` **只进日志，不进事件**：envelope 是封闭 schema（`additionalProperties: false`），
  往 payload 里塞 trace 字段会让契约校验失败。

两个 id 放进 `request.state`，供下游依赖读取；每请求一行日志，满足 DoD「日志含 request_id 与
trace_id」。
"""

from __future__ import annotations

import logging
import string
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from fastapi import FastAPI, Request, Response

REQUEST_ID_HEADER = "X-Request-Id"
TRACEPARENT_HEADER = "traceparent"
TRACE_ID_LENGTH = 32

logger = logging.getLogger("research_core.http")


def install_request_context_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def _request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = parse_request_id(request.headers.get(REQUEST_ID_HEADER))
        trace_id = parse_trace_id(request.headers.get(TRACEPARENT_HEADER)) or str(request_id)
        request.state.request_id = request_id
        request.state.trace_id = trace_id
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "http_request_failed request_id=%s trace_id=%s method=%s path=%s",
                request_id,
                trace_id,
                request.method,
                request.url.path,
            )
            raise
        response.headers[REQUEST_ID_HEADER] = str(request_id)
        logger.info(
            "http_request request_id=%s trace_id=%s method=%s path=%s status=%s",
            request_id,
            trace_id,
            request.method,
            request.url.path,
            response.status_code,
        )
        return response


def parse_request_id(value: str | None) -> UUID:
    """只有合法 UUID 才采纳：客户端可以传垃圾值，我们不能让它污染关联 id。"""
    if value:
        try:
            return UUID(value)
        except ValueError:
            pass
    return uuid4()


def parse_trace_id(value: str | None) -> str | None:
    """从 `traceparent` 里取 trace-id 段（W3C Trace Context）。"""
    if not value:
        return None
    parts = value.split("-")
    if len(parts) != 4:
        return None
    trace_id = parts[1].lower()
    if len(trace_id) != TRACE_ID_LENGTH or trace_id == "0" * TRACE_ID_LENGTH:
        return None
    if any(character not in string.hexdigits for character in trace_id):
        return None
    return trace_id
