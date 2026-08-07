# src/buildpolaris_ai/platform/retrieval/pgvector_adapter.py
import asyncpg
import json
from pgvector.asyncpg import register_vector
from buildpolaris_ai.platform.retrieval.vector_store import VectorStoreProtocol

class PgVectorAdapter(VectorStoreProtocol):
    """Hexagonal Adapter for pgvector."""
    def __init__(self, conn: asyncpg.Connection):
        self.conn = conn

    async def setup(self):
        """Ensure the vector table exists and register the vector type with asyncpg."""
        # CRITICAL FIX: Register the pgvector type so asyncpg knows how to serialize 
        # Python lists to the PostgreSQL 'vector' type and vice versa.
        await register_vector(self.conn)
        
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS public.document_embeddings (
                id UUID PRIMARY KEY,
                embedding vector(768), -- nomic-embed-text dimension
                metadata JSONB
            );
        """)

    async def upsert_embedding(self, doc_id: str, embedding: list[float], metadata: dict) -> None:
        await self.conn.execute("""
            INSERT INTO public.document_embeddings (id, embedding, metadata)
            VALUES ($1, $2, $3)
            ON CONFLICT (id) DO UPDATE 
            SET embedding = EXCLUDED.embedding, metadata = EXCLUDED.metadata;
        """, doc_id, embedding, json.dumps(metadata))