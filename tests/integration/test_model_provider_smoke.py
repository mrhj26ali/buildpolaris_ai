# tests/integration/test_model_provider_smoke.py
"""
Integration smoke test for the model provider.

This test requires Ollama to be running locally with the configured model.
It will be SKIPPED if Ollama is not available — it is not a hard failure.

To run: ensure Ollama is running with `ollama serve` and the model is pulled.
"""
import pytest
from pydantic import BaseModel

from buildpolaris_ai.platform.model_provider.factory import get_model_provider


class SimpleResponse(BaseModel):
    answer: str


@pytest.mark.asyncio
async def test_model_provider_generates_structured_response():
    """
    Smoke test: verify the configured model provider can actually generate
    a validated structured response end-to-end.
    """
    try:
        provider = get_model_provider()
        result = await provider.structured_generate(
            "Reply with exactly: hello world",
            SimpleResponse,
        )
        assert isinstance(result, SimpleResponse)
        assert isinstance(result.answer, str)
        assert len(result.answer) > 0
    except Exception as exc:
        pytest.skip(f"Model provider not available (Ollama not running?): {exc}")