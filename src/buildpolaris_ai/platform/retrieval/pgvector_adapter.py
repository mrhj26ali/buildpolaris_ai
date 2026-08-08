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
        await register_vector(self.conn)
        logger.info("Registered pgvector type with asyncpg")

        # Create the table if missing and ensure tenant_id column exists.
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS public.document_embeddings (
                id UUID PRIMARY KEY,
                embedding vector(768),
                metadata JSONB
            );
        """)

        # Add tenant_id if it's missing (safe in mixed-schema environments)
        await self.conn.execute("""
            ALTER TABLE IF EXISTS public.document_embeddings
            ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(100) DEFAULT 'UNKNOWN'::varchar;
        """)

        # Index for fast tenant filtering (IF NOT EXISTS not supported for CREATE INDEX in older PG versions)
        await self.conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE c.relname = 'idx_document_embeddings_tenant' AND n.nspname = 'public'
                ) THEN
                    CREATE INDEX idx_document_embeddings_tenant ON public.document_embeddings(tenant_id);
                END IF;
            END$$;
        """)

    async def upsert_embedding(self, doc_id: str, tenant_id: str, embedding: list[float], metadata: dict) -> None:
        native_id = uuid.UUID(doc_id) if isinstance(doc_id, str) else doc_id
        metadata_json = json.dumps(metadata)
        await self.conn.execute("""
            INSERT INTO public.document_embeddings (id, tenant_id, embedding, metadata)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (id) DO UPDATE
            SET tenant_id = EXCLUDED.tenant_id,
                embedding = EXCLUDED.embedding, 
                metadata = EXCLUDED.metadata;
        """, native_id, tenant_id, embedding, metadata_json)

    async def search(self, query_embedding: list[float], tenant_id: str, limit: int = 3) -> list[dict]:
        try:
            embed_len = len(query_embedding) if query_embedding is not None else 0
        except Exception:
            embed_len = 0
        logger.info("Vector search invoked", embedding_length=embed_len, tenant_id=tenant_id, limit=limit)

        # Ensure we always call fetch even if embedding is falsy
        rows = await getattr(self.conn, "fetch")("""
            SELECT id, metadata, embedding <-> $1 AS distance
            FROM public.document_embeddings
            WHERE tenant_id = $3
            ORDER BY distance
            LIMIT $2
        """, query_embedding, limit, tenant_id)

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