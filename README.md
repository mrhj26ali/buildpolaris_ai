# buildpolaris_ai

FastAPI sidecar implementing BuildPolaris's AI Copilot, RAG retrieval
(pgvector + Apache AGE hybrid), and the four proposed-action agents. Built
against `ARCH v2.1 Â§3.3/Â§4.2/Â§6.3`, `ERD v2.1 Â§4`, `SDD v2.1` M8, `UC v2.1`
UC-8.1â€“UC-8.4, and `REQ v2.1` FR-8.x/NFR-AIGOV.x.

## Layout

- `app/gateway/` â€” HTTP surface: routers, auth (service credential +
  Scope Assertion), request/response schemas, middleware.
- `app/orchestrator/` â€” the microkernel: agent registry, turn runner,
  intent classifier. Never imports a concrete agent directly.
- `app/agents/<name>/` â€” one folder per agent (`manifest.yaml` +
  `handler.py` + `prompts/`). Copy `app/agents/_template/` to add one.
- `app/platform/` â€” hexagonal ports + adapters: `model_provider/` (Gemini
  primary, Ollama fallback, Anthropic/OpenAI extensibility slots),
  `vector_store/` (pgvector), `graph_store/` (Apache AGE), `rag/`
  (the full retrieval pipeline), `citations/`, `governance/`
  (ActionApprovalGateClient â€” proposes only, never resolves), `bff/`
  (the client back into buildpolaris_bff's MCP server).
- `app/ingest/` â€” isolated from the orchestrator entirely: ingestion
  (file -> citable chunk) and entity mirror (MariaDB -> AGE graph).
- `app/db/` â€” Postgres pool + typed row models.
- `app/eval/` â€” golden-set citation-accuracy / grounding-score harness.
- `migrations/` â€” numbered `.sql` files, applied by `migrations/env.py`.

## Local setup

```
cp .env.example .env
# fill in MODEL_PROVIDER__GEMINI_API_KEY (free key: https://aistudio.google.com/apikey)
docker compose up -d db redis
pip install -r requirements.txt --break-system-packages
python -m migrations.env
python scripts/register_agents.py     # sanity-checks every agent manifest
python scripts/seed_eval_data.py      # optional: local dev corpus
uvicorn app.main:app --reload
```

Never expose this service publicly â€” it is reachable only from
`buildpolaris_bff` on a private network segment (ARCH v2.1 Â§4.2).
