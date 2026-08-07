# src/buildpolaris_ai/platform/retrieval/pgvector_adapter.py
import asyncpg
import json
import uuid
from pgvector.asyncpg import register_vector
from buildpolaris_ai.platform.retrieval.vector_store import VectorStoreProtocol
import structlog

logger = structlog.get_logger()

class PgVectorAdapter(VectorStoreProtocol):
    """Hexagonal Adapter for pgvector."""
    def __init__(self, conn: asyncpg.Connection):
        self.conn = conn

    async def setup(self):
        # Register the pgvector type so asyncpg knows how to serialize Python lists
        await register_vector(self.conn)
        logger.info("Registered pgvector type with asyncpg")
        
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS public.document_embeddings (
                id UUID PRIMARY KEY,
                embedding vector(768), 
                metadata JSONB
            );
        """)

    async def upsert_embedding(self, doc_id: str, embedding: list[float], metadata: dict) -> None:
        native_id = uuid.UUID(doc_id) if isinstance(doc_id, str) else doc_id
        metadata_json = json.dumps(metadata)
        
        await self.conn.execute("""
            INSERT INTO public.document_embeddings (id, embedding, metadata)
            VALUES ($1, $2, $3)
            ON CONFLICT (id) DO UPDATE 
            SET embedding = EXCLUDED.embedding, metadata = EXCLUDED.metadata;
        """, native_id, embedding, metadata_json)

    async def search(self, query_embedding: list[float], limit: int = 3) -> list[dict]:
        # CORRECT FIX: Pass the list directly. The register_vector codec will 
        # automatically and correctly serialize it to PostgreSQL's vector type.
        # Debug: log embedding length and number of rows visible to this session
        try:
            embed_len = len(query_embedding) if query_embedding is not None else 0
        except Exception:
            embed_len = 0
        logger.info("Vector search invoked", embedding_length=embed_len, limit=limit)
        try:
            table_count = await self.conn.fetchval("SELECT COUNT(*) FROM public.document_embeddings;")
        except Exception as e:
            table_count = None
            logger.warning("Failed to count document_embeddings", error=str(e))
        logger.info("document_embeddings visible rows", count=table_count)

        rows = await self.conn.fetch("""
            SELECT id, metadata, embedding <-> $1 AS distance
            FROM public.document_embeddings
            ORDER BY distance
            LIMIT $2
        """, query_embedding, limit)
        
        results = []
        for row in rows:
            meta = row['metadata']
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except json.JSONDecodeError:
                    meta = {}
            
            results.append({
                'id': row['id'],
                'metadata': meta,
                'distance': row['distance']
            })
        return results