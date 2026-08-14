"""Formats retrieved chunks into a numbered context block for the
generation prompt, and provides the reverse mapping citation_validator.py
needs to resolve a [n] marker back to the real chunk it refers to.
"""
from __future__ import annotations

from app.platform.vector_store.adapter import ScoredChunk


def format_answer_with_citations(chunks: list[ScoredChunk]) -> str:
    lines = []
    for i, chunk in enumerate(chunks, start=1):
        lines.append(
            f"[{i}] ({chunk.source_doctype} {chunk.source_name}, "
            f"{chunk.span_type} {chunk.span_start}"
            f"{'-' + str(chunk.span_end) if chunk.span_end != chunk.span_start else ''}):\n"
            f"{chunk.chunk_text}\n"
        )
    return "\n".join(lines)
