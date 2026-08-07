# src/buildpolaris_ai/platform/retrieval/citation_validator.py
from pydantic import BaseModel, Field
import structlog

logger = structlog.get_logger()

class Citation(BaseModel):
    source_docname: str
    quoted_span: str

class RAGResponse(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)

class CitationValidator:
    """
    Deterministic post-hoc check (NFR-AI-18).
    Verifies that every quoted span actually exists in the source document.
    """
    def validate(self, response: RAGResponse, source_documents: dict[str, str]) -> bool:
        # 1. If the model explicitly says it doesn't know, empty citations are valid.
        if "don't have enough information" in response.answer.lower():
            return True
            
        # 2. CRITICAL: If the model provides a factual answer, it MUST have at least one citation.
        if not response.citations:
            logger.warning(
                "Citation validation FAILED: Model provided a factual answer but no citations.",
                answer=response.answer
            )
            return False
            
        # 3. Verify every citation's quoted span exists in the source text.
        for citation in response.citations:
            source_text = source_documents.get(citation.source_docname, "")
            if not source_text:
                logger.warning("Citation validation failed: Source document not found", docname=citation.source_docname)
                return False
            
            # Exact match required to guarantee zero hallucination
            if citation.quoted_span not in source_text:
                logger.warning(
                    "Citation validation failed: Quoted span not found in source", 
                    docname=citation.source_docname, 
                    span=citation.quoted_span
                )
                return False
                
        logger.info("Citation validation passed", num_citations=len(response.citations))
        return True