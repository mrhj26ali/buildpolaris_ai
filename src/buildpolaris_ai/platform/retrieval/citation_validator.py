"""Deterministic citation validator (NFR-AI-2 / NFR-AI-18).

Phase 2 upgrade: tolerance-based span matching instead of exact substring.
Rules:
1. Explicit "I don't know" => empty citations are valid.
2. Factual answer MUST have >= 1 citation.
3. Each quoted_span must match its source via:
   - normalized substring match, OR
   - token-level Jaccard similarity >= threshold (default 0.9).
Deterministic and testable; no LLM-as-judge in the validation path.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from pydantic import BaseModel, Field
import structlog

logger = structlog.get_logger()

JACCARD_THRESHOLD = 0.9


class Citation(BaseModel):
    source_docname: str
    quoted_span: str


class RAGResponse(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)


@dataclass(frozen=True)
class ValidationResult:
    is_valid: bool
    reason: str


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"\w+", text))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    union = len(a | b)
    return len(a & b) / union if union else 0.0


def span_matches_source(
    quoted_span: str, source_text: str, threshold: float = JACCARD_THRESHOLD
) -> ValidationResult:
    norm_span = _normalize(quoted_span)
    norm_source = _normalize(source_text)
    if not norm_span:
        return ValidationResult(False, "empty_span")
    if not norm_source:
        return ValidationResult(False, "empty_source")
    if norm_span in norm_source:
        return ValidationResult(True, "substring_match")
    sim = _jaccard(_tokenize(norm_span), _tokenize(norm_source))
    if sim >= threshold:
        return ValidationResult(True, f"jaccard_match:{sim:.3f}")
    return ValidationResult(False, f"no_match:jaccard={sim:.3f}")


class CitationValidator:
    def __init__(self, jaccard_threshold: float = JACCARD_THRESHOLD) -> None:
        self.jaccard_threshold = jaccard_threshold

    def validate(self, response: RAGResponse, source_documents: dict[str, str]) -> bool:
        if "don't have enough information" in response.answer.lower():
            return True
        if not response.citations:
            logger.warning("Citation validation FAILED: factual answer with no citations.", answer=response.answer)
            return False
        for citation in response.citations:
            source_text = source_documents.get(citation.source_docname, "")
            if not source_text:
                logger.warning("Citation validation failed: source not found", docname=citation.source_docname)
                return False
            result = span_matches_source(citation.quoted_span, source_text, self.jaccard_threshold)
            if not result.is_valid:
                logger.warning(
                    "Citation validation failed",
                    docname=citation.source_docname,
                    span=citation.quoted_span,
                    reason=result.reason,
                    threshold=self.jaccard_threshold,
                )
                return False
        logger.info("Citation validation passed", num_citations=len(response.citations))
        return True