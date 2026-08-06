# src/buildpolaris_ai/gateway/api/llm_test.py
from fastapi import APIRouter
from pydantic import BaseModel, Field
from buildpolaris_ai.platform.model_provider.ollama_adapter import OllamaProvider

router = APIRouter(prefix="/test", tags=["Testing"])

class TestRFIDraft(BaseModel):
    subject: str = Field(description="The subject of the RFI")
    question: str = Field(description="The specific question being asked")
    cost_impact: bool = Field(description="Whether this RFI has a cost impact")
    schedule_impact: bool = Field(description="Whether this RFI has a schedule impact")

@router.post("/llm-structured")
async def test_llm_structured():
    """
    Test endpoint to verify Ollama structured output via Instructor.
    """
    provider = OllamaProvider()
    prompt = "Draft an RFI about a discrepancy in the concrete mix design on site. It will cause a 2-day delay but no extra cost."
    result = await provider.structured_generate(prompt, TestRFIDraft)
    return result.model_dump()