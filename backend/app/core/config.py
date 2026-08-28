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
    task_backend: str = "thread"  # thread | celery
    worker_max_retries: int = 3
    max_human_revisions: int = 3

    openai_api_key: str | None = None
    # OpenAI 兼容接口地址（如 DeepSeek: https://api.deepseek.com/v1；留空用官方 OpenAI）
    openai_base_url: str | None = None
    anthropic_api_key: str | None = None
    default_model: str = "gpt-4o"

    github_token: str | None = None
    github_api_url: str = "https://api.github.com"
    git_author_name: str = "Autonomous SWE Agent"
    git_author_email: str = "agent@example.invalid"
    model_input_cost_per_million: float = 0.0
    model_output_cost_per_million: float = 0.0
    task_max_input_tokens: int = 8_000_000
    task_max_output_tokens: int = 250_000
    task_max_llm_calls: int = 128
    task_max_cost_usd: float = 2.0

    # Repository retrieval. `hashing` is the zero-download fallback; `fastembed`
    # runs a real local ONNX model; `openai` uses an OpenAI-compatible endpoint.
    embedding_provider: str = "hashing"  # hashing | fastembed | openai
    embedding_model: str = "BAAI/bge-small-en"
    embedding_dimensions: int = 384
    embedding_batch_size: int = 64
    embedding_cache_dir: str = "./.fastembed_cache"
    embedding_model_path: str | None = None
    rag_vector_store: str = "memory"  # memory | pgvector
    rag_vector_threshold: float = 0.1

    workdir: str = "./workspace"  # 本地沙箱工作目录
    artifact_dir: str = "./artifacts"
    repository_allowed_hosts: str = "github.com"
    allow_local_repositories: bool = True
    sandbox_provider: str = "local"  # local | docker | e2b
    e2b_api_key: str | None = None
    e2b_template: str = "base"  # E2B 沙箱模板
    docker_image: str = "python:3.12-slim"  # Docker 沙箱镜像


@lru_cache
def get_settings() -> Settings:
    return Settings()
