"""Chunker â€” page/clause-bounded splitting (ARCH Flowchart 5 step K:
"Chunk â€” page/clause-bounded"). Chunking never crosses a page boundary for
scanned/paginated sources or a clause boundary for contract text, because
FR-8.3's citation contract is "point to the exact page/clause a claim came
from" â€” a chunk that straddles two pages can't honestly cite either one.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.config import get_settings


@dataclass(slots=True)
class RawChunk:
    span_type: str  # 'page' | 'clause'
    span_start: int
    span_end: int
    text: str


# Matches common contract clause numbering: "1.", "1.1", "1.1.2", "Article 3",
# "Section 4.2" at the start of a line â€” used only to prefer clause
# boundaries as chunk breakpoints; token budget still hard-caps chunk size.
_CLAUSE_HEADING_RE = re.compile(
    r"^(?:(?:Article|Section)\s+\d+[.:]?|\d+(?:\.\d+){0,3}[.)]?)\s+\S",
    re.MULTILINE,
)


def _approx_token_count(text: str) -> int:
    # Cheap, provider-agnostic estimate (~4 chars/token for English prose)
    # good enough to bound chunk size without a tokenizer dependency per
    # provider (NFR-EXT.2 â€” chunker must not be coupled to one vendor's
    # tokenizer).
    return max(len(text) // 4, 1)


def chunk_pages(pages: list[str]) -> list[RawChunk]:
    """Page-bounded chunking for scanned/paginated sources (PDFs without
    reliable clause structure). One chunk per page unless the page exceeds
    the configured token budget, in which case it's split further but the
    span_start/span_end still both point at that same page number.
    """
    settings = get_settings().rag
    chunks: list[RawChunk] = []

    for page_num, page_text in enumerate(pages, start=1):
        page_text = page_text.strip()
        if not page_text:
            continue

        if _approx_token_count(page_text) <= settings.chunk_token_size:
            chunks.append(RawChunk("page", page_num, page_num, page_text))
            continue

        # Oversized page: split on paragraph boundaries within the page,
        # every sub-chunk still cites span=(page_num, page_num).
        for sub in _split_by_token_budget(page_text, settings.chunk_token_size,
                                           settings.chunk_token_overlap):
            chunks.append(RawChunk("page", page_num, page_num, sub))

    return chunks


def chunk_clauses(full_text: str, clause_numbers: list[tuple[int, int, str]] | None = None) -> list[RawChunk]:
    """Clause-bounded chunking for contract-style text with clause
    numbering. If `clause_numbers` (pre-extracted (start_offset, end_offset,
    label) triples) isn't supplied, falls back to the heading regex to find
    clause breakpoints.
    """
    settings = get_settings().rag

    if not clause_numbers:
        boundaries = [m.start() for m in _CLAUSE_HEADING_RE.finditer(full_text)]
        boundaries.append(len(full_text))
        clause_numbers = [
            (boundaries[i], boundaries[i + 1], str(i + 1))
            for i in range(len(boundaries) - 1)
            if boundaries[i + 1] > boundaries[i]
        ]

    chunks: list[RawChunk] = []
    for idx, (start, end, _label) in enumerate(clause_numbers, start=1):
        text = full_text[start:end].strip()
        if not text:
            continue
        if _approx_token_count(text) <= settings.chunk_token_size:
            chunks.append(RawChunk("clause", idx, idx, text))
        else:
            for sub in _split_by_token_budget(text, settings.chunk_token_size,
                                               settings.chunk_token_overlap):
                chunks.append(RawChunk("clause", idx, idx, sub))
    return chunks


def _split_by_token_budget(text: str, budget_tokens: int, overlap_tokens: int) -> list[str]:
    budget_chars = budget_tokens * 4
    overlap_chars = overlap_tokens * 4
    if len(text) <= budget_chars:
        return [text]

    parts = []
    start = 0
    while start < len(text):
        end = min(start + budget_chars, len(text))
        parts.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap_chars
    return parts
