"""Application settings loaded from environment / .env file."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Autonomous SWE Agent"
    debug: bool = False

    # 默认 SQLite（无需 Docker 即可跑通）；生产可改为 PostgreSQL，如
    # postgresql+psycopg://swe:swe@localhost:5432/swe_agent
    database_url: str = "sqlite:///./swe_agent.db"
    redis_url: str = "redis://localhost:6379/0"

    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    default_model: str = "gpt-4o"

    workdir: str = "./workspace"  # 本地沙箱工作目录
    sandbox_provider: str = "local"  # local | e2b | docker
    e2b_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
