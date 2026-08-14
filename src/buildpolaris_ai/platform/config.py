"""Centralized application configuration for the AI sidecar service."""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseModel):
    enable_dev_routes: bool = False
    environment: Literal["development", "staging", "production"] = "development"


class DatabaseSettings(BaseModel):
    user: str = "polaris_ai"
    password: SecretStr = SecretStr("polaris_ai_dev_password")
    host: str = "localhost"
    port: int = 5432
    name: str = "polaris_knowledge"

    def connect_kwargs(self) -> dict:
        return {
            "user": self.user,
            "password": self.password.get_secret_value(),
            "host": self.host,
            "port": self.port,
            "database": self.name,
        }

    @property
    def dsn(self) -> str:
        return (
            f"postgresql://{self.user}:{self.password.get_secret_value()}"
            f"@{self.host}:{self.port}/{self.name}"
        )


class RedisSettings(BaseModel):
    url: str = "redis://localhost:6379"


class AuthSettings(BaseModel):
    mode: Literal["dev", "secret", "jwks"] = "dev"
    jwt_secret: SecretStr = SecretStr("buildpolaris-dev-secret-key-change-in-production")
    jwks_url: str | None = None
    expected_issuer: str | None = None
    expected_audience: str | None = None
    leeway_seconds: int = 30
    ingest_api_key: SecretStr = SecretStr("dev-ingest-key-change-in-production")


class ModelProviderSettings(BaseModel):
    """Multi-provider configuration with primary + fallback."""
    primary_provider: Literal["groq", "gemini", "ollama", "openai"] = "groq"
    groq_api_key: SecretStr | None = None
    groq_model: str = "llama-3.1-70b-versatile"
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-1.5-flash-latest"
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-4o-mini"
    ollama_model: str = "qwen2.5:3b-instruct"
    ollama_base_url: str = "http://localhost:11434"
    # Legacy compatibility
    provider_id: str = "ollama/qwen2.5:3b-instruct"
    api_key: SecretStr | None = None
    base_url: str | None = None


class EmbeddingSettings(BaseModel):
    provider: Literal["sentence-transformers", "ollama", "openai"] = "sentence-transformers"
    model: str = "all-MiniLM-L6-v2"
    dimensions: int = 384
    ollama_model: str = "nomic-embed-text"
    batch_size: int = 32


class RagSettings(BaseModel):
    vector_search_limit: int = 10
    graph_enrich_limit: int = 5
    rerank_top_k: int = 5
    jaccard_threshold: float = 0.85
    max_generation_retries: int = 2
    use_rag_fusion: bool = True
    use_query_transform: bool = True
    use_hyde: bool = True
    chunk_size: int = 512
    chunk_overlap: int = 64


class BFFSettings(BaseModel):
    mode: Literal["mock", "http"] = "mock"
    base_url: str | None = None
    api_token: SecretStr | None = None
    timeout_seconds: float = 10.0


class IngestSettings(BaseModel):
    transport: Literal["http", "redis"] = "http"
    stream_key: str = "bp.cdc.events"
    dlq_key: str = "bp.cdc.events.dlq"
    processed_set_key: str = "bp.cdc.processed"
    consumer_group: str = "bp_ai_ingest"
    batch_size: int = 10
    max_retries: int = 3


class GovernanceSettings(BaseModel):
    token_soft_ceiling_per_tenant: int = 2_000_000
    token_hard_ceiling_per_tenant: int = 3_000_000
    request_soft_ceiling_per_tenant: int = 20_000
    max_tokens_per_request: int = 4096


class ResilienceSettings(BaseModel):
    provider_timeout_seconds: float = 60.0
    breaker_failure_threshold: int = 5
    breaker_recovery_seconds: float = 30.0


class ObservabilitySettings(BaseModel):
    log_level: str = "INFO"
    log_format: Literal["console", "json"] = "console"
    enable_tracing: bool = False


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    app: AppSettings = Field(default_factory=AppSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    model_provider: ModelProviderSettings = Field(default_factory=ModelProviderSettings)
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    rag: RagSettings = Field(default_factory=RagSettings)
    bff: BFFSettings = Field(default_factory=BFFSettings)
    ingest: IngestSettings = Field(default_factory=IngestSettings)
    governance: GovernanceSettings = Field(default_factory=GovernanceSettings)
    resilience: ResilienceSettings = Field(default_factory=ResilienceSettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)


@lru_cache
def get_settings() -> Settings:
    return Settings()
