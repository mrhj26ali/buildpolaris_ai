import pytest
from pydantic import SecretStr

from buildpolaris_ai.platform.config import Settings


def test_default_settings_load():
    s = Settings()
    assert s.database.user == "polaris_ai"
    assert s.database.host == "localhost"
    assert s.database.port == 5432
    assert s.database.name == "polaris_knowledge"
    assert s.redis.url == "redis://localhost:6379"
    assert s.model_provider.provider_id.startswith("ollama/")


def test_env_override(monkeypatch):
    monkeypatch.setenv("DATABASE__HOST", "db.internal")
    monkeypatch.setenv("DATABASE__PORT", "5433")
    monkeypatch.setenv("REDIS__URL", "redis://cache:6380")
    s = Settings()
    assert s.database.host == "db.internal"
    assert s.database.port == 5433
    assert s.redis.url == "redis://cache:6380"


def test_password_is_secret_and_not_leaked_in_repr():
    s = Settings()
    assert isinstance(s.database.password, SecretStr)
    # The plaintext password must never appear in the settings repr/logs.
    assert "polaris_ai_dev_password" not in repr(s)


def test_connect_kwargs_unwraps_secret():
    s = Settings()
    kwargs = s.database.connect_kwargs()
    assert kwargs["user"] == "polaris_ai"
    assert kwargs["password"] == "polaris_ai_dev_password"
    assert kwargs["database"] == "polaris_knowledge"
    assert kwargs["host"] == "localhost"
    assert kwargs["port"] == 5432


def test_model_provider_api_key_optional():
    s = Settings()
    assert s.model_provider.api_key is None