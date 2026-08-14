"""Reciprocal Rank Fusion â€” combines multiple ranked result lists (one per
reformulated query, plus the graph-traversal list) into a single
deduplicated, re-ranked context set (Flowchart 4 step H).

RRF score for a document d: sum over lists L containing d of
1 / (k + rank_L(d)). k=60 is the standard default from the original RRF
paper and needs no per-corpus tuning to be effective.
"""
from __future__ import annotations

from collections import defaultdict
from typing import TypeVar

T = TypeVar("T")


def reciprocal_rank_fusion(
    ranked_lists: list[list[T]], key_fn, k: int = 60
) -> list[T]:
    """`key_fn(item) -> hashable` identifies duplicate items across lists
    (e.g. chunk_id). Returns items ordered by fused score, deduplicated,
    keeping the first-seen instance of each key for the returned object.
    """
    scores: dict = defaultdict(float)
    first_seen: dict = {}

    for ranked_list in ranked_lists:
        for rank, item in enumerate(ranked_list, start=1):
            key = key_fn(item)
            scores[key] += 1.0 / (k + rank)
            if key not in first_seen:
                first_seen[key] = item

    ordered_keys = sorted(scores.keys(), key=lambda k_: scores[k_], reverse=True)
    return [first_seen[k_] for k_ in ordered_keys]
