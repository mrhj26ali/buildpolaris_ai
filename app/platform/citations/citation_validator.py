"""CitationValidator â€” Flowchart 4 step J: "claim matches real span?"

Two checks, both must pass for a citation marker to be considered valid:
1. The marker [n] must resolve to an actual chunk that was in the context
   (not an out-of-range or hallucinated index).
2. The sentence the marker is attached to must have meaningful lexical
   overlap with that chunk's text â€” catching the case where the model
   attaches a real-looking [n] to a claim the chunk doesn't actually
   support (citation-marker fabrication, not just index fabrication).

This is intentionally a lexical-overlap heuristic, not a full entailment
model â€” UC-8.1 E2 only requires catching claims that don't match a real
span "closely enough," and a heavyweight NLI model would add latency
(NFR-PERF.6) disproportionate to what a single retry-then-refuse already
buys.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.observability.logging import get_logger
from app.platform.vector_store.adapter import ScoredChunk

logger = get_logger(__name__)

_MARKER_RE = re.compile(r"\[(\d+)\]")
_WORD_RE = re.compile(r"[a-zA-Z0-9]+")


@dataclass(slots=True)
class ValidatedCitation:
    source_doctype: str
    source_name: str
    span_type: str
    span_start: int
    span_end: int
    quoted_span: str


def _sentence_containing(text: str, marker_pos: int) -> str:
    start = text.rfind(".", 0, marker_pos) + 1
    end = text.find(".", marker_pos)
    end = end + 1 if end != -1 else len(text)
    return text[start:end].strip()


def _jaccard(a: str, b: str) -> float:
    words_a = set(w.lower() for w in _WORD_RE.findall(a))
    words_b = set(w.lower() for w in _WORD_RE.findall(b))
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)


class CitationValidator:
    def __init__(self, min_overlap: float = 0.15) -> None:
        self._min_overlap = min_overlap

    def validate(
        self, answer_text: str, chunks: list[ScoredChunk]
    ) -> tuple[bool, list[ValidatedCitation]]:
        markers = list(_MARKER_RE.finditer(answer_text))
        if not markers:
            # An answer that makes claims with zero citations is exactly
            # what this gate exists to catch â€” treat as invalid so it
            # goes through the stricter-prompt retry rather than shipping
            # ungrounded prose.
            logger.info("citation_validation_no_markers_found")
            return False, []

        validated: list[ValidatedCitation] = []
        for match in markers:
            idx = int(match.group(1)) - 1
            if idx < 0 or idx >= len(chunks):
                logger.info("citation_validation_index_out_of_range", index=idx + 1)
                return False, []

            chunk = chunks[idx]
            claim_sentence = _sentence_containing(answer_text, match.start())
            overlap = _jaccard(claim_sentence, chunk.chunk_text)
            if overlap < self._min_overlap:
                logger.info(
                    "citation_validation_low_overlap",
                    index=idx + 1, overlap=round(overlap, 3),
                )
                return False, []

            validated.append(
                ValidatedCitation(
                    source_doctype=chunk.source_doctype,
                    source_name=chunk.source_name,
                    span_type=chunk.span_type,
                    span_start=chunk.span_start,
                    span_end=chunk.span_end,
                    quoted_span=chunk.chunk_text[:280],
                )
            )

        return True, validated
