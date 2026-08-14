"""Assembles the individual metric outputs into one report, and flags a
regression when a metric drops below a fixed floor â€” the eval harness's
job is to make a citation-accuracy or grounding regression loud in CI,
not just measurable after the fact.
"""
from __future__ import annotations

CITATION_ACCURACY_FLOOR = 0.7
GROUNDING_SCORE_FLOOR = 0.8


def build_regression_report(citation_accuracy: dict, grounding: dict, raw_results: list[dict]) -> dict:
    regressions = []

    if citation_accuracy.get("accuracy") is not None and citation_accuracy["accuracy"] < CITATION_ACCURACY_FLOOR:
        regressions.append(
            f"citation_accuracy {citation_accuracy['accuracy']:.2f} below floor {CITATION_ACCURACY_FLOOR}"
        )
    if grounding.get("score") is not None and grounding["score"] < GROUNDING_SCORE_FLOOR:
        regressions.append(f"grounding_score {grounding['score']:.2f} below floor {GROUNDING_SCORE_FLOOR}")

    return {
        "citation_accuracy": citation_accuracy,
        "grounding": grounding,
        "case_count": len(raw_results),
        "regressions": regressions,
        "passed": len(regressions) == 0,
    }
