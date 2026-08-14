"""Grounding score â€” of all answered (non-refused) questions, what
fraction produced at least one citation at all. A low grounding score
means the model is answering confidently without citing anything, which
FR-8.3 treats as a correctness bug, not a style issue.
"""
from __future__ import annotations


def score_grounding(results: list[dict]) -> dict:
    answered = [r for r in results if not r.get("refused")]
    grounded = [r for r in answered if r.get("citations")]

    score = len(grounded) / len(answered) if answered else None
    return {
        "metric": "grounding_score",
        "answered_cases": len(answered),
        "grounded_cases": len(grounded),
        "score": score,
    }
