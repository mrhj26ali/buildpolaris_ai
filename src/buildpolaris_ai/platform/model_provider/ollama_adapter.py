# src/buildpolaris_ai/platform/model_provider/ollama_adapter.py
import instructor
from openai import AsyncOpenAI
from pydantic import BaseModel
from typing import Type, TypeVar, Optional

T = TypeVar("T", bound=BaseModel)

class OllamaProvider:
    """
    Hexagonal Adapter for Ollama.
    Uses the `instructor` library patched onto an OpenAI-compatible client 
    to enforce strict, validated Pydantic outputs.
    """
    def __init__(self, model: str = "qwen2.5:3b-instruct", host: str = "http://localhost:11434"):
        self.model = model
        
        openai_client = AsyncOpenAI(
            base_url=f"{host}/v1",
            api_key="ollama", # Dummy key required by OpenAI client, ignored by Ollama
        )
        
        # CRITICAL FIX: Force JSON mode for local Ollama models. 
        # This prevents crashes when the model outputs plain text instead of tool calls.
        self.client = instructor.from_openai(
            openai_client, 
            mode=instructor.Mode.JSON
        )

    async def structured_generate(self, prompt: str, response_model: Type[T], model: Optional[str] = None) -> T:
        target_model = model or self.model
        
        response = await self.client.chat.completions.create(
            model=target_model,
            messages=[{"role": "user", "content": prompt}],
            response_model=response_model,
        )
        return response