"""认证接口：谁在操作（§9 / 执行计划 W4.3）。

**用户系统不归属 workspace**：本期既不签发也不校验凭据，只保留接口。domain 与 application
只认这里的 `Actor` 与 `actorId` 字符串，不认任何用户模型——真实实现（令牌校验）落在服务级
`adapters/outbound/identity/`，随用户系统落地。

401 的语义在入站层终结：凭据缺失 / 无效 / 过期时由 `ActorResolver` 的实现抛这里的错误，
请求不进入 application / domain。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Protocol

from research_core.workspace.domain.enums import ActorType
from research_core.workspace.domain.errors import ValidationError

ACTOR_ID_MAX_LENGTH = 128


@dataclass(frozen=True, slots=True)
class Actor:
    """已认证的操作者：只有标识与类型，没有用户资料。

    `type` 决定事件 envelope 的 `actor.type`；HTTP 命令一律是 `USER`，内部用例
    （如引用标 stale）用 `SYSTEM`（§7.2）。
    """

    id: str
    type: ActorType = ActorType.USER

    def __post_init__(self) -> None:
        if not self.id or not self.id.strip():
            raise ValidationError("actorId must not be blank")
        if len(self.id) > ACTOR_ID_MAX_LENGTH:
            raise ValidationError(f"actorId must be at most {ACTOR_ID_MAX_LENGTH} characters")


class ActorResolutionError(ValueError):
    """凭据无法解析为 `Actor`。子类各带一个 §9 的错误码，由入站层翻成 401。"""

    code: ClassVar[str] = "UNAUTHENTICATED"


class UnauthenticatedError(ActorResolutionError):
    """凭据缺失、格式错误或不可验证。"""

    code: ClassVar[str] = "UNAUTHENTICATED"


class TokenExpiredError(ActorResolutionError):
    """凭据可验证但已过期。"""

    code: ClassVar[str] = "TOKEN_EXPIRED"


class ActorResolver(Protocol):
    """把入站凭据解析成 `Actor`（端口）。

    实现放在服务级 `adapters/outbound/identity/`：用户系统落地后换实现，domain、application
    与本签名都不需要改。
    """

    async def resolve(self, authorization: str | None) -> Actor:
        """解析 `Authorization` 凭据；失败抛 `UnauthenticatedError` / `TokenExpiredError`。"""
