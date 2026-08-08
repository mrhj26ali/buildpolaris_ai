from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class GraphStoreProtocol(Protocol):
    """
    Hexagonal Port for Graph Store interactions.

    This port is intentionally narrow and stable so the underlying adapter
    can be swapped without affecting callers.

    Every method is tenant-scoped (NFR-AI-3): implementations MUST accept
    and enforce `tenant_id` on both reads and writes.
    """

    async def upsert_document_node(
        self,
        doctype: str,
        docname: str,
        tenant_id: str,
        properties: dict[str, Any],
    ) -> None:
        """
        Insert or update a Document node in the graph, scoped to a tenant.

        Implementations MUST treat doctype/docname/properties as untrusted
        input and MUST NOT interpolate them directly into query strings.
        """
        ...

    async def enrich_with_graph_context(
        self,
        seed_docnames: list[str],
        tenant_id: str,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        """
        Given seed documents returned by vector search, traverse immediate
        graph relationships and return related documents for hybrid RAG.

        Implementations MUST parameterize all inputs and enforce the tenant
        boundary on BOTH the seed and the related nodes.
        """
        ...