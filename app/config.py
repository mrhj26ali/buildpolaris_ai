"""Centralized application configuration for the AI sidecar.

Every setting below maps to a specific requirement rather than existing
generically Ã¢â‚¬â€ see the inline references. Secrets are never checked into a
versioned file (ARCH v2.1 Ã‚Â§7): this only reads from environment/.env.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseModel):
    environment: Literal["development", "staging", "production"] = "development"
    enable_dev_routes: bool = False


class DatabaseSettings(BaseModel):
    """Postgres Ã¢â‚¬â€ pgvector + Apache AGE. Disposable/rebuildable (ERD Ã‚Â§1)."""

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


class RedisSettings(BaseModel):
    url: str = "redis://localhost:6379"


class ServiceAuthSettings(BaseModel):
    """ARCH v2.1 Ã‚Â§4.2 Direction 1 Ã¢â‚¬â€ service credential + Scope Assertion.

    This is NOT user authentication (Frappe's session cookie already
    handles that end-to-end). It is a narrow, short-lived, service-to-
    service scope assertion the BFF mints after its own has_permission
    check has already passed.
    """

    service_key: SecretStr = SecretStr("dev-bff-service-key-change-in-production")
    scope_assertion_secret: SecretStr = SecretStr(
        "dev-scope-assertion-secret-change-in-production"
    )
    scope_assertion_max_ttl_seconds: int = 60


class ModelProviderSettings(BaseModel):
    """NFR-MAINT.5 / NFR-AIGOV.2 Ã¢â‚¬â€ swappable, version-pinnable provider."""

    primary: Literal["gemini", "ollama", "anthropic", "openai"] = "gemini"
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-2.0-flash"
    gemini_embedding_model: str = "text-embedding-004"

    fallback: Literal["gemini", "ollama", "anthropic", "openai", "none"] = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b-instruct"

    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-sonnet-4-6"
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-4o-mini"

    # NFR-AIGOV.2: pin a specific model version globally (or per-tenant via
    # model_pin.py) so a silent upstream update can't change agent
    # behavior without a deliberate, tested rollout.
    model_version_pin: str = "gemini-2.0-flash"


class EmbeddingSettings(BaseModel):
    provider: Literal["sentence-transformers", "gemini", "ollama"] = "sentence-transformers"
    model: str = "all-MiniLM-L6-v2"
    dimensions: int = 384
    batch_size: int = 32


class RagSettings(BaseModel):
    vector_search_limit: int = 10
    graph_traversal_limit: int = 10
    rerank_top_k: int = 5
    reranker_enabled: bool = False  # ARCH Ã‚Â§3.3 point 6: optional, tenant-tunable
    max_citation_retries: int = 1  # UC-8.1 E1: exactly one stricter-prompt retry
    query_reformulations: int = 3  # 2-4 per ARCH Ã‚Â§3.3 point 2
    rrf_k: int = 60  # published RRF default
    chunk_token_size: int = 512
    chunk_token_overlap: int = 64


class BFFClientSettings(BaseModel):
    """ARCH v2.1 section 4.2 Direction 2 -- AI calls back into buildpolaris_bff
    (propose_agent_action, MCP tool reads), authenticating as the
    low-privilege 'BuildPolaris AI Service' transport account.

    buildpolaris_bff is a Frappe app: an inbound call is either an
    authenticated (non-Guest) Frappe session or it carries Frappe's own
    `Authorization: token api_key:api_secret` header -- there is no other
    way to avoid being treated as Guest, and BFF's mcp_server.py's
    `_assert_service_caller()` rejects Guests outright. `api_key`/
    `api_secret` below are exactly the pair buildpolaris_bff/install.py
    generates for that account and writes (once) to
    sites/<site>/private/files/buildpolaris_ai_service_credentials.txt --
    copy them here, then delete that file.

    The Scope Assertion is a SEPARATE, narrower concept from this
    transport credential (see gateway/auth/scope_assertion.py) and is
    sent per-call as an explicit `scope_assertion` field in the request
    body/query -- never as a header on this side, since it's simply
    forwarded as one of BFF's own whitelisted-method keyword arguments
    (propose_agent_action(..., scope_assertion, ...),
    mcp_server.call_tool(..., scope_assertion, ...)).
    """

    base_url: str = "http://localhost:8080"
    api_key: SecretStr = SecretStr("")
    api_secret: SecretStr = SecretStr("")
    # service_key is used the OTHER direction (BFF -> AI, verified by
    # gateway/auth/service_credential.py) -- kept here too since both
    # directions' shared secrets live naturally next to the client that
    # talks to that peer. Must equal buildpolaris_bff's site_config.json
    # `buildpolaris_ai_service_key`.
    service_key: SecretStr = SecretStr("dev-ai-service-key-change-in-production")
    timeout_seconds: float = 15.0

    @property
    def list_tools_path(self) -> str:
        return "/api/method/buildpolaris_bff.ai_copilot.mcp.mcp_server.list_tools"

    @property
    def call_tool_path(self) -> str:
        return "/api/method/buildpolaris_bff.ai_copilot.mcp.mcp_server.call_tool"

    @property
    def propose_agent_action_path(self) -> str:
        return "/api/method/buildpolaris_bff.ai_copilot.api.propose_agent_action"


class GovernanceSettings(BaseModel):
    """NFR-AIGOV.1 Ã¢â‚¬â€ spend observability with a soft ceiling before hard deny."""

    token_soft_ceiling_per_tenant: int = 2_000_000
    token_hard_ceiling_per_tenant: int = 3_000_000
    request_soft_ceiling_per_tenant: int = 20_000


class ResilienceSettings(BaseModel):
    """Backs the model_provider circuit breaker (ARCH Ã‚Â§3.3 point 2)."""

    provider_timeout_seconds: float = 30.0
    breaker_failure_threshold: int = 5
    breaker_recovery_seconds: float = 30.0


class ObservabilitySettings(BaseModel):
    log_level: str = "INFO"
    log_format: Literal["console", "json"] = "console"


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
    service_auth: ServiceAuthSettings = Field(default_factory=ServiceAuthSettings)
    model_provider: ModelProviderSettings = Field(default_factory=ModelProviderSettings)
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    rag: RagSettings = Field(default_factory=RagSettings)
    bff: BFFClientSettings = Field(default_factory=BFFClientSettings)
    governance: GovernanceSettings = Field(default_factory=GovernanceSettings)
    resilience: ResilienceSettings = Field(default_factory=ResilienceSettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)


@lru_cache
def get_settings() -> Settings:
    return Settings()
