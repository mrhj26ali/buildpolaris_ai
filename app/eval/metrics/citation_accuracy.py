"""Citation accuracy metric â€” of the golden-set questions where a source
was expected, what fraction of the model's actual citations landed on an
expected source document.
"""
from __future__ import annotations


def score_citation_accuracy(results: list[dict]) -> dict:
    total_with_expected = 0
    correct = 0

    for r in results:
        expected = set(r.get("expected_sources", []))
        if not expected:
            continue
        total_with_expected += 1
        actual = set(r.get("citations", []))
        if expected & actual:
            correct += 1

    accuracy = correct / total_with_expected if total_with_expected else None
    return {
        "metric": "citation_accuracy",
        "total_cases": total_with_expected,
        "correct": correct,
        "accuracy": accuracy,
    }
