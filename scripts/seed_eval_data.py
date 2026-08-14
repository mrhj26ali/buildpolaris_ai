"""Seeds a small local dev/eval corpus directly into document_chunks +
embeddings, bypassing the /ingest HTTP path (no real BFF file needed) â€”
lets `python -m app.eval.run_eval` produce a meaningful score against
`eval/datasets/golden_qa.jsonl` on a bare-bones local setup.

Usage: python scripts/seed_eval_data.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.postgres import close_pool, get_pool, init_pool  # noqa: E402
from app.observability.logging import configure_logging, get_logger  # noqa: E402
from app.platform.model_provider.factory import get_model_provider  # noqa: E402
from app.platform.rag.chunker import RawChunk  # noqa: E402
from app.platform.rag.embedder import Embedder  # noqa: E402
from app.platform.vector_store.pgvector_adapter import PgVectorAdapter  # noqa: E402

configure_logging()
logger = get_logger(__name__)

SEED_DOCS = [
    {
        "source_doctype": "Commitment", "source_name": "COMMIT-0001",
        "file_id": "FILE-seed-0001", "content_hash": "seed-hash-0001",
        "chunks": [
            RawChunk("clause", 1, 1, "Article 5. Retention. Owner shall withhold retention "
                     "of ten percent (10%) from each progress payment until Substantial "
                     "Completion, at which point retention reduces to five percent (5%)."),
        ],
    },
    {
        "source_doctype": "Commitment", "source_name": "COMMIT-0002",
        "file_id": "FILE-seed-0002", "content_hash": "seed-hash-0002",
        "chunks": [
            RawChunk("clause", 1, 1, "Article 9. Notice of Delay Claims. Subcontractor "
                     "shall provide written notice of any delay claim within seven (7) "
                     "calendar days of the event giving rise to the claim, or the claim "
                     "is waived."),
        ],
    },
    {
        "source_doctype": "RFI", "source_name": "RFI-0004",
        "file_id": "FILE-seed-0004", "content_hash": "seed-hash-0004",
        "chunks": [
            RawChunk("page", 1, 1, "RFI-0004: Clash detected between HVAC duct routing and "
                     "the structural beam at gridline C4, level 3. Requesting revised "
                     "coordination drawing. Status: Open."),
        ],
    },
]


async def seed(company: str = "dev-co", project: str = "dev-project") -> None:
    await init_pool()
    try:
        embedder = Embedder(get_model_provider())
        async with get_pool().acquire() as conn:
            vector_store = PgVectorAdapter(conn)
            for doc in SEED_DOCS:
                for chunk in doc["chunks"]:
                    embedding = await embedder.embed_text(chunk.text)
                    await vector_store.upsert_chunk(
                        company=company, project=project, source_doctype=doc["source_doctype"],
                        source_name=doc["source_name"], file_id=doc["file_id"],
                        content_hash=doc["content_hash"], span_type=chunk.span_type,
                        span_start=chunk.span_start, span_end=chunk.span_end,
                        chunk_text=chunk.text, embedding=embedding, model_version=embedder.model_version,
                    )
                logger.info("seed_doc_indexed", source_name=doc["source_name"])
    finally:
        await close_pool()

    print(f"Seeded {len(SEED_DOCS)} document(s) for company='{company}' project='{project}'.")


if __name__ == "__main__":
    asyncio.run(seed())
