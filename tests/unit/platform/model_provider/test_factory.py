# tests/unit/platform/model_provider/test_factory.py
"""Unit tests for the model provider factory."""
import pytest
from unittest.mock import MagicMock, patch

from buildpolaris_ai.platform.model_provider.factory import get_model_provider
from buildpolaris_ai.platform.model_provider.instructor_adapter import InstructorProvider
from buildpolaris_ai.platform.model_provider.protocol import ModelProviderProtocol


class TestGetModelProvider:
    def test_returns_instructor_provider_instance(self):
        with patch("buildpolaris_ai.platform.model_provider.instructor_adapter.instructor.from_provider") as mock_fp:
            mock_fp.return_value = MagicMock()
            provider = get_model_provider()
            assert isinstance(provider, InstructorProvider)

    def test_returns_model_provider_protocol(self):
        with patch("buildpolaris_ai.platform.model_provider.instructor_adapter.instructor.from_provider") as mock_fp:
            mock_fp.return_value = MagicMock()
            provider = get_model_provider()
            assert isinstance(provider, ModelProviderProtocol)

    def test_reads_provider_id_from_config(self):
        """The factory must use settings.model_provider.provider_id."""
        with patch("buildpolaris_ai.platform.model_provider.instructor_adapter.instructor.from_provider") as mock_fp:
            mock_fp.return_value = MagicMock()
            provider = get_model_provider()
            # Default config is "ollama/qwen2.5:3b-instruct"
            assert provider.provider_id == "ollama/qwen2.5:3b-instruct"

    def test_config_change_changes_provider(self):
        """Switching provider_id in config must change the adapter's provider."""
        with patch("buildpolaris_ai.platform.model_provider.factory.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                model_provider=MagicMock(
                    provider_id="google/gemini-2.5-flash",
                    api_key=None,
                    base_url=None,
                )
            )
            with patch("buildpolaris_ai.platform.model_provider.instructor_adapter.instructor.from_provider") as mock_fp:
                mock_fp.return_value = MagicMock()
                provider = get_model_provider()
                assert provider.provider_id == "google/gemini-2.5-flash"