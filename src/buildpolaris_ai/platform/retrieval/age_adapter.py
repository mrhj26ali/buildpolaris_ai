# src/buildpolaris_ai/platform/retrieval/age_adapter.py
import asyncpg
from buildpolaris_ai.platform.retrieval.graph_store import GraphStoreProtocol

class AGEAdapter(GraphStoreProtocol):
    """Hexagonal Adapter for Apache AGE."""
    def __init__(self, conn: asyncpg.Connection, graph_name: str = "polaris_knowledge_graph"):
        self.conn = conn
        self.graph_name = graph_name

    async def upsert_document_node(self, doctype: str, docname: str, properties: dict) -> None:
        # Sanitize strings for Cypher
        safe_doctype = doctype.replace("'", "''")
        safe_docname = docname.replace("'", "''")
        
        # Build Cypher property assignments
        props = []
        for k, v in properties.items():
            if isinstance(v, str):
                escaped = v.replace("'", "''")
                props.append(f"n.{k} = '{escaped}'")
            elif isinstance(v, bool):
                props.append(f"n.{k} = {str(v).lower()}")
            elif isinstance(v, (int, float)):
                props.append(f"n.{k} = {v}")
        
        set_clause = f"SET n.doctype = '{safe_doctype}'"
        if props:
            set_clause += ", " + ", ".join(props)

        query = f"""
            SELECT * FROM ag_catalog.cypher('{self.graph_name}', $$
                MERGE (n:Document {{docname: '{safe_docname}'}})
                {set_clause}
                RETURN n
            $$) AS (n ag_catalog.agtype);
        """
        await self.conn.execute(query)
