"""Application settings, loaded from environment variables (and an optional ``.env`` file)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- General -----------------------------------------------------------------------
    app_name: str = "Retrieva"
    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    log_json: bool = True
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # --- Database ----------------------------------------------------------------------
    # The API and workers connect as a non-superuser role so Row-Level Security applies.
    database_url: str = "postgresql+psycopg://retrieva_app:retrieva_app@localhost:5432/retrieva"
    # Migrations run as the schema owner.
    migration_database_url: str | None = None
    db_pool_size: int = 10
    db_max_overflow: int = 10

    # --- Redis / Celery ----------------------------------------------------------------
    redis_url: str | None = "redis://localhost:6379/0"
    celery_broker_url: str | None = None
    celery_task_always_eager: bool = False

    # --- Security ----------------------------------------------------------------------
    jwt_secret: str = "change-me-in-development-only-0123456789abcdef"  # noqa: S105 (rejected in production)
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 14
    refresh_cookie_name: str = "retrieva_refresh"
    cookie_secure: bool = False
    rate_limit_per_minute: int = 120
    auth_rate_limit_per_minute: int = 10
    allow_open_registration: bool = True

    # --- Storage / uploads -------------------------------------------------------------
    storage_dir: Path = BACKEND_DIR / "storage"
    max_upload_mb: int = 50
    allowed_extensions: list[str] = Field(
        default_factory=lambda: [".pdf", ".docx", ".txt", ".md", ".markdown", ".csv", ".html", ".htm"]
    )

    # --- Embeddings --------------------------------------------------------------------
    embedding_provider: Literal["sentence-transformers", "hashing"] = "sentence-transformers"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384
    embedding_batch_size: int = 32
    # Instruction prefix for asymmetric retrieval models (BGE recommends one for queries).
    embedding_query_prefix: str = "Represent this sentence for searching relevant passages: "

    # --- Chunking defaults -------------------------------------------------------------
    chunking_strategy: Literal["recursive", "token", "semantic", "structure"] = "structure"
    chunk_size: int = 900
    chunk_overlap: int = 150
    chunk_max_tokens: int = 256

    # --- Retrieval ---------------------------------------------------------------------
    retrieval_top_k: int = 8
    retrieval_candidate_k: int = 40
    rrf_k: int = 60
    relevance_threshold: float = 0.0
    reranker_provider: Literal["cross-encoder", "lexical", "none"] = "cross-encoder"
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    # Minimum rerank score (cross-encoder logit) for evidence to count as relevant.
    rerank_abstain_threshold: float = -4.0

    # --- Generation --------------------------------------------------------------------
    llm_provider: Literal["extractive", "openai", "anthropic"] = "extractive"
    llm_model: str = ""
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    llm_temperature: float = 0.1
    llm_max_tokens: int = 900
    llm_timeout_seconds: float = 60.0
    context_token_budget: int = 2400

    # --- Observability -----------------------------------------------------------------
    otel_enabled: bool = False
    otel_exporter_endpoint: str | None = None
    otel_service_name: str = "retrieva-api"
    metrics_enabled: bool = True

    @field_validator("cors_origins", "allowed_extensions", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip().startswith("["):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def _check_production(self) -> Settings:
        if self.environment == "production":
            if self.jwt_secret.startswith("change-me") or len(self.jwt_secret) < 32:
                raise ValueError("JWT_SECRET must be set to a strong secret (>= 32 chars) in production")
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be true in production")
        return self

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def broker_url(self) -> str | None:
        return self.celery_broker_url or self.redis_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
