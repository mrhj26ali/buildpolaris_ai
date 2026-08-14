# buildpolaris_ai

**The AI sidecar for the BuildPolaris platform — RAG retrieval, agentic drafting, and the MCP client.**

`buildpolaris_ai` is a standalone Python/FastAPI service. It holds no facts of its own — everything in its database is a derived, disposable, rebuildable projection of what already exists in `buildpolaris_bff`. It can be deleted and rebuilt (by re-running ingestion and the entity mirror) without losing anything that matters legally or financially. It is never in the synchronous critical path of a non-AI workflow: if this service is down, every other part of BuildPolaris keeps working.

This document covers the project structure (folder hierarchy), what each part does, how to run the project, the technologies/tools/libraries it needs to run correctly, and — since this service depends on pretrained language and embedding models — exactly how to provide those models (via API keys or a local Ollama install) rather than shipping them in the repo.

---

## 0. Related BuildPolaris repositories

BuildPolaris is three separate repositories that together make up one platform. Link the other two here:

- `buildpolaris_bff` (backend / system of record — Frappe on ERPNext v16): `(https://github.com/mrhj26ali/buildpolaris_bff)`
- `buildpolaris_pwa` (offline-first frontend): `https://github.com/mrhj26ali/buildpolaris_pwa`

---

## 1. Where this component sits in the platform

```
buildpolaris_pwa  ──▶  buildpolaris_bff  ◀──▶  buildpolaris_ai   (THIS REPO)
  (never talks to           (mediates every call,       │
   buildpolaris_ai            re-scopes permissions,     ├── Postgres (pgvector + Apache AGE) — derived, disposable
   directly)                  is the MCP server)          ├── RAG pipeline, agents, MCP client
                                                            └── never exposed to the public internet — private network only
```

- Every path to this service goes through `buildpolaris_bff`. There is no direct frontend-to-AI path.
- `buildpolaris_bff` calls this service (ingestion, entity mirror, the copilot proxy) authenticated by a service credential plus a short-lived signed scope token — this service enforces tenant/project scope at the query layer using that token, without a round-trip back to the backend's database per query.
- This service calls back into `buildpolaris_bff` only through the MCP tool surface that `buildpolaris_bff` hosts — this service's own account has no direct access to any BuildPolaris data; every tool call runs on behalf of the forwarded scope token.
- Writes are never applied directly by this service. An agent only ever *proposes* a payload; the approval record and the approval authority both live in `buildpolaris_bff`.

## 2. Architecture style

**Hexagonal microkernel over a derived retrieval platform.**

- **Microkernel (plugin) architecture for agents** — `orchestrator/` (the kernel) knows nothing about RFI drafting or contract-clause extraction specifically. It looks up an agent by `agent_type` and calls `.run(context)`. Adding a new agent means adding a `manifest.yaml` + `handler.py` + `prompts/` — nothing in `orchestrator/` or `gateway/` changes.
- **Hexagonal (ports-and-adapters) for the platform-services layer** — three ports exist specifically so the underlying store/model can be swapped without touching callers:
  - `RetrievalAdapter` (pgvector / Apache AGE today) — swappable without touching `RagService`
  - `ModelProviderAdapter` (Groq, Gemini, OpenAI, Anthropic, local Ollama) — with a circuit breaker that falls back from a rate-limited free-tier key to a secondary provider without any agent code knowing a fallback occurred
  - `ActionApprovalGateClient` — deliberately thin; it can only *propose*, never *resolve* an approval

## 3. Project structure (folder hierarchy)

```text
buildpolaris_ai/
│
├── pyproject.toml
├── requirements.txt
├── Dockerfile
├── docker-entrypoint.sh
├── alembic.ini
├── docker-compose.yml           # local Postgres (pgvector + Apache AGE) + Redis
├── Dockerfile.db                # Postgres 16 image with pgvector + Apache AGE compiled in
├── init-db.sh                   # enables the extensions, creates the graph namespace
├── .env.example                 # copy to .env — see §7 below
│
├── migrations/                  # Alembic — schema for the derived Postgres store
│   └── versions/
│       ├── 0001_enable_pgvector.sql
│       ├── 0002_enable_apache_age.sql
│       ├── 0003_create_document_chunks.sql
│       ├── 0004_create_embeddings.sql
│       ├── 0005_create_graph_nodes.sql
│       ├── 0006_create_graph_edges.sql
│       └── 0007_create_agent_audit_tables.sql
│
├── eval/                        # golden-set quality evaluation (citation accuracy, grounding, etc.)
│   └── golden_sets/
│
├── scripts/                     # embed_seed_data, seed_mock_data, test_rag, verify_gemini, ...
│
└── src/
    ├── main.py
    │
    ├── app/
    │   ├── main.py, config.py, dependencies.py, exceptions.py
    │   │
    │   ├── gateway/              # HTTP boundary — the only layer that knows about FastAPI routing
    │   │   ├── routers/          # copilot_message, ingest, graph_sync, health, metrics
    │   │   ├── auth/             # service_credential, scope_assertion, on_behalf_of
    │   │   ├── schemas/          # Pydantic request/response contracts shared with buildpolaris_bff
    │   │   └── middleware/       # request_logging, timeout, circuit_breaker
    │   │
    │   ├── orchestrator/          # the microkernel — agent registry, turn runner, intent classifier
    │   │
    │   ├── agents/                 # one folder per agent, always {manifest.yaml, handler.py, prompts/}
    │   │   ├── rfi_drafting/
    │   │   ├── submittal_review/
    │   │   ├── daily_log_extraction/
    │   │   ├── contract_clause_extraction/
    │   │   └── _template/         # copy this to add a new agent
    │   │
    │   ├── platform/               # the hexagon's ports & adapters
    │   │   ├── model_provider/     # adapter.py + one file per provider + circuit_breaker.py
    │   │   ├── vector_store/       # pgvector adapter
    │   │   ├── graph_store/        # Apache AGE adapter
    │   │   ├── rag/                # query_transform, rrf (RAG-Fusion), chunker, embedder, retriever, reranker
    │   │   ├── citations/          # citation_validator.py — every generated claim is checked before it ships
    │   │   ├── governance/         # action_approval_gate, proposal_schema, payload_verifier, audit_logger
    │   │   └── bff/                # bff_client.py, mcp_client.py — this service is the MCP CLIENT
    │   │
    │   ├── ingest/                  # document ingestion — architecturally separate from query-time retrieval
    │   │   └── workers/             # embedding_worker, graph_projection_worker
    │   │
    │   ├── db/models/               # SQLAlchemy models for chunks, embeddings, graph nodes/edges, agent runs
    │   ├── eval/                    # run_eval.py + datasets/ + metrics/
    │   └── observability/           # structured logging, tracing, metrics, token_usage (feeds cost dashboard)
    │
    └── scripts/                    # rebuild_read_model, replay_cdc, seed_eval_data, register_agents
```

**Why retrieval is layered, not a single vector search:** a question like "which subcontractors on delayed tasks also have open safety incidents" isn't answerable from any single chunk's semantic neighborhood — it's a graph traversal, not a similarity search. So the pipeline is: intent classification → query transformation (2–4 reformulations) → parallel pgvector search per reformulation → Reciprocal Rank Fusion → a scoped Apache AGE graph traversal run in parallel when the question implies a multi-hop relationship → fused, deduplicated context → citation-validated generation (one stricter-prompt retry on failure, then a refusal — never an unvalidated answer shipped to a user).

## 4. Technologies, tools & libraries

Taken directly from this project's `pyproject.toml`:

| Concern | Library |
|---|---|
| Web framework | FastAPI, Uvicorn |
| Data validation | Pydantic v2, Pydantic Settings |
| Database driver | asyncpg (async Postgres) |
| Vector search | pgvector |
| Graph store | Apache AGE (via `apache-age-python`) — Cypher on Postgres |
| Cache / queue | Redis, hiredis |
| Agent orchestration | LangGraph (human-in-the-loop `interrupt()`/`Command(resume=...)` — this is what backs the write-approval requirement), langchain-core |
| Structured LLM output | `instructor` |
| Model providers | Groq, Google Gemini, OpenAI, Anthropic, Ollama — see §5 below, this is required, not optional |
| Embeddings | `sentence-transformers` (local, free) — see §5 below |
| Tool protocol | MCP (`mcp` package) — Streamable HTTP transport, this service is the **client**; `buildpolaris_bff` is the **server** |
| Document parsing | PyMuPDF (`fitz`) for PDFs, `pdfplumber`, `python-docx` for DOCX, `unstructured` |
| Auth | PyJWT (service-credential / scope-token verification) |
| Resilience | `tenacity` (retries), custom circuit breaker over model providers |
| Observability | `structlog`, OpenTelemetry (API + SDK + FastAPI instrumentation) |
| Testing | `pytest`, `pytest-asyncio`, `pytest-cov`, `pytest-mock`, `testcontainers`, `ragas` (RAG quality eval), `locust` (load) |
| Security/quality tooling | `bandit`, `ruff`, `pip-audit` |
| Migrations | Alembic |
| Package management | [`uv`](https://docs.astral.sh/uv/) |

## 5. LLM & embedding models — this service cannot run without at least one provider configured

This service does not ship any model weights in the repository. It calls out to either a hosted LLM API or a locally-run model, and it downloads a small pretrained embedding model on first run. You must configure **at least one** LLM path and the embedding model before the copilot, RAG retrieval, or any agent will work.

### Option A — Hosted API keys (fastest to get running, free tiers available)

| Provider | Role | Get a free key |
|---|---|---|
| Groq | Primary LLM provider | https://console.groq.com/keys (30 req/min, no credit card) |
| Google Gemini | Fallback LLM provider | https://aistudio.google.com/apikey (15 requests/min free) |
| OpenAI | Optional additional provider | https://platform.openai.com/api-keys |
| Anthropic | Optional additional provider | https://console.anthropic.com/settings/keys |

Set the corresponding key(s) in `.env` (see §7). The circuit breaker in `platform/model_provider/circuit_breaker.py` automatically falls back from the primary provider to the fallback provider if a call is rate-limited or fails — no code changes needed to add or rotate a provider, only `.env`.

### Option B — Local, fully offline models via Ollama

If you'd rather not depend on any external API, install [Ollama](https://ollama.com) and pull a model locally:

```bash
# Install Ollama (see https://ollama.com/download for your OS)
ollama pull llama3.1          # or any chat-capable model of your choice
ollama pull nomic-embed-text  # if you want to use Ollama for embeddings too (see below)
```

Then point the config at Ollama instead of a hosted provider (`MODEL_PROVIDER__PRIMARY_PROVIDER=ollama` in `.env`). Ollama's own model library, with the full list of models you can pull and their original sources, is at **https://ollama.com/library**.

### Embeddings — pretrained model, downloaded automatically, not committed to this repo

By default this service uses a small pretrained sentence-embedding model, loaded automatically by the `sentence-transformers` library the first time it runs:

- Model: **`all-MiniLM-L6-v2`**, 384 dimensions
- Original source / model card: **https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2**
- No fine-tuning is performed on this model — it is used exactly as published. The weights are downloaded and cached locally by the library (typically under `~/.cache/torch/sentence_transformers/`) and are **not** stored in this repository.

If you prefer to generate embeddings through Ollama instead, set `EMBEDDING__PROVIDER=ollama` and `EMBEDDING__MODEL=nomic-embed-text` in `.env` (model source: https://ollama.com/library/nomic-embed-text) after pulling it as shown above.

## 6. Prerequisites

- Python **3.12+**
- Docker + Docker Compose (for the local Postgres + Apache AGE + Redis stack)
- `uv` (or `pip`, if you prefer)
- At least one LLM path configured per §5 above (a free Groq key + a free Gemini key is the fastest way to get a fully working setup; Ollama is the fully local/offline alternative)

## 7. Setup & installation

```bash
git clone <this-repo-url> buildpolaris_ai
cd buildpolaris_ai

# 1. Bring up Postgres (pgvector + Apache AGE, pre-built) and Redis
docker compose up -d

# 2. Install Python dependencies
uv sync                       # or: pip install -e . --break-system-packages

# 3. Configure environment
cp .env.example .env
# then edit .env:
#  - set MODEL_PROVIDER__GROQ_API_KEY and/or MODEL_PROVIDER__GEMINI_API_KEY (see §5, Option A)
#    ...or set MODEL_PROVIDER__PRIMARY_PROVIDER=ollama (see §5, Option B)
#  - leave EMBEDDING__PROVIDER=sentence-transformers unless you want Ollama embeddings too

# 4. Run database migrations
alembic upgrade head

# 5. Start the service
uvicorn buildpolaris_ai.main:app --reload --port 8001
# or, using the project's own entry point:
buildpolaris-ai
```

On first run, the embedding model described in §5 is downloaded automatically — this requires a working internet connection the first time, even if you're using Ollama for the LLM itself.

The service exposes a `/health` endpoint separate from any authenticated route, and streams copilot responses via Server-Sent Events at `/copilot/message`.

## 8. Configuration (`.env`)

Key groups defined in `.env.example` — copy it to `.env` and never commit the real file:

- **Database** — Postgres connection (matches `docker-compose.yml`)
- **Redis** — cache/queue URL
- **Authentication** — dev mode locally; secret/JWKS mode in an environment wired to `buildpolaris_bff`'s real service credentials
- **Model Provider** — primary + fallback provider/model + API keys, or Ollama (§5)
- **Embeddings** — provider + model + dimensions (§5)
- **Retrieval (RAG)** — vector search limit, graph enrich limit, rerank top-k, RAG-Fusion/query-transform/HyDE toggles, chunk size/overlap
- **Backend Integration** — a mock mode for local frontend-independent development, or a real base URL pointed at a running `buildpolaris_bff` site
- **Governance** — per-tenant token soft/hard ceilings, max tokens per request
- **Resilience** — provider timeout, circuit breaker thresholds
- **Observability** — log level/format, tracing toggle

Real LLM API keys are never committed — `.env` is gitignored, and in production they're injected via environment/secret-manager at container start, never written into `manifest.yaml` or any versioned file.


