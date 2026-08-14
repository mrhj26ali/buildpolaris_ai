"""Submittal review assistant agent (read-only, FR-8.5)."""
from __future__ import annotations

from pydantic import BaseModel, Field

import structlog

from buildpolaris_ai.gateway.orchestrator.schemas import AgentInvocation, AgentResult
from buildpolaris_ai.platform.model_provider import get_model_provider

logger = structlog.get_logger()


class SubmittalReview(BaseModel):
    compliance_assessment: str = Field(description="Overall compliance assessment")
    issues_found: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    risk_level: str = Field(default="Low")


async def handle(invocation: AgentInvocation) -> AgentResult:
    """Review submittal content and provide assessment (read-only)."""
    try:
        provider = get_model_provider()
        prompt = f"""You are a construction submittal review specialist.
Review the following submittal content against typical specification requirements.
Provide compliance assessment, issues found, and recommendations.

Submittal Content:
{invocation.message[:2000]}

Provide a structured review."""

        review = await provider.structured_generate(prompt, SubmittalReview)

        return AgentResult(
            kind="answer",
            answer=(
                f"**Submittal Review Assessment:**\n\n"
                f"**Compliance:** {review.compliance_assessment}\n\n"
                f"**Issues Found:**\n" + "\n".join(f"- {i}" for i in review.issues_found) + "\n\n"
                f"**Recommendations:**\n" + "\n".join(f"- {r}" for r in review.recommendations)
            ),
            citations=[],
        )

    except Exception as e:
        logger.error("Submittal review failed", error=str(e))
        return AgentResult(kind="error", error=str(e))
