"""开发期 `ActorResolver`：**不得用于生产**。

`Authorization: Bearer <actorId>` 里的字符串**直接当主体标识**，不做任何签名、时效或归属校验。
它存在的唯一理由，是让本地与测试能在用户系统落地前把链路跑通；真实实现（令牌校验）落在同一个包
里，替换时 domain、application 与路由契约都不需要改。

装配由 `ALLOW_DEV_IDENTITY=1` 显式开启（见 `bootstrap/settings.py`）。默认关闭时
`actor_resolver` 为 `None`，全部路由 401——**默认拒绝**，而不是默认放行。
"""

from __future__ import annotations

from dataclasses import dataclass

from research_core.workspace.application.actors import Actor, UnauthenticatedError
from research_core.workspace.domain.errors import ValidationError

DEV_IDENTITY_ENV = "ALLOW_DEV_IDENTITY"
_BEARER_PREFIX = "bearer "


@dataclass(frozen=True, slots=True)
class DevActorResolver:
    """见模块说明：只在 `ALLOW_DEV_IDENTITY=1` 时被装配。"""

    async def resolve(self, authorization: str | None) -> Actor:
        if not authorization or not authorization.lower().startswith(_BEARER_PREFIX):
            raise UnauthenticatedError("credentials are missing or not a bearer token")
        actor_id = authorization[len(_BEARER_PREFIX) :].strip()
        if not actor_id:
            raise UnauthenticatedError("credentials are missing or not a bearer token")
        try:
            return Actor(id=actor_id)
        except ValidationError as error:
            # 凭据本身不合法 → 401，而不是 400：这个请求根本没通过认证。
            raise UnauthenticatedError(str(error)) from error
