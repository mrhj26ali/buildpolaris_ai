# src/buildpolaris_ai/gateway/api/copilot_test.py
import asyncpg
import ollama
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from pgvector.asyncpg import register_vector
import structlog

from buildpolaris_ai.platform.retrieval.pgvector_adapter import PgVectorAdapter
from buildpolaris_ai.platform.retrieval.age_adapter import AGEAdapter
from buildpolaris_ai.platform.retrieval.citation_validator import CitationValidator, RAGResponse
from buildpolaris_ai.platform.model_provider.ollama_adapter import OllamaProvider

logger = structlog.get_logger()
router = APIRouter(prefix="/copilot", tags=["Copilot"])

async def get_db_conn():
    conn = await asyncpg.connect(
        user="polaris_ai", password="polaris_ai_dev_password", 
        host="localhost", port="5432", database="polaris_knowledge"
    )
    
    await register_vector(conn)
    await conn.execute('LOAD \'age\'; SET search_path = ag_catalog, "$user", public;')
    
    try:
        yield conn
    finally:
        await conn.close()

class QueryRequest(BaseModel):
    question: str

@router.post("/query")
async def copilot_query(req: QueryRequest, conn: asyncpg.Connection = Depends(get_db_conn)):
    """
    TRUE HYBRID RAG endpoint:
    1. Embed query -> 2. Vector Search -> 3. Graph Enrichment -> 4. Generate -> 5. Validate.
    """
    # 1. Generate query embedding
    ollama_client = ollama.AsyncClient()
    query_embedding_resp = await ollama_client.embeddings(model='nomic-embed-text', prompt=req.question)
    query_embedding = query_embedding_resp['embedding']
    
    logger.info(f"Generated query embedding of dimension: {len(query_embedding)}")
    
    # 2. Vector Search (Semantic Retrieval)
    vector_store = PgVectorAdapter(conn)
    vector_results = await vector_store.search(query_embedding, limit=3)
    
    logger.info(f"Vector search returned {len(vector_results)} results")
    
    if not vector_results:
        return {"answer": "I don't have enough information in the knowledge base to answer that.", "citations": [], "citations_validated": True}
    
    # 3. Graph Enrichment (Relational Retrieval)
    seed_docnames = [res['metadata'].get('docname') for res in vector_results if res['metadata'].get('docname')]
    graph_store = AGEAdapter(conn)
    graph_results = await graph_store.enrich_with_graph_context(seed_docnames, limit=3)
    
    logger.info(f"Graph enrichment found {len(graph_results)} related documents")
    
    # 4. Merge and Format Context for the LLM
    context_str = ""
    source_docs_map = {}
    
    # Add vector results
    for res in vector_results:
        meta = res['metadata']
        docname = meta.get('docname', 'Unknown')
        doctype = meta.get('doctype', 'Unknown')
        subject = meta.get('subject', meta.get('title', ''))
        description = meta.get('description', '')
        status = meta.get('status', 'N/A')
        
        context_str += f"[Document: {docname}]\nType: {doctype}\nSubject: {subject}\nStatus: {status}\nDescription: {description}\n\n"
        source_docs_map[docname] = f"Type: {doctype} Subject: {subject} Status: {status} Description: {description}"
        
    # Add graph results (if any)
    for res in graph_results:
        docname = res['docname']
        if docname not in source_docs_map: # Avoid duplicates
            context_str += f"[Related Document: {docname}]\nType: {res['doctype']}\nRelationship: {res['relationship']}\nSubject: {res['subject']}\n\n"
            source_docs_map[docname] = f"Type: {res['doctype']} Relationship: {res['relationship']} Subject: {res['subject']}"
        
    logger.info(f"Retrieved context documents for RAG docs={list(source_docs_map.keys())}")
    
    # 5. Prompt LLM with strict JSON and citation instructions
    prompt = f"""You are a helpful construction project management assistant. 
Answer the user's question based ONLY on the provided context. 
You MUST output a valid JSON object with "answer" and "citations" fields.

CRITICAL RULES:
1. If you find the answer in the context, you MUST provide at least one citation in the "citations" array.
2. The "source_docname" must exactly match the document name in the context (e.g., "RFI-1009").
3. The "quoted_span" must be an EXACT, verbatim substring from the context that proves your answer.
4. If the answer is NOT in the context, set "answer" to "I don't have enough information in the knowledge base to answer that." and "citations" to [].

Context:
{context_str}

Question: {req.question}
"""
    
    # 6. Generate structured response using Instructor
    provider = OllamaProvider()
    rag_response = await provider.structured_generate(prompt, RAGResponse)
    
    logger.info(f"RAG model response", rag_response=rag_response.model_dump())
    
    # 7. Validate citations deterministically (NFR-AI-18)
    validator = CitationValidator()
    is_valid = validator.validate(rag_response, source_docs_map)
    
    if not is_valid:
        return {
            "answer": "I couldn't verify the sources for this answer. Please check the documents manually.",
            "citations": [],
            "citations_validated": False
        }
    
    return {
        "answer": rag_response.answer,
        "citations": [c.model_dump() for c in rag_response.citations],
        "citations_validated": is_valid
    }