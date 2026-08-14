"""Eval harness runner â€” NFR-AIGOV.3 ("citation accuracy and approval-gate
reliability must be measurable, not just claimed") / ARCH Â§6.3. Runs the
golden datasets in eval/datasets/ against the live RagService + agent
pipeline and prints a regression_report.

Usage: python -m app.eval.run_eval
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.db.postgres import close_pool, init_pool
from app.eval.metrics.citation_accuracy import score_citation_accuracy
from app.eval.metrics.grounding_score import score_grounding
from app.eval.metrics.regression_report import build_regression_report
from app.observability.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)

DATASETS_DIR = Path(__file__).resolve().parent / "datasets"


async def _run_golden_qa() -> list[dict]:
    from app.dependencies import get_rag_service

    golden_path = DATASETS_DIR / "golden_qa.jsonl"
    if not golden_path.exists():
        logger.warning("golden_qa_dataset_missing", path=str(golden_path))
        return []

    rag_service = get_rag_service()
    results = []
    with golden_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            case = json.loads(line)
            answer = await rag_service.answer(case["question"], case["company"], case.get("project"))
            results.append(
                {
                    "question": case["question"],
                    "expected_sources": case.get("expected_sources", []),
                    "answer": answer.text,
                    "citations": [c.source_name for c in answer.citations],
                    "refused": answer.refused,
                }
            )
    return results


async def main() -> None:
    await init_pool()
    try:
        qa_results = await _run_golden_qa()
        citation_accuracy = score_citation_accuracy(qa_results)
        grounding = score_grounding(qa_results)
        report = build_regression_report(citation_accuracy, grounding, qa_results)
        print(json.dumps(report, indent=2))
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
