"""One-shot: embed seeded mock docs into the vector store."""
import asyncio, json, sys, uuid
sys.path.insert(0, "src")
from buildpolaris_ai.platform.retrieval.connection import create_ai_connection
from buildpolaris_ai.platform.retrieval.pgvector_adapter import PgVectorAdapter
from buildpolaris_ai.platform.embedding.service import get_embedding_service


def build_text(doctype, docname, payload):
    parts = [f"Document ID: {docname}. Type: {doctype}."]
    for key in ["description", "subject", "title"]:
        if payload.get(key):
            parts.append(str(payload[key]))
    return " ".join(parts)


async def main():
    conn = await create_ai_connection()
    vector_store = PgVectorAdapter(conn)
    await vector_store.setup()
    embedder = get_embedding_service()

    rows = await conn.fetch(
        "SELECT tenant_id, doctype, docname, payload FROM public.mock_erpnext_docs"
    )
    if not rows:
        print("mock_erpnext_docs is EMPTY. Run: uv run python scripts/seed_mock_data.py first.")
        await conn.close(); return

    print(f"Embedding {len(rows)} documents...")
    count = 0
    for row in rows:
        payload = row["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        text = build_text(row["doctype"], row["docname"], payload)
        embedding = await embedder.embed_text(text)
        chunk_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{row['docname']}:0"))
        meta = {**payload, "docname": row["docname"], "doctype": row["doctype"]}
        await vector_store.upsert_embedding(chunk_id, row["tenant_id"], embedding, meta)
        count += 1
    print(f"Embedded {count} documents.")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
