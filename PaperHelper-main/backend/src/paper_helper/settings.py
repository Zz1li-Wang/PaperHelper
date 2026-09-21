from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process configuration loaded from PAPER_HELPER_* environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="PAPER_HELPER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["local", "test", "staging", "production"] = "local"
    database_url: str | None = None
    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8001
    mcp_log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
