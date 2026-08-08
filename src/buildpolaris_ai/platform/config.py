"""Centralized application configuration for buildpolaris_ai.

This module is the single source of truth for all environment-driven
settings. Every component reads config from `get_settings()` instead of
calling `os.getenv` directly, so secrets and environment behavior are
auditable in one place (Implementation Plan §1.2 issue #7).

Environment variables use a `__` delimiter for nested groups, e.g.:
    DATABASE__USER, DATABASE__PASSWORD, REDIS__URL, MODEL_PROVIDER__PROVIDER_ID

A `.env` file at the repo root is loaded automatically if present
(see `.env.example`). `.env` itself is gitignored — never commit secrets.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseModel):
    """Postgres + pgvector + Apache AGE connection settings."""

    user: str = "polaris_ai"
    password: SecretStr = SecretStr("polaris_ai_dev_password")
    host: str = "localhost"
    port: int = 5432
    name: str = "polaris_knowledge"

    def connect_kwargs(self) -> dict:
        """Return kwargs suitable for `asyncpg.connect(**kwargs)`.

        Callers never touch `.get_secret_value()` themselves — the secret
        is unwrapped exactly here and nowhere else.
        """
        return {
            "user": self.user,
            "password": self.password.get_secret_value(),
            "host": self.host,
            "port": self.port,
            "database": self.name,
        }


class RedisSettings(BaseModel):
    """Event-bus (Redis Streams) connection settings."""

    url: str = "redis://localhost:6379"


class ModelProviderSettings(BaseModel):
    """Model provider selection.

    Consumed by the next branch (feat/model-provider-adapters). Declared
    here now so provider selection becomes a config change, not a code change.
    """

    # e.g. "ollama/qwen2.5:3b-instruct" or "google/gemini-2.5-flash"
    provider_id: str = "ollama/qwen2.5:3b-instruct"
    api_key: SecretStr | None = None


class Settings(BaseSettings):
    """Root settings object composing all subsystem groups."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    model_provider: ModelProviderSettings = Field(default_factory=ModelProviderSettings)


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings singleton."""
    return Settings()