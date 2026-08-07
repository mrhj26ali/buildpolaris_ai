# src/buildpolaris_ai/platform/retrieval/age_adapter.py
import asyncpg
import json
from buildpolaris_ai.platform.retrieval.graph_store import GraphStoreProtocol
import structlog

logger = structlog.get_logger()

class AGEAdapter(GraphStoreProtocol):
    """Hexagonal Adapter for Apache AGE."""
    def __init__(self, conn: asyncpg.Connection, graph_name: str = "polaris_knowledge_graph"):
        self.conn = conn
        self.graph_name = graph_name

    async def upsert_document_node(self, doctype: str, docname: str, properties: dict) -> None:
        safe_doctype = doctype.replace("'", "''")
        safe_docname = docname.replace("'", "''")
        
        props = []
        for k, v in properties.items():
            if isinstance(v, str):
                props.append(f"{k}: '{v.replace("'", "''")}'")
            elif isinstance(v, bool):
                props.append(f"{k}: {str(v).lower()}")
            elif isinstance(v, (int, float)):
                props.append(f"{k}: {v}")
        props_str = ", ".join(props)

        query = f"""
            SELECT * FROM ag_catalog.cypher('{self.graph_name}', $$
                MERGE (n:Document {{docname: '{safe_docname}'}})
                SET n.doctype = '{safe_doctype}', {props_str}
                RETURN n
            $$) AS (n ag_catalog.agtype);
        """
        await self.conn.execute(query)

    async def enrich_with_graph_context(self, seed_docnames: list[str], limit: int = 3) -> list[dict]:
        """
        Hybrid RAG Step 2: Take the docnames found by vector search, 
        and traverse the graph to find directly related documents (e.g., linked Change Events, Tasks).
        """
        if not seed_docnames:
            return []
            
        # Format docnames for Cypher IN clause
        docnames_str = ", ".join([f"'{d.replace("'", "''")}'" for d in seed_docnames])
        
        # Query: Find the seed documents and any documents they are linked to
        query = f"""
            SELECT * FROM ag_catalog.cypher('{self.graph_name}', $$
                MATCH (seed:Document)
                WHERE seed.docname IN [{docnames_str}]
                OPTIONAL MATCH (seed)-[r]-(related:Document)
                RETURN seed.docname AS seed_doc, related.doctype AS related_type, related.docname AS related_doc, related.subject AS related_subject
                LIMIT {limit}
            $$) AS (seed_doc ag_catalog.agtype, related_type ag_catalog.agtype, related_doc ag_catalog.agtype, related_subject ag_catalog.agtype);
        """
        
        try:
            rows = await self.conn.fetch(query)
            enriched = []
            for row in rows:
                # agtype returns strings with quotes, so we strip them
                seed = str(row['seed_doc']).strip('"')
                rel_type = str(row['related_type']).strip('"') if row['related_type'] else None
                rel_doc = str(row['related_doc']).strip('"') if row['related_doc'] else None
                rel_subject = str(row['related_subject']).strip('"') if row['related_subject'] else "N/A"
                
                if rel_doc and rel_doc != seed:
                    enriched.append({
                        'docname': rel_doc,
                        'doctype': rel_type,
                        'subject': rel_subject,
                        'relationship': f"Linked to {seed}"
                    })
            return enriched
        except Exception as e:
            logger.warning("Graph enrichment failed, falling back to vector-only", error=str(e))
            return []