"""Research Core 的启动配置。

只读环境变量、只做"能不能启动"的判断（URL 缺失、驱动不对就拒绝启动），不做业务校验。
本地取值见 `backend/.env.example`。
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy.engine import make_url

from research_core.adapters.outbound.identity.dev_stub import DEV_IDENTITY_ENV

DATABASE_URL_ENV = "PAPER_HELPER_RESEARCH_CORE_DATABASE_URL"
REQUIRED_DRIVER = "postgresql+asyncpg"


@dataclass(frozen=True, slots=True)
class Settings:
    """启动一个 Research Core 进程所需要的全部配置。"""

    database_url: str
    #: 只有显式设为 1 才装载开发期 `ActorResolver`；其余任何取值（含未设置）都是"不装载"。
    allow_dev_identity: bool

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> Settings:
        values = os.environ if environ is None else environ
        database_url = values.get(DATABASE_URL_ENV)
        if not database_url:
            raise RuntimeError(f"{DATABASE_URL_ENV} is required to start Research Core")
        if make_url(database_url).drivername != REQUIRED_DRIVER:
            raise RuntimeError(f"{DATABASE_URL_ENV} must use the {REQUIRED_DRIVER} driver")
        return cls(
            database_url=database_url,
            allow_dev_identity=values.get(DEV_IDENTITY_ENV) == "1",
        )
