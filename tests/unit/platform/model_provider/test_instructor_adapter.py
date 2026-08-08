# tests/unit/platform/model_provider/test_instructor_adapter.py
"""Unit tests for the config-driven InstructorProvider adapter."""
import instructor
import pytest
from pydantic import BaseModel, SecretStr
from unittest.mock import AsyncMock, MagicMock, patch

from buildpolaris_ai.platform.model_provider.instructor_adapter import InstructorProvider
from buildpolaris_ai.platform.model_provider.protocol import ModelProviderProtocol


class SampleResponse(BaseModel):
    answer: str


# --- Initialization & Protocol Conformance ---


class TestProtocolConformance:
    def test_satisfies_model_provider_protocol(self):
        """InstructorProvider must satisfy ModelProviderProtocol structurally."""
        with patch("buildpolaris_ai.platform.model_provider.instructor_adapter.instructor.from_provider") as mock_fp:
            mock_fp.return_value = MagicMock()
            provider = InstructorProvider(provider_id="ollama/qwen2.5:3b-instruct")
            assert isinstance(provider, ModelProviderProtocol)

    def test_has_structured_generate_method(self):
        """The protocol requires structured_generate(prompt, response_model, model)."""
        assert hasattr(InstructorProvider, "structured_generate")
        assert callable(getattr(InstructorProvider, "structured_generate"))


# --- Provider ID Parsing ---


class TestExtractModel:
    def test_ollama_provider_id(self):
        assert InstructorProvider._extract_model("ollama/qwen2.5:3b-instruct") == "qwen2.5:3b-instruct"

    def test_google_provider_id(self):
        assert InstructorProvider._extract_model("google/gemini-2.5-flash") == "gemini-2.5-flash"

    def test_anthropic_provider_id(self):
        assert InstructorProvider._extract_model("anthropic/claude-sonnet-4-20250514") == "claude-sonnet-4-20250514"

    def test_provider_id_with_slash_in_model(self):
        """Model names can contain slashes (e.g., some HuggingFace models)."""
        assert InstructorProvider._extract_model("ollama/models/my-custom:v1") == "models/my-custom:v1"

    def test_invalid_provider_id_no_slash(self):
        with pytest.raises(ValueError, match="Invalid provider_id"):
            InstructorProvider._extract_model("invalid-no-slash")

    def test_invalid_provider_id_empty_model(self):
        with pytest.raises(ValueError, match="Invalid provider_id"):
            InstructorProvider._extract_model("ollama/")

    def test_invalid_provider_id_empty_provider(self):
        with pytest.raises(ValueError, match="Invalid provider_id"):
            InstructorProvider._extract_model("/qwen2.5:3b-instruct")


# --- Mode Resolution ---


class TestModeResolution:
    def test_ollama_uses_json_mode(self):
        """CRITICAL: Ollama must use JSON mode to prevent crashes (preserves original fix)."""
        with patch("buildpolaris_ai.platform.model_provider.instructor_adapter.instructor.from_provider") as mock_fp:
            mock_fp.return_value = MagicMock()
            InstructorProvider(provider_id="ollama/qwen2.5:3b-instruct")
            _, kwargs = mock_fp.call_args
            assert kwargs["mode"] == instructor.Mode.JSON

    def test_google_uses_tools_mode(self):
        with patch("buildpolaris_ai.platform.model_provider.instructor_adapter.instructor.from_provider") as mock_fp:
            mock_fp.return_value = MagicMock()
            InstructorProvider(provider_id="google/gemini-2.5-flash")
            _, kwargs = mock_fp.call_args
            assert kwargs["mode"] == instructor.Mode.TOOLS

    def test_anthropic_uses_tools_mode(self):
        with patch("buildpolaris_ai.platform.model_provider.instructor_adapter.instructor.from_provider") as mock_fp:
            mock_fp.return_value = MagicMock()
            InstructorProvider(provider_id="anthropic/claude-sonnet-4-20250514")
            _, kwargs = mock_fp.call_args
            assert kwargs["mode"] == instructor.Mode.TOOLS


# --- API Key & Base URL Handling ---


class TestConfigPassthrough:
    def test_api_key_passed_when_provided(self):
        with patch("buildpolaris_ai.platform.model_provider.instructor_adapter.instructor.from_provider") as mock_fp:
            mock_fp.return_value = MagicMock()
            InstructorProvider(
                provider_id="google/gemini-2.5-flash",
                api_key=SecretStr("test-key-123"),
            )
            _, kwargs = mock_fp.call_args
            assert kwargs["api_key"] == "test-key-123"

    def test_api_key_not_passed_when_none(self):
        with patch("buildpolaris_ai.platform.model_provider.instructor_adapter.instructor.from_provider") as mock_fp:
            mock_fp.return_value = MagicMock()
            InstructorProvider(provider_id="ollama/qwen2.5:3b-instruct")
            _, kwargs = mock_fp.call_args
            assert "api_key" not in kwargs

    def test_base_url_passed_when_provided(self):
        with patch("buildpolaris_ai.platform.model_provider.instructor_adapter.instructor.from_provider") as mock_fp:
            mock_fp.return_value = MagicMock()
            InstructorProvider(
                provider_id="ollama/qwen2.5:3b-instruct",
                base_url="http://custom-host:11434",
            )
            _, kwargs = mock_fp.call_args
            assert kwargs["base_url"] == "http://custom-host:11434"

    def test_base_url_not_passed_when_none(self):
        with patch("buildpolaris_ai.platform.model_provider.instructor_adapter.instructor.from_provider") as mock_fp:
            mock_fp.return_value = MagicMock()
            InstructorProvider(provider_id="ollama/qwen2.5:3b-instruct")
            _, kwargs = mock_fp.call_args
            assert "base_url" not in kwargs


# --- Structured Generate ---


class TestStructuredGenerate:
    @pytest.mark.asyncio
    async def test_uses_default_model_from_provider_id(self):
        with patch("buildpolaris_ai.platform.model_provider.instructor_adapter.instructor.from_provider") as mock_fp:
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(
                return_value=SampleResponse(answer="hello")
            )
            mock_fp.return_value = mock_client

            provider = InstructorProvider(provider_id="ollama/qwen2.5:3b-instruct")
            result = await provider.structured_generate("Say hello", SampleResponse)

            assert result.answer == "hello"
            mock_client.chat.completions.create.assert_called_once_with(
                model="qwen2.5:3b-instruct",
                messages=[{"role": "user", "content": "Say hello"}],
                response_model=SampleResponse,
            )

    @pytest.mark.asyncio
    async def test_model_override_takes_precedence(self):
        with patch("buildpolaris_ai.platform.model_provider.instructor_adapter.instructor.from_provider") as mock_fp:
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(
                return_value=SampleResponse(answer="overridden")
            )
            mock_fp.return_value = mock_client

            provider = InstructorProvider(provider_id="ollama/qwen2.5:3b-instruct")
            result = await provider.structured_generate(
                "Say hello", SampleResponse, model="llama3:8b"
            )

            assert result.answer == "overridden"
            mock_client.chat.completions.create.assert_called_once_with(
                model="llama3:8b",
                messages=[{"role": "user", "content": "Say hello"}],
                response_model=SampleResponse,
            )

    @pytest.mark.asyncio
    async def test_returns_validated_pydantic_instance(self):
        with patch("buildpolaris_ai.platform.model_provider.instructor_adapter.instructor.from_provider") as mock_fp:
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(
                return_value=SampleResponse(answer="validated")
            )
            mock_fp.return_value = mock_client

            provider = InstructorProvider(provider_id="google/gemini-2.5-flash")
            result = await provider.structured_generate("test", SampleResponse)

            assert isinstance(result, SampleResponse)
            assert result.answer == "validated"