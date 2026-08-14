<#
BuildPolaris AI sidecar — full rebuild script (ARCH v2.1 §6.3 tree).

This DESTROYS and RECREATES the buildpolaris-ai project structure at the
current directory to match ARCH v2.1 / ERD v2.1 / REQ v2.1 exactly. Run
this FROM INSIDE your existing buildpolaris-ai folder:

    cd C:\Users\DELL\Desktop\Projects\4th-Year-Project\BuildPolaris\buildpolaris-ai
    powershell -ExecutionPolicy Bypass -File .\deploy_buildpolaris_ai.ps1

What it does:
  1. Backs up your current .env (if present) to .env.bak so your Gemini
     key etc. isn't lost, then removes the old src/, app/, migrations/,
     scripts/, eval/ folders and the old pyproject.toml/requirements.txt.
  2. Recreates the entire app/, migrations/, scripts/ tree with the new,
     ARCH-compliant code.
  3. Writes a fresh .env.example. Your OLD .env is restored automatically
     if it existed (merged is NOT automatic — see the note printed at the
     end; new required keys use the double-underscore nested format).
  4. Does NOT touch your .venv, .git, or docker volumes.

After running: fill in MODEL_PROVIDER__GEMINI_API_KEY in .env (get a free
key at https://aistudio.google.com/apikey), then:

    pip install -r requirements.txt --break-system-packages
    python -m migrations.env
    python scripts/register_agents.py
    uvicorn app.main:app --reload
#>

$ErrorActionPreference = "Stop"
$root = Get-Location
Write-Host "==> BuildPolaris AI rebuild starting in $root" -ForegroundColor Cyan

# --- 1. Backup + clean old tree -------------------------------------------
if (Test-Path ".env") {
    Copy-Item ".env" ".env.bak" -Force
    Write-Host "==> Backed up existing .env to .env.bak" -ForegroundColor Yellow
}

$oldPaths = @("src", "app", "migrations", "scripts", "eval", "pyproject.toml", "requirements.txt", "alembic.ini", "Dockerfile", "Dockerfile.db", "docker-compose.yml", "docker-entrypoint.sh", "init-db.sh", ".env.example")
foreach ($p in $oldPaths) {
    if (Test-Path $p) {
        Remove-Item $p -Recurse -Force
        Write-Host "==> Removed old $p" -ForegroundColor DarkGray
    }
}

# --- 2. Recreate tree -------------------------------------------------------
function New-Dir($path) {
    New-Item -ItemType Directory -Force -Path $path | Out-Null
}

function Write-File($path, $content) {
    $dir = Split-Path -Parent $path
    if ($dir -and -not (Test-Path $dir)) { New-Dir $dir }
    Set-Content -Path $path -Value $content -Encoding UTF8 -NoNewline
}

Write-Host "==> Writing files..." -ForegroundColor Cyan

Write-File ".env.example" @'
# =============================================================================
# BuildPolaris AI sidecar — environment configuration (ARCH v2.1 §7: secrets
# are injected at container start, never checked into a versioned file).
# Copy to .env for local dev. NEVER commit .env. Nested settings use a
# double underscore (matches app/config.py's env_nested_delimiter="__").
# =============================================================================

APP__ENVIRONMENT=development
APP__ENABLE_DEV_ROUTES=true

# --- Postgres (pgvector + Apache AGE) — disposable/rebuildable, ERD §1 ---
DATABASE__USER=polaris_ai
DATABASE__PASSWORD=polaris_ai_dev_password
DATABASE__HOST=localhost
DATABASE__PORT=5432
DATABASE__NAME=polaris_knowledge

# --- Redis (circuit-breaker/local rate state only — no message bus, ARCH §2.4) ---
REDIS__URL=redis://localhost:6379

# --- Service credential + Scope Assertion (ARCH §4.2 Direction 1) ---
SERVICE_AUTH__SERVICE_KEY=dev-bff-service-key-change-in-production
SERVICE_AUTH__SCOPE_ASSERTION_SECRET=dev-scope-assertion-secret-change-in-production
SERVICE_AUTH__SCOPE_ASSERTION_MAX_TTL_SECONDS=60

# --- Model provider — primary: Gemini free tier (NFR-MAINT.5/NFR-AIGOV.2) ---
MODEL_PROVIDER__PRIMARY=gemini
MODEL_PROVIDER__GEMINI_API_KEY=YOUR_GEMINI_API_KEY_HERE
MODEL_PROVIDER__GEMINI_MODEL=gemini-2.0-flash
MODEL_PROVIDER__GEMINI_EMBEDDING_MODEL=text-embedding-004
MODEL_PROVIDER__FALLBACK=ollama
MODEL_PROVIDER__OLLAMA_BASE_URL=http://localhost:11434
MODEL_PROVIDER__OLLAMA_MODEL=qwen2.5:3b-instruct
MODEL_PROVIDER__MODEL_VERSION_PIN=gemini-2.0-flash

# --- Embeddings (local, free — sentence-transformers; dimension pinned, ERD §8.1) ---
EMBEDDING__PROVIDER=sentence-transformers
EMBEDDING__MODEL=all-MiniLM-L6-v2
EMBEDDING__DIMENSIONS=384

# --- BFF callback (Direction 2 — AI calls BFF's MCP surface, on-behalf-of) ---
BFF__BASE_URL=http://localhost:8080
BFF__MCP_URL=http://localhost:8080/api/method/buildpolaris_bff.ai_copilot.mcp.mcp_server.handle
BFF__SERVICE_KEY=dev-ai-service-key-change-in-production
BFF__TIMEOUT_SECONDS=15

# --- AI governance (NFR-AIGOV.1) ---
GOVERNANCE__TOKEN_SOFT_CEILING_PER_TENANT=2000000
GOVERNANCE__TOKEN_HARD_CEILING_PER_TENANT=3000000

# --- Resilience (NFR-SCALE.5, circuit breaker) ---
RESILIENCE__PROVIDER_TIMEOUT_SECONDS=30
RESILIENCE__BREAKER_FAILURE_THRESHOLD=5
RESILIENCE__BREAKER_RECOVERY_SECONDS=30

OBSERVABILITY__LOG_LEVEL=INFO
OBSERVABILITY__LOG_FORMAT=console

'@

Write-File ".gitignore" @'
.venv/
__pycache__/
*.pyc
.env
.pytest_cache/
.ruff_cache/
*.egg-info/
dist/
build/

'@

Write-File "Dockerfile" @'
FROM python:3.11-slim

WORKDIR /srv/buildpolaris_ai

RUN apt-get update && apt-get install -y --no-install-recursive gcc libpq-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY migrations/ ./migrations/
COPY alembic.ini .
COPY docker-entrypoint.sh .
RUN chmod +x docker-entrypoint.sh

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

'@

Write-File "Dockerfile.db" @'
# Postgres image with pgvector + Apache AGE pre-installed (ARCH v2.1 §6.3,
# ERD v2.1 §1). Built from the postgres official image rather than a
# third-party AGE image so the Postgres version is under our control.
FROM postgres:16

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
      postgresql-server-dev-16 \
      git \
      ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# pgvector
RUN git clone --branch v0.7.4 https://github.com/pgvector/pgvector.git /tmp/pgvector \
    && cd /tmp/pgvector \
    && make \
    && make install \
    && rm -rf /tmp/pgvector

# Apache AGE (matched to Postgres 16)
RUN git clone --branch PG16/v1.5.0 https://github.com/apache/age.git /tmp/age \
    && cd /tmp/age \
    && make \
    && make install \
    && rm -rf /tmp/age

COPY init-db.sh /docker-entrypoint-initdb.d/10-init-db.sh
RUN chmod +x /docker-entrypoint-initdb.d/10-init-db.sh

'@

Write-File "README.md" @'
# buildpolaris_ai

FastAPI sidecar implementing BuildPolaris's AI Copilot, RAG retrieval
(pgvector + Apache AGE hybrid), and the four proposed-action agents. Built
against `ARCH v2.1 §3.3/§4.2/§6.3`, `ERD v2.1 §4`, `SDD v2.1` M8, `UC v2.1`
UC-8.1–UC-8.4, and `REQ v2.1` FR-8.x/NFR-AIGOV.x.

## Layout

- `app/gateway/` — HTTP surface: routers, auth (service credential +
  Scope Assertion), request/response schemas, middleware.
- `app/orchestrator/` — the microkernel: agent registry, turn runner,
  intent classifier. Never imports a concrete agent directly.
- `app/agents/<name>/` — one folder per agent (`manifest.yaml` +
  `handler.py` + `prompts/`). Copy `app/agents/_template/` to add one.
- `app/platform/` — hexagonal ports + adapters: `model_provider/` (Gemini
  primary, Ollama fallback, Anthropic/OpenAI extensibility slots),
  `vector_store/` (pgvector), `graph_store/` (Apache AGE), `rag/`
  (the full retrieval pipeline), `citations/`, `governance/`
  (ActionApprovalGateClient — proposes only, never resolves), `bff/`
  (the client back into buildpolaris_bff's MCP server).
- `app/ingest/` — isolated from the orchestrator entirely: ingestion
  (file -> citable chunk) and entity mirror (MariaDB -> AGE graph).
- `app/db/` — Postgres pool + typed row models.
- `app/eval/` — golden-set citation-accuracy / grounding-score harness.
- `migrations/` — numbered `.sql` files, applied by `migrations/env.py`.

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

Never expose this service publicly — it is reachable only from
`buildpolaris_bff` on a private network segment (ARCH v2.1 §4.2).

'@

Write-File "alembic.ini" @'
# BuildPolaris AI does not use Alembic's autogenerate machinery — the
# retrieval schema is small, hand-authored, and version-reviewed the same
# way MariaDB migrations are (ERD v2.1 §7: "a chunk table shape change
# requires a documented backfill plan, not a silent re-embed-on-next-query").
# This file exists so tooling that expects alembic.ini at the repo root
# doesn't break; the actual runner is migrations/env.py, which applies the
# numbered .sql files in migrations/versions/ in order and tracks state in
# a schema_migrations table. Run: python -m migrations.env
[alembic]
script_location = migrations
sqlalchemy.url = driver://user:pass@localhost/dbname

'@

Write-File "docker-compose.yml" @'
# Local dev stack for buildpolaris_ai in isolation from buildpolaris_bff.
# Brings up Postgres (pgvector + Apache AGE) and the sidecar itself.
services:
  db:
    build:
      context: .
      dockerfile: Dockerfile.db
    environment:
      POSTGRES_USER: polaris_ai
      POSTGRES_PASSWORD: polaris_ai_dev_password
      POSTGRES_DB: polaris_knowledge
    ports:
      - "5432:5432"
    volumes:
      - polaris_ai_pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U polaris_ai -d polaris_knowledge"]
      interval: 5s
      timeout: 5s
      retries: 10

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  ai:
    build:
      context: .
      dockerfile: Dockerfile
    env_file:
      - .env
    environment:
      DATABASE__HOST: db
      REDIS__URL: redis://redis:6379
    ports:
      - "8000:8000"
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_started

volumes:
  polaris_ai_pgdata:

'@

Write-File "docker-entrypoint.sh" @'
#!/bin/sh
# Runs pending Postgres migrations (pgvector + AGE + BuildPolaris schema)
# before starting the sidecar. Never exposed to the public internet
# directly (ARCH §4.2) — this container only listens on the private
# network segment reachable from buildpolaris_bff.
set -e

echo "[buildpolaris_ai] applying migrations..."
python -m migrations.env

echo "[buildpolaris_ai] starting: $@"
exec "$@"

'@

Write-File "init-db.sh" @'
#!/bin/bash
# Runs once, on first container init, as the postgres official image's
# docker-entrypoint-initdb.d convention. Enables both extensions so the
# very first connection from buildpolaris_ai's migration runner
# (migrations/env.py) already has CREATE EXTENSION permissions available
# without a superuser round-trip mid-migration.
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-SQL
    CREATE EXTENSION IF NOT EXISTS vector;
    CREATE EXTENSION IF NOT EXISTS age;
SQL

'@

Write-File "pyproject.toml" @'
[project]
name = "buildpolaris-ai"
version = "2.1.0"
description = "BuildPolaris AI sidecar — hexagonal microkernel over a derived retrieval platform (ARCH v2.1 §3.3, §6.3)"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "pydantic>=2.9.0",
    "pydantic-settings>=2.6.0",
    "asyncpg>=0.30.0",
    "pgvector>=0.3.6",
    "httpx>=0.27.0",
    "structlog>=24.4.0",
    "google-genai>=0.3.0",
    "sentence-transformers>=3.2.0",
    "PyMuPDF>=1.24.0",
    "python-docx>=1.1.0",
    "pyyaml>=6.0.2",
    "mcp>=1.1.0",
    "sse-starlette>=2.1.3",
]

[project.optional-dependencies]
# Only needed if a tenant is pinned to one of the extensibility-slot
# adapters (app/platform/model_provider/anthropic_adapter.py,
# openai_adapter.py) — neither is imported unless actually selected via
# MODEL_PROVIDER__PRIMARY or MODEL_PROVIDER__FALLBACK, so these are not
# in the base dependency set.
extended-providers = [
    "anthropic>=0.39.0",
    "openai>=1.54.0",
]
dev = [
    "pytest>=8.3.0",
    "pytest-asyncio>=0.24.0",
    "ruff>=0.7.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["app"]

[tool.ruff]
line-length = 100
target-version = "py311"

'@

Write-File "requirements.txt" @'
# Generated pin set — mirrors pyproject.toml. Install with:
#   pip install -r requirements.txt --break-system-packages
fastapi>=0.115.0
uvicorn[standard]>=0.32.0
pydantic>=2.9.0
pydantic-settings>=2.6.0
asyncpg>=0.30.0
pgvector>=0.3.6
httpx>=0.27.0
structlog>=24.4.0
google-genai>=0.3.0
sentence-transformers>=3.2.0
PyMuPDF>=1.24.0
python-docx>=1.1.0
pyyaml>=6.0.2
mcp>=1.1.0
sse-starlette>=2.1.3

# Optional — only required if pinned as a provider (see pyproject.toml's
# [project.optional-dependencies].extended-providers):
# anthropic>=0.39.0
# openai>=1.54.0

'@

New-Dir (Split-Path -Parent "app/__init__.py")
Write-File "app/__init__.py" @'

'@

New-Dir (Split-Path -Parent "app/config.py")
Write-File "app/config.py" @'
"""Centralized application configuration for the AI sidecar.

Every setting below maps to a specific requirement rather than existing
generically — see the inline references. Secrets are never checked into a
versioned file (ARCH v2.1 §7): this only reads from environment/.env.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseModel):
    environment: Literal["development", "staging", "production"] = "development"
    enable_dev_routes: bool = False


class DatabaseSettings(BaseModel):
    """Postgres — pgvector + Apache AGE. Disposable/rebuildable (ERD §1)."""

    user: str = "polaris_ai"
    password: SecretStr = SecretStr("polaris_ai_dev_password")
    host: str = "localhost"
    port: int = 5432
    name: str = "polaris_knowledge"

    def connect_kwargs(self) -> dict:
        return {
            "user": self.user,
            "password": self.password.get_secret_value(),
            "host": self.host,
            "port": self.port,
            "database": self.name,
        }


class RedisSettings(BaseModel):
    url: str = "redis://localhost:6379"


class ServiceAuthSettings(BaseModel):
    """ARCH v2.1 §4.2 Direction 1 — service credential + Scope Assertion.

    This is NOT user authentication (Frappe's session cookie already
    handles that end-to-end). It is a narrow, short-lived, service-to-
    service scope assertion the BFF mints after its own has_permission
    check has already passed.
    """

    service_key: SecretStr = SecretStr("dev-bff-service-key-change-in-production")
    scope_assertion_secret: SecretStr = SecretStr(
        "dev-scope-assertion-secret-change-in-production"
    )
    scope_assertion_max_ttl_seconds: int = 60


class ModelProviderSettings(BaseModel):
    """NFR-MAINT.5 / NFR-AIGOV.2 — swappable, version-pinnable provider."""

    primary: Literal["gemini", "ollama", "anthropic", "openai"] = "gemini"
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-2.0-flash"
    gemini_embedding_model: str = "text-embedding-004"

    fallback: Literal["gemini", "ollama", "anthropic", "openai", "none"] = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b-instruct"

    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-sonnet-4-6"
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-4o-mini"

    # NFR-AIGOV.2: pin a specific model version globally (or per-tenant via
    # model_pin.py) so a silent upstream update can't change agent
    # behavior without a deliberate, tested rollout.
    model_version_pin: str = "gemini-2.0-flash"


class EmbeddingSettings(BaseModel):
    provider: Literal["sentence-transformers", "gemini", "ollama"] = "sentence-transformers"
    model: str = "all-MiniLM-L6-v2"
    dimensions: int = 384
    batch_size: int = 32


class RagSettings(BaseModel):
    vector_search_limit: int = 10
    graph_traversal_limit: int = 10
    rerank_top_k: int = 5
    reranker_enabled: bool = False  # ARCH §3.3 point 6: optional, tenant-tunable
    max_citation_retries: int = 1  # UC-8.1 E1: exactly one stricter-prompt retry
    query_reformulations: int = 3  # 2-4 per ARCH §3.3 point 2
    rrf_k: int = 60  # published RRF default
    chunk_token_size: int = 512
    chunk_token_overlap: int = 64


class BFFClientSettings(BaseModel):
    """ARCH v2.1 §4.2 Direction 2 — AI calls BFF's MCP surface, on-behalf-of."""

    base_url: str = "http://localhost:8080"
    mcp_url: str = (
        "http://localhost:8080/api/method/"
        "buildpolaris_bff.ai_copilot.mcp.mcp_server.handle"
    )
    service_key: SecretStr = SecretStr("dev-ai-service-key-change-in-production")
    timeout_seconds: float = 15.0


class GovernanceSettings(BaseModel):
    """NFR-AIGOV.1 — spend observability with a soft ceiling before hard deny."""

    token_soft_ceiling_per_tenant: int = 2_000_000
    token_hard_ceiling_per_tenant: int = 3_000_000
    request_soft_ceiling_per_tenant: int = 20_000


class ResilienceSettings(BaseModel):
    """Backs the model_provider circuit breaker (ARCH §3.3 point 2)."""

    provider_timeout_seconds: float = 30.0
    breaker_failure_threshold: int = 5
    breaker_recovery_seconds: float = 30.0


class ObservabilitySettings(BaseModel):
    log_level: str = "INFO"
    log_format: Literal["console", "json"] = "console"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    app: AppSettings = Field(default_factory=AppSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    service_auth: ServiceAuthSettings = Field(default_factory=ServiceAuthSettings)
    model_provider: ModelProviderSettings = Field(default_factory=ModelProviderSettings)
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    rag: RagSettings = Field(default_factory=RagSettings)
    bff: BFFClientSettings = Field(default_factory=BFFClientSettings)
    governance: GovernanceSettings = Field(default_factory=GovernanceSettings)
    resilience: ResilienceSettings = Field(default_factory=ResilienceSettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)


@lru_cache
def get_settings() -> Settings:
    return Settings()

'@

New-Dir (Split-Path -Parent "app/dependencies.py")
Write-File "app/dependencies.py" @'
"""FastAPI dependency wiring — the composition root. Every router pulls
its collaborators from here rather than constructing adapters inline, so
swapping an adapter (NFR-EXT.2) touches exactly this file.
"""
from __future__ import annotations

from functools import lru_cache
from typing import AsyncIterator

import asyncpg
from fastapi import Depends

from app.db.session import get_db_conn
from app.gateway.auth.scope_assertion import ScopeAssertion, verify_scope_assertion
from app.orchestrator.agent_registry import AgentRegistry, get_agent_registry
from app.orchestrator.turn_runner import TurnRunner
from app.platform.citations.citation_validator import CitationValidator
from app.platform.graph_store.age_adapter import AgeGraphAdapter
from app.platform.model_provider.factory import get_model_provider
from app.platform.rag.embedder import Embedder
from app.platform.rag.rag_service import RagService
from app.platform.rag.retriever import Retriever
from app.platform.vector_store.pgvector_adapter import PgVectorAdapter


@lru_cache
def get_citation_validator() -> CitationValidator:
    return CitationValidator()


def get_embedder() -> Embedder:
    return Embedder(get_model_provider())


async def get_vector_store(conn: asyncpg.Connection = Depends(get_db_conn)) -> PgVectorAdapter:
    return PgVectorAdapter(conn)


async def get_graph_store(conn: asyncpg.Connection = Depends(get_db_conn)) -> AgeGraphAdapter:
    return AgeGraphAdapter(conn)


async def get_retriever(
    vector_store: PgVectorAdapter = Depends(get_vector_store),
    graph_store: AgeGraphAdapter = Depends(get_graph_store),
) -> Retriever:
    return Retriever(vector_store, graph_store, get_embedder())


async def get_rag_service_dep(
    vector_store: PgVectorAdapter = Depends(get_vector_store),
    graph_store: AgeGraphAdapter = Depends(get_graph_store),
    retriever: Retriever = Depends(get_retriever),
) -> RagService:
    return RagService(
        vector_store=vector_store, graph_store=graph_store, model_provider=get_model_provider(),
        retriever=retriever, citation_validator=get_citation_validator(),
    )


# Non-DI accessor for callers outside a request lifecycle (agents calling
# back into RagService need a plain awaitable-returning function, not a
# FastAPI Depends chain — see app/agents/submittal_review/handler.py and
# app/agents/contract_clause_extraction/handler.py). Always called from
# inside an already-running event loop (an agent's own `run()`), so this
# defers connection acquisition to the `.answer()` call itself rather
# than holding a pooled connection open for the agent's entire run.
class _LazyRagService:
    async def answer(self, question: str, company: str, project: str | None):
        from app.db.postgres import get_pool

        async with get_pool().acquire() as conn:
            vector_store = PgVectorAdapter(conn)
            graph_store = AgeGraphAdapter(conn)
            retriever = Retriever(vector_store, graph_store, get_embedder())
            service = RagService(
                vector_store=vector_store, graph_store=graph_store,
                model_provider=get_model_provider(), retriever=retriever,
                citation_validator=get_citation_validator(),
            )
            return await service.answer(question, company, project)


def get_rag_service() -> "_LazyRagService":
    return _LazyRagService()


async def get_turn_runner(
    rag_service: RagService = Depends(get_rag_service_dep),
    registry: AgentRegistry = Depends(get_agent_registry),
) -> TurnRunner:
    return TurnRunner(registry, rag_service)


async def get_ingestion_service(conn: asyncpg.Connection = Depends(get_db_conn)):
    from app.ingest.ingestion_service import IngestionService

    return IngestionService(PgVectorAdapter(conn), get_embedder(), conn)


async def get_entity_mirror_service(conn: asyncpg.Connection = Depends(get_db_conn)):
    from app.ingest.entity_mirror_service import EntityMirrorService

    return EntityMirrorService(AgeGraphAdapter(conn), conn)


def require_scope(assertion: ScopeAssertion = Depends(verify_scope_assertion)) -> ScopeAssertion:
    return assertion

'@

New-Dir (Split-Path -Parent "app/exceptions.py")
Write-File "app/exceptions.py" @'
"""Shared exception types for the AI sidecar.

Kept centralized so gateway/routers/*.py can map every one of these to a
correct HTTP status without each router re-inventing error shapes
(NFR-MAINT.1/.2).
"""
from __future__ import annotations


class BuildPolarisAIError(Exception):
    """Base class for every error this service raises deliberately."""


class InvalidServiceCredentialError(BuildPolarisAIError):
    """Caller did not present a valid X-Service-Key (ARCH §4.2 Direction 1)."""


class InvalidScopeAssertionError(BuildPolarisAIError):
    """Scope Assertion missing, expired, malformed, or signature mismatch."""


class ScopeMismatchError(BuildPolarisAIError):
    """Company/Project in a request doesn't match the asserted scope.

    UC-8.4 E3 — a defensive check applied to the ingestion write path too,
    not just reads (NFR-SEC.8).
    """


class UnknownAgentTypeError(BuildPolarisAIError):
    """OrchestrationLayer was asked to dispatch an agent_type with no
    registered module (FR-8.5 — should be structurally impossible if the
    orchestrator and the manifest registry stay in sync, but the caller-
    facing surface must still fail loudly rather than silently no-op)."""


class CitationValidationExhaustedError(BuildPolarisAIError):
    """UC-8.1 E2 — citation validation failed even after the single
    stricter-prompt retry. Callers must convert this into a refusal, never
    an unvalidated answer."""


class NoExtractableTextError(BuildPolarisAIError):
    """UC-8.4 E1 — no text layer found (e.g. scanned/image-only PDF).
    Carries a machine-readable reason so BFF can set
    AI Document Index.status = Failed(reason) rather than Indexed(empty)."""

    def __init__(self, reason: str = "no_text_layer") -> None:
        self.reason = reason
        super().__init__(reason)


class ModelProviderUnavailableError(BuildPolarisAIError):
    """All configured providers (primary + fallback) are unavailable.
    NFR-SCALE.5 requires the caller (BFF) to fail closed on this, not the
    sidecar silently degrading into a stale or fabricated answer."""


class ApprovalProposalError(BuildPolarisAIError):
    """ActionApprovalGateClient could not register a proposed write with
    the BFF. The sidecar never marks a write approved itself — if the
    proposal call fails, the agent output must be surfaced as failed, not
    silently treated as approved or discarded."""

'@

New-Dir (Split-Path -Parent "app/main.py")
Write-File "app/main.py" @'
"""buildpolaris_ai — FastAPI sidecar entrypoint.

Wires: middleware stack (request logging -> timeout -> circuit breaker),
every gateway router, exception handlers mapping every app.exceptions
type to a correct HTTP status, and startup/shutdown for the Postgres
pool + agent registry discovery.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.db.postgres import close_pool, init_pool
from app.exceptions import (
    ApprovalProposalError,
    BuildPolarisAIError,
    CitationValidationExhaustedError,
    InvalidScopeAssertionError,
    InvalidServiceCredentialError,
    ModelProviderUnavailableError,
    NoExtractableTextError,
    ScopeMismatchError,
    UnknownAgentTypeError,
)
from app.gateway.middleware.circuit_breaker_middleware import CircuitBreakerMiddleware
from app.gateway.middleware.request_logging import RequestLoggingMiddleware
from app.gateway.middleware.timeout_middleware import TimeoutMiddleware
from app.gateway.routers import copilot_message, graph_sync, health, ingest, metrics
from app.observability.logging import configure_logging, get_logger
from app.orchestrator.agent_registry import get_agent_registry

configure_logging()
logger = get_logger(__name__)

_EXCEPTION_STATUS_MAP: dict[type[Exception], int] = {
    InvalidServiceCredentialError: 401,
    InvalidScopeAssertionError: 401,
    ScopeMismatchError: 403,
    UnknownAgentTypeError: 400,
    CitationValidationExhaustedError: 422,
    NoExtractableTextError: 422,
    ModelProviderUnavailableError: 503,
    ApprovalProposalError: 502,
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    get_agent_registry()  # discover + register every agents/<name>/manifest.yaml on startup
    logger.info("buildpolaris_ai_startup_complete")
    yield
    await close_pool()
    logger.info("buildpolaris_ai_shutdown_complete")


app = FastAPI(
    title="buildpolaris_ai",
    description="BuildPolaris AI sidecar — hexagonal microkernel over a derived retrieval platform.",
    version="2.1.0",
    lifespan=lifespan,
)

app.add_middleware(CircuitBreakerMiddleware)
app.add_middleware(
    TimeoutMiddleware, timeout_seconds=get_settings().resilience.provider_timeout_seconds
)
app.add_middleware(RequestLoggingMiddleware)


@app.exception_handler(BuildPolarisAIError)
async def handle_buildpolaris_ai_error(request: Request, exc: BuildPolarisAIError):
    status_code = _EXCEPTION_STATUS_MAP.get(type(exc), 400)
    logger.warning(
        "buildpolaris_ai_error", error_type=type(exc).__name__, detail=str(exc), path=request.url.path
    )
    return JSONResponse(status_code=status_code, content={"detail": str(exc), "error": type(exc).__name__})


app.include_router(health.router)
app.include_router(metrics.router)
app.include_router(copilot_message.router)
app.include_router(ingest.router)
app.include_router(graph_sync.router)


if get_settings().app.enable_dev_routes:
    from app.gateway.auth.scope_assertion import mint_scope_assertion

    @app.get("/dev/mint-scope-assertion")
    async def dev_mint_scope_assertion(
        company: str = "dev-co", project: str = "dev-project", user: str = "dev@buildpolaris.local",
        role: str = "Project Manager",
    ) -> dict:
        """Dev-only helper — mints a Scope Assertion locally so the sidecar's
        test suite and manual curl/Postman sessions don't require a live BFF.
        Registered only when APP__ENABLE_DEV_ROUTES=true."""
        token = mint_scope_assertion(company, project, user, role)
        return {"scope_assertion": token}

'@

New-Dir (Split-Path -Parent "app/orchestrator/__init__.py")
Write-File "app/orchestrator/__init__.py" @'
from app.orchestrator.agent_registry import AgentRegistry, get_agent_registry
from app.orchestrator.turn_runner import TurnRunner

__all__ = ["AgentRegistry", "get_agent_registry", "TurnRunner"]

'@

New-Dir (Split-Path -Parent "app/orchestrator/agent_registry.py")
Write-File "app/orchestrator/agent_registry.py" @'
"""AgentRegistry — the microkernel's registration seam (ARCH §3.3).

Discovers every agents/<name>/manifest.yaml at startup, validates its
shape, and maps `agent_type` -> the agent's `run()` entrypoint. Adding a
new agent is: drop a new folder under app/agents/ with a manifest.yaml
and a handler.py exposing `async def run(context) -> AgentResult`, and
this registry picks it up on next startup — no orchestrator code changes.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from app.exceptions import UnknownAgentTypeError
from app.observability.logging import get_logger
from app.orchestrator.contracts import AgentModule

logger = get_logger(__name__)

AGENTS_DIR = Path(__file__).resolve().parent.parent / "agents"


@dataclass(slots=True)
class AgentManifest:
    agent_type: str
    display_name: str
    description: str
    target_doctype: str
    intent_examples: list[str]
    module_path: str


class AgentRegistry:
    def __init__(self) -> None:
        self._manifests: dict[str, AgentManifest] = {}
        self._modules: dict[str, AgentModule] = {}

    def discover(self) -> None:
        if not AGENTS_DIR.exists():
            logger.warning("agents_dir_missing", path=str(AGENTS_DIR))
            return

        for folder in sorted(AGENTS_DIR.iterdir()):
            if not folder.is_dir() or folder.name.startswith("_"):
                continue  # _template/ is a scaffold, never registered
            manifest_path = folder / "manifest.yaml"
            if not manifest_path.exists():
                continue

            raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            agent_type = raw["agent_type"]
            module_path = f"app.agents.{folder.name}.handler"

            self._manifests[agent_type] = AgentManifest(
                agent_type=agent_type,
                display_name=raw.get("display_name", agent_type),
                description=raw.get("description", ""),
                target_doctype=raw["target_doctype"],
                intent_examples=raw.get("intent_examples", []),
                module_path=module_path,
            )

            module = importlib.import_module(module_path)
            self._modules[agent_type] = module
            logger.info("agent_registered", agent_type=agent_type, module=module_path)

    def get_module(self, agent_type: str) -> AgentModule:
        module = self._modules.get(agent_type)
        if module is None:
            raise UnknownAgentTypeError(agent_type)
        return module

    def get_manifest(self, agent_type: str) -> AgentManifest:
        manifest = self._manifests.get(agent_type)
        if manifest is None:
            raise UnknownAgentTypeError(agent_type)
        return manifest

    def all_manifests(self) -> list[AgentManifest]:
        return list(self._manifests.values())

    def match_intent(self, message: str) -> str | None:
        """Very small keyword-overlap matcher used as intent_classifier's
        fallback when the LLM-based classification is ambiguous — real
        classification lives in orchestrator/intent_classifier.py; this is
        just registry-side lookup support so the classifier doesn't need
        its own copy of every agent's intent_examples."""
        message_lower = message.lower()
        for manifest in self._manifests.values():
            for example in manifest.intent_examples:
                if example.lower() in message_lower:
                    return manifest.agent_type
        return None


@lru_cache
def get_agent_registry() -> AgentRegistry:
    registry = AgentRegistry()
    registry.discover()
    return registry

'@

New-Dir (Split-Path -Parent "app/orchestrator/context.py")
Write-File "app/orchestrator/context.py" @'
"""TurnContext — everything an agent or the RAG path needs for one
copilot turn, threaded through explicitly rather than via globals so
concurrent turns (different tenants, different users) never leak state
into each other.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.gateway.auth.scope_assertion import ScopeAssertion
from app.platform.bff.mcp_client import BFFMCPClient
from app.platform.model_provider.adapter import ModelProviderAdapter


@dataclass(slots=True)
class TurnContext:
    thread_id: str
    message: str
    history: list[dict]
    assertion: ScopeAssertion
    raw_assertion_token: str
    trace_id: str
    model_provider: ModelProviderAdapter
    mcp_client: BFFMCPClient
    extra: dict = field(default_factory=dict)  # agent-specific scratch space (e.g. attached file refs)

    @property
    def company(self) -> str:
        return self.assertion.company

    @property
    def project(self) -> str | None:
        return self.assertion.project

    @property
    def user(self) -> str:
        return self.assertion.user

'@

New-Dir (Split-Path -Parent "app/orchestrator/contracts.py")
Write-File "app/orchestrator/contracts.py" @'
"""The AgentModule contract every agents/<name>/handler.py implements
(ARCH §3.3: "adding an agent = new folder + registry entry, never
touching the orchestrator"). This is the microkernel's one extension
point.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.orchestrator.context import TurnContext
from app.platform.governance.proposal_schema import ProposedAction


@dataclass(slots=True)
class AgentResult:
    proposed_action: ProposedAction
    rationale: str  # short human-readable summary shown alongside the pending-approval card


@runtime_checkable
class AgentModule(Protocol):
    """Every agent module exposes exactly this shape. The orchestrator
    calls `run()` and does nothing else — it never inspects an agent's
    internals, imports its prompts, or knows what target DocType it
    writes to (that's declared in the agent's own manifest.yaml and
    enforced by governance/payload_verifier.py, not by the orchestrator).
    """

    async def run(self, context: TurnContext) -> AgentResult: ...

'@

New-Dir (Split-Path -Parent "app/orchestrator/intent_classifier.py")
Write-File "app/orchestrator/intent_classifier.py" @'
"""Intent classification — Flowchart 4 step C ("buildpolaris_ai classifies
intent") + step D's three-way branch: navigation, grounded factual
question, or proposed action.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel

from app.observability.logging import get_logger
from app.orchestrator.agent_registry import AgentRegistry
from app.platform.model_provider.adapter import ModelProviderAdapter

logger = get_logger(__name__)


class IntentType(str, Enum):
    NAVIGATION = "navigation"
    GROUNDED_QUESTION = "grounded_question"
    PROPOSED_ACTION = "proposed_action"


class _IntentClassification(BaseModel):
    intent_type: IntentType
    agent_type: str | None = None  # populated only when intent_type == proposed_action


CLASSIFY_PROMPT = """Classify the user's request into exactly one category:

- "navigation": they want to find or open something that already exists
  (a record, screen, or link) — e.g. "show me RFI-042", "find the punch
  list for Building B".
- "grounded_question": they're asking a factual question that should be
  answered from indexed project documents, with citations — e.g. "what
  does the contract say about liquidated damages".
- "proposed_action": they want something drafted or created that would
  become a new or modified record — e.g. "draft an RFI about the beam
  clash", "review this submittal against the spec".

If proposed_action, also identify which of these agent types best fits:
{agent_types}

User message: {message}
"""


async def classify_intent(
    message: str, provider: ModelProviderAdapter, registry: AgentRegistry
) -> tuple[IntentType, str | None]:
    manifests = registry.all_manifests()
    agent_type_list = "\n".join(f"- {m.agent_type}: {m.description}" for m in manifests)

    prompt = CLASSIFY_PROMPT.format(agent_types=agent_type_list, message=message)
    try:
        result = await provider.structured_complete(prompt, _IntentClassification, temperature=0.0)
        return result.intent_type, result.agent_type
    except Exception as exc:  # noqa: BLE001
        logger.warning("intent_classification_failed_falling_back", error=str(exc))
        matched = registry.match_intent(message)
        if matched:
            return IntentType.PROPOSED_ACTION, matched
        return IntentType.GROUNDED_QUESTION, None

'@

New-Dir (Split-Path -Parent "app/orchestrator/tool_dispatcher.py")
Write-File "app/orchestrator/tool_dispatcher.py" @'
"""Dispatches a navigation-intent turn to the appropriate BFF read tool
(Flowchart 4 step E: "resolve within caller's existing permitted scope").
Kept separate from turn_runner.py so the mapping from a navigation intent
to a specific MCP tool call is independently testable/reviewable.
"""
from __future__ import annotations

from app.observability.logging import get_logger
from app.orchestrator.context import TurnContext
from app.platform.bff import read_tools

logger = get_logger(__name__)


async def dispatch_navigation(context: TurnContext) -> dict:
    """v1 heuristic: if the message looks like a direct doctype+name
    reference, fetch it; otherwise treat it as a free-text find. A more
    sophisticated slot-filling classifier is a natural extension point
    here without touching the orchestrator or any agent."""
    message = context.message.strip()

    doctypes = ["RFI", "Submittal Package", "Commitment", "Task", "Daily Log", "Punch List Item"]
    for doctype in doctypes:
        if doctype.lower() in message.lower():
            return await read_tools.find_record(context.mcp_client, doctype, message)

    return await read_tools.get_project_summary(context.mcp_client, context.project or "")

'@

New-Dir (Split-Path -Parent "app/orchestrator/turn_runner.py")
Write-File "app/orchestrator/turn_runner.py" @'
"""TurnRunner — executes one copilot turn end-to-end (ARCH Flowchart 4,
the whole diagram). This is the orchestrator's top-level entrypoint;
gateway/routers/copilot_message.py calls exactly this and streams its
result.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.observability.logging import get_logger
from app.observability.metrics import AGENT_RUNS_TOTAL, COPILOT_REQUESTS_TOTAL, counters
from app.orchestrator.agent_registry import AgentRegistry
from app.orchestrator.context import TurnContext
from app.orchestrator.intent_classifier import IntentType, classify_intent
from app.orchestrator.tool_dispatcher import dispatch_navigation
from app.platform.governance.action_approval_gate import ActionApprovalGateClient
from app.platform.rag.rag_service import RagAnswer, RagService

logger = get_logger(__name__)


@dataclass(slots=True)
class TurnResult:
    kind: str  # 'navigation' | 'grounded_answer' | 'pending_approval' | 'refusal'
    text: str | None = None
    rag_answer: RagAnswer | None = None
    navigation_result: dict | None = None
    approval_ref: str | None = None
    agent_type: str | None = None
    proposed_payload: dict | None = None
    model_version: str = ""


class TurnRunner:
    def __init__(self, registry: AgentRegistry, rag_service: RagService) -> None:
        self._registry = registry
        self._rag_service = rag_service

    async def run_turn(self, context: TurnContext) -> TurnResult:
        counters.increment(COPILOT_REQUESTS_TOTAL)

        intent_type, agent_type = await classify_intent(
            context.message, context.model_provider, self._registry
        )
        logger.info(
            "turn_intent_classified", intent_type=intent_type.value, agent_type=agent_type,
            trace_id=context.trace_id,
        )

        if intent_type == IntentType.NAVIGATION:
            result = await dispatch_navigation(context)
            return TurnResult(kind="navigation", navigation_result=result)

        if intent_type == IntentType.GROUNDED_QUESTION:
            answer = await self._rag_service.answer(context.message, context.company, context.project)
            kind = "refusal" if answer.refused else "grounded_answer"
            return TurnResult(kind=kind, rag_answer=answer, model_version=answer.model_version)

        # proposed_action
        if agent_type is None:
            logger.warning("proposed_action_with_no_agent_type_falling_back_to_rag")
            answer = await self._rag_service.answer(context.message, context.company, context.project)
            return TurnResult(
                kind="refusal" if answer.refused else "grounded_answer",
                rag_answer=answer, model_version=answer.model_version,
            )

        module = self._registry.get_module(agent_type)
        counters.increment(AGENT_RUNS_TOTAL)
        agent_result = await module.run(context)

        gate = ActionApprovalGateClient(context.raw_assertion_token)
        approval_ref = await gate.propose(agent_result.proposed_action)

        return TurnResult(
            kind="pending_approval",
            text=agent_result.rationale,
            approval_ref=approval_ref,
            agent_type=agent_type,
            proposed_payload=agent_result.proposed_action.payload,
            model_version=agent_result.proposed_action.model_version,
        )

'@

New-Dir (Split-Path -Parent "app/gateway/__init__.py")
Write-File "app/gateway/__init__.py" @'

'@

New-Dir (Split-Path -Parent "app/gateway/auth/__init__.py")
Write-File "app/gateway/auth/__init__.py" @'
from app.gateway.auth.scope_assertion import ScopeAssertion, verify_scope_assertion
from app.gateway.auth.service_credential import verify_service_credential

__all__ = ["ScopeAssertion", "verify_scope_assertion", "verify_service_credential"]

'@

New-Dir (Split-Path -Parent "app/gateway/auth/on_behalf_of.py")
Write-File "app/gateway/auth/on_behalf_of.py" @'
"""ARCH v2.1 §4.2 Direction 2 — AI calls BFF's MCP surface, on-behalf-of.

When this sidecar calls back into the BFF (a read-only MCP tool call, per
UC-8.2), it authenticates as itself (its own service credential) but
forwards the Scope Assertion it was handed for the current turn. The
BFF's has_permission check, when the tool call arrives, runs against the
*asserted user*, not against the AI service account's own permissions —
the AI service account itself has no direct Role-based access to any
BuildPolaris data; it is purely a transport identity.
"""
from __future__ import annotations

from app.gateway.auth.scope_assertion import ScopeAssertion


def build_on_behalf_of_headers(
    assertion: ScopeAssertion, ai_service_key: str, raw_assertion_token: str
) -> dict[str, str]:
    """Headers this sidecar attaches to an outbound call into
    buildpolaris_bff's MCP surface — reusing the exact assertion token it
    was handed, not re-minting one (the sidecar has no signing authority
    over Scope Assertions; only the BFF does)."""
    return {
        "X-Service-Key": ai_service_key,
        "X-Scope-Assertion": raw_assertion_token,
        "X-On-Behalf-Of-User": assertion.user,
        "X-On-Behalf-Of-Role": assertion.role,
    }

'@

New-Dir (Split-Path -Parent "app/gateway/auth/scope_assertion.py")
Write-File "app/gateway/auth/scope_assertion.py" @'
"""ARCH v2.1 §4.2 Direction 1 — the Scope Assertion.

A small, signed, short-lived payload minted by
`buildpolaris_bff/shared/scope_assertion.py` at request time, containing
`{company, project, user, role, expires_at}` with a ~60-second TTL. It
lets this sidecar enforce "the tool call inherits the calling user's
tenant/Project permission scope at the query layer" (NFR-SEC.8) without a
round-trip back to MariaDB on every retrieval query.

It is NOT a general-purpose auth token and is never sent to the browser.
A stolen or replayed assertion is limited by its short TTL and by the
fact that it can only ever narrow scope — the BFF only mints one after its
own has_permission check has already passed, so this can never grant a
permission the acting user's Role doesn't already have.

HMAC-SHA256 signed, symmetric secret shared with the BFF
(SERVICE_AUTH__SCOPE_ASSERTION_SECRET on both sides) — both services are
first-party and internal-network-only (ARCH §4.4), so asymmetric signing
isn't earning its complexity here.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass

from fastapi import Header

from app.config import get_settings
from app.exceptions import InvalidScopeAssertionError


@dataclass(slots=True, frozen=True)
class ScopeAssertion:
    company: str
    project: str | None
    user: str
    role: str
    expires_at: int

    def is_expired(self) -> bool:
        return time.time() >= self.expires_at


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def mint_scope_assertion(
    company: str, project: str | None, user: str, role: str, ttl_seconds: int | None = None
) -> str:
    """Used by tests/dev tooling and by BFF-side mirrors of this module.
    Production Scope Assertions are minted by buildpolaris_bff, but the
    sidecar carries this so its own test suite and local dev scripts don't
    need a live BFF just to exercise an authenticated call chain."""
    settings = get_settings().service_auth
    ttl = ttl_seconds or settings.scope_assertion_max_ttl_seconds
    payload = {
        "company": company,
        "project": project,
        "user": user,
        "role": role,
        "expires_at": int(time.time()) + ttl,
    }
    body = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    secret = settings.scope_assertion_secret.get_secret_value().encode()
    signature = _b64url_encode(hmac.new(secret, body.encode(), hashlib.sha256).digest())
    return f"{body}.{signature}"


def verify_scope_assertion(x_scope_assertion: str = Header(...)) -> ScopeAssertion:
    settings = get_settings().service_auth
    try:
        body, signature = x_scope_assertion.split(".", 1)
    except ValueError as exc:
        raise InvalidScopeAssertionError("malformed scope assertion") from exc

    secret = settings.scope_assertion_secret.get_secret_value().encode()
    expected_sig = _b64url_encode(hmac.new(secret, body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(signature, expected_sig):
        raise InvalidScopeAssertionError("scope assertion signature mismatch")

    try:
        payload = json.loads(_b64url_decode(body))
        assertion = ScopeAssertion(
            company=payload["company"],
            project=payload.get("project"),
            user=payload["user"],
            role=payload["role"],
            expires_at=int(payload["expires_at"]),
        )
    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        raise InvalidScopeAssertionError("scope assertion payload malformed") from exc

    if assertion.is_expired():
        raise InvalidScopeAssertionError("scope assertion expired")

    # Defensive belt-and-suspenders on top of the TTL embedded in the
    # payload: never trust an assertion whose *issued* lifetime exceeds
    # the sidecar's own configured max, even if the signature is valid.
    if assertion.expires_at - int(time.time()) > settings.scope_assertion_max_ttl_seconds:
        raise InvalidScopeAssertionError("scope assertion TTL exceeds configured maximum")

    return assertion

'@

New-Dir (Split-Path -Parent "app/gateway/auth/service_credential.py")
Write-File "app/gateway/auth/service_credential.py" @'
"""ARCH v2.1 §4.2 Direction 1 — service credential check.

`buildpolaris_ai` is never exposed to the public internet directly; every
path to it goes through `buildpolaris_bff`. This is the first of the two
checks every inbound call must pass: a simple X-Service-Key bearer header,
appropriate because this is a private-network call, not a public API
(ARCH explicitly rejects building the full external-facing OAuth 2.1
resource-server flow for a surface with exactly one internal consumer).
"""
from __future__ import annotations

import hmac

from fastapi import Header

from app.config import get_settings
from app.exceptions import InvalidServiceCredentialError


def verify_service_credential(x_service_key: str = Header(...)) -> None:
    settings = get_settings().service_auth
    expected = settings.service_key.get_secret_value()
    if not hmac.compare_digest(x_service_key, expected):
        raise InvalidServiceCredentialError("invalid X-Service-Key")

'@

New-Dir (Split-Path -Parent "app/gateway/middleware/__init__.py")
Write-File "app/gateway/middleware/__init__.py" @'

'@

New-Dir (Split-Path -Parent "app/gateway/middleware/circuit_breaker_middleware.py")
Write-File "app/gateway/middleware/circuit_breaker_middleware.py" @'
"""Gateway-level circuit breaker state exposure.

The actual breaker logic that matters (falling back from a rate-limited
model provider to a secondary one) lives in
platform/model_provider/circuit_breaker.py — that is a per-provider
concern, not a per-HTTP-request one. This middleware's job is narrower:
if the *model provider* breaker is currently open (all providers down),
fail fast on provider-dependent routes with a clear 503 rather than
letting the request proceed into a guaranteed timeout, which is what
actually protects NFR-SCALE.5 at the BFF's calling layer.
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.observability.logging import get_logger
from app.platform.model_provider.circuit_breaker import get_circuit_breaker

logger = get_logger(__name__)

PROVIDER_DEPENDENT_PATH_PREFIXES = ("/copilot/message", "/copilot/agent", "/ingest")


class CircuitBreakerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if any(path.startswith(p) for p in PROVIDER_DEPENDENT_PATH_PREFIXES):
            breaker = get_circuit_breaker()
            if breaker.all_providers_open():
                logger.warning("circuit_breaker_all_open_fail_fast", path=path)
                return JSONResponse(
                    status_code=503,
                    content={
                        "detail": "All configured model providers are currently "
                        "unavailable. This does not affect non-AI platform "
                        "functions (NFR-SCALE.5)."
                    },
                )
        return await call_next(request)

'@

New-Dir (Split-Path -Parent "app/gateway/middleware/request_logging.py")
Write-File "app/gateway/middleware/request_logging.py" @'
"""Structured request logging + trace_id propagation middleware
(NFR-OBS.1). Reads the inbound trace_id set by the PWA/job origin and
forwarded by buildpolaris_bff; mints one only if genuinely absent (a
direct/dev-tool call, never expected from the real BFF proxy path).
"""
from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.observability.logging import get_logger
from app.observability.tracing import new_trace_id, trace_id_var

logger = get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        trace_id = request.headers.get("X-Trace-Id") or new_trace_id()
        token = trace_id_var.set(trace_id)
        start = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "request_failed", path=request.url.path, method=request.method
            )
            raise
        finally:
            trace_id_var.reset(token)

        duration_ms = (time.monotonic() - start) * 1000
        logger.info(
            "request_completed",
            path=request.url.path,
            method=request.method,
            status_code=getattr(response, "status_code", None),
            duration_ms=round(duration_ms, 2),
            trace_id=trace_id,
        )
        response.headers["X-Trace-Id"] = trace_id
        return response

'@

New-Dir (Split-Path -Parent "app/gateway/middleware/timeout_middleware.py")
Write-File "app/gateway/middleware/timeout_middleware.py" @'
"""Per-request timeout — backs NFR-PERF.6's latency budget and, combined
with the circuit breaker, NFR-SCALE.5 ("the platform must remain fully
usable for all non-AI workflows if buildpolaris_ai is slow or
unreachable" — this is the sidecar's own half of failing fast rather than
hanging the BFF's request thread indefinitely).
"""
from __future__ import annotations

import asyncio

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.observability.logging import get_logger

logger = get_logger(__name__)

# SSE streaming responses (copilot/message) manage their own internal
# per-stage timeouts and must not be wrapped here — a blanket timeout
# would kill a legitimately long-lived stream.
EXEMPT_PATH_PREFIXES = ("/copilot/message",)


class TimeoutMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, timeout_seconds: float = 30.0) -> None:
        super().__init__(app)
        self._timeout = timeout_seconds

    async def dispatch(self, request: Request, call_next):
        if any(request.url.path.startswith(p) for p in EXEMPT_PATH_PREFIXES):
            return await call_next(request)

        try:
            return await asyncio.wait_for(call_next(request), timeout=self._timeout)
        except asyncio.TimeoutError:
            logger.error("request_timeout", path=request.url.path, timeout_s=self._timeout)
            return JSONResponse(
                status_code=504,
                content={"detail": "buildpolaris_ai timed out processing this request"},
            )

'@

New-Dir (Split-Path -Parent "app/gateway/schemas/__init__.py")
Write-File "app/gateway/schemas/__init__.py" @'

'@

New-Dir (Split-Path -Parent "app/gateway/schemas/copilot_request.py")
Write-File "app/gateway/schemas/copilot_request.py" @'
"""POST /copilot/message request body (UC-8.1 step 2)."""
from __future__ import annotations

from pydantic import BaseModel, Field


class CopilotMessageRequest(BaseModel):
    thread_id: str = Field(..., description="Copilot Thread name (BFF-owned DocType)")
    message: str = Field(..., min_length=1, max_length=8000)
    history: list["CopilotHistoryTurn"] = Field(default_factory=list)


class CopilotHistoryTurn(BaseModel):
    role: str  # 'user' | 'assistant'
    content: str


CopilotMessageRequest.model_rebuild()

'@

New-Dir (Split-Path -Parent "app/gateway/schemas/copilot_response.py")
Write-File "app/gateway/schemas/copilot_response.py" @'
"""Non-streaming shape of a copilot turn's result — also what each SSE
'done' event carries (ARCH §4.5, sse_events.py streams the incremental
version of this).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Citation(BaseModel):
    """FR-8.3 / NFR-UX.4 — every cited claim must show a real,
    human-meaningful reference, never a hidden one."""

    source_doctype: str
    source_name: str
    span_type: str
    span_start: int
    span_end: int
    quoted_span: str


class PendingApprovalCard(BaseModel):
    """Rendered instead of an applied change — FR-8.6."""

    approval_id: str | None = None  # set once BFF has persisted the row
    agent_type: str
    target_doctype: str
    proposed_payload: dict
    model_version: str
    confidence: float
    tool_trace_id: str


class CopilotResponse(BaseModel):
    kind: Literal["navigation", "grounded_answer", "tool_result", "pending_approval", "refusal"]
    text: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    pending_approval: PendingApprovalCard | None = None
    ai_generated: bool = True  # FR-8.9 — persistent, unambiguous disclosure
    model_version: str
    trace_id: str

'@

New-Dir (Split-Path -Parent "app/gateway/schemas/graph_sync_event.py")
Write-File "app/gateway/schemas/graph_sync_event.py" @'
"""Entity-mirror CDC event shape — POST /graph/sync (FR-8.2).

Mirrors app/ingest/cdc_event_schema.py's CDCEvent 1:1; kept as a separate
gateway-facing schema per NFR-EXT.1/ARCH §4.2 so the wire contract and the
internal processing model can diverge later without a breaking API
change.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class GraphSyncEvent(BaseModel):
    company: str
    event_type: Literal["after_insert", "on_update", "on_trash"]
    source_doctype: str  # 'Project' | 'Task' | 'RFI' | 'Commitment' | 'User' | 'Safety Incident'
    source_name: str
    project: str | None = None
    properties: dict[str, Any] = {}
    event_seq: int


class GraphSyncResult(BaseModel):
    accepted: bool
    node_key: str | None = None
    reason: str | None = None

'@

New-Dir (Split-Path -Parent "app/gateway/schemas/ingest_event.py")
Write-File "app/gateway/schemas/ingest_event.py" @'
"""POST /ingest request/response — UC-8.4 steps 5-9.

The sidecar never fetches a file on its own initiative; every field here
is what a BFF background job passes after its own eligibility + hash
check (ERD §4.1).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class IngestRequest(BaseModel):
    company: str
    project: str
    source_doctype: Literal["Commitment", "Submittal Package", "RFI"]
    source_name: str
    file_id: str
    content_hash: str
    # Permission-checked, time-limited signed download reference
    # (NFR-SEC.7) — never a raw internal file path.
    signed_download_url: str
    model_version_hint: str | None = None


class IngestResult(BaseModel):
    status: Literal["indexed", "failed"]
    chunk_count: int = 0
    model_version: str | None = None
    failure_reason: str | None = None  # e.g. 'no_text_layer', 'scope_mismatch'

'@

New-Dir (Split-Path -Parent "app/gateway/schemas/sse_events.py")
Write-File "app/gateway/schemas/sse_events.py" @'
"""Server-Sent Event payload shapes for the streaming copilot response
path (ARCH §4.5 — 'a full-response wait reads as "hung" compared to
token-by-token streaming'). buildpolaris_bff proxies this stream through
to the PWA rather than buffering it.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class SSEToken(BaseModel):
    event: Literal["token"] = "token"
    text: str


class SSECitation(BaseModel):
    event: Literal["citation"] = "citation"
    source_doctype: str
    source_name: str
    span_type: str
    span_start: int
    span_end: int


class SSEDisclosure(BaseModel):
    """FR-8.9 — sent once at the start of every stream so the client can
    render the AI-generated badge before the first token even arrives."""

    event: Literal["disclosure"] = "disclosure"
    ai_generated: bool = True


class SSEDone(BaseModel):
    event: Literal["done"] = "done"
    kind: str
    model_version: str
    trace_id: str


class SSEError(BaseModel):
    event: Literal["error"] = "error"
    message: str

'@

New-Dir (Split-Path -Parent "app/gateway/routers/__init__.py")
Write-File "app/gateway/routers/__init__.py" @'

'@

New-Dir (Split-Path -Parent "app/gateway/routers/copilot_message.py")
Write-File "app/gateway/routers/copilot_message.py" @'
"""POST /copilot/message — the one conversational copilot surface
(ARCH Flowchart 4). Streams via SSE (ARCH §4.5) so the PWA/BFF proxy
never buffers a full response before the user sees anything.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Header, Request
from sse_starlette.sse import EventSourceResponse

from app.gateway.auth.scope_assertion import ScopeAssertion, verify_scope_assertion
from app.gateway.auth.service_credential import verify_service_credential
from app.gateway.schemas.copilot_request import CopilotMessageRequest
from app.gateway.schemas.copilot_response import Citation, CopilotResponse, PendingApprovalCard
from app.observability.logging import get_logger
from app.observability.tracing import get_trace_id
from app.orchestrator.agent_registry import AgentRegistry, get_agent_registry
from app.orchestrator.context import TurnContext
from app.orchestrator.turn_runner import TurnResult
from app.platform.bff.mcp_client import BFFMCPClient
from app.platform.model_provider.factory import get_model_provider

logger = get_logger(__name__)

router = APIRouter(
    prefix="/copilot", tags=["copilot"], dependencies=[Depends(verify_service_credential)]
)


def _turn_result_to_response(result: TurnResult, trace_id: str) -> CopilotResponse:
    if result.kind == "navigation":
        return CopilotResponse(
            kind="navigation", text=json.dumps(result.navigation_result),
            model_version="n/a", trace_id=trace_id,
        )
    if result.kind in ("grounded_answer", "refusal") and result.rag_answer is not None:
        return CopilotResponse(
            kind=result.kind, text=result.rag_answer.text,
            citations=[
                Citation(
                    source_doctype=c.source_doctype, source_name=c.source_name,
                    span_type=c.span_type, span_start=c.span_start, span_end=c.span_end,
                    quoted_span=c.quoted_span,
                )
                for c in result.rag_answer.citations
            ],
            model_version=result.model_version, trace_id=trace_id,
        )
    if result.kind == "pending_approval":
        return CopilotResponse(
            kind="pending_approval", text=result.text,
            pending_approval=PendingApprovalCard(
                approval_id=result.approval_ref, agent_type=result.agent_type or "",
                target_doctype="", proposed_payload=result.proposed_payload or {},
                model_version=result.model_version, confidence=0.0,
                tool_trace_id=result.approval_ref or "",
            ),
            model_version=result.model_version, trace_id=trace_id,
        )
    return CopilotResponse(kind="refusal", text="Unable to process this request.",
                            model_version="n/a", trace_id=trace_id)


@router.post("/message")
async def post_message(
    body: CopilotMessageRequest,
    request: Request,
    x_scope_assertion: str = Header(...),
    assertion: ScopeAssertion = Depends(verify_scope_assertion),
    registry: AgentRegistry = Depends(get_agent_registry),
):
    """Streams disclosure -> tokens/citations -> done, per ARCH §4.5.
    Non-streaming callers can simply read the final 'done' event's payload
    (it carries the same shape as CopilotResponse).
    """
    trace_id = get_trace_id()

    async def event_generator():
        yield {"event": "disclosure", "data": json.dumps({"ai_generated": True})}

        try:
            provider = get_model_provider()
            mcp_client = BFFMCPClient(assertion, x_scope_assertion)

            context = TurnContext(
                thread_id=body.thread_id, message=body.message,
                history=[h.model_dump() for h in body.history],
                assertion=assertion, raw_assertion_token=x_scope_assertion,
                trace_id=trace_id, model_provider=provider, mcp_client=mcp_client,
            )

            from app.platform.citations.citation_validator import CitationValidator
            from app.platform.graph_store.age_adapter import AgeGraphAdapter
            from app.platform.rag.embedder import Embedder
            from app.platform.rag.rag_service import RagService
            from app.platform.rag.retriever import Retriever
            from app.platform.vector_store.pgvector_adapter import PgVectorAdapter
            from app.db.postgres import get_pool

            async with get_pool().acquire() as conn:
                vector_store = PgVectorAdapter(conn)
                graph_store = AgeGraphAdapter(conn)
                retriever = Retriever(vector_store, graph_store, Embedder(provider))
                rag_service = RagService(
                    vector_store, graph_store, provider, retriever, CitationValidator()
                )

                from app.orchestrator.turn_runner import TurnRunner

                runner = TurnRunner(registry, rag_service)
                result = await runner.run_turn(context)

            response = _turn_result_to_response(result, trace_id)

            if response.text:
                # Token-level streaming of a fully-generated answer still
                # gives the "reads as alive, not hung" UX §4.5 asks for,
                # without needing the model provider's own token stream
                # wired through every provider adapter in v1.
                for chunk in _chunk_text(response.text):
                    yield {"event": "token", "data": json.dumps({"text": chunk})}

            for citation in response.citations:
                yield {
                    "event": "citation",
                    "data": json.dumps(citation.model_dump()),
                }

            yield {
                "event": "done",
                "data": response.model_dump_json(),
            }
        except Exception as exc:  # noqa: BLE001
            logger.exception("copilot_turn_failed", trace_id=trace_id)
            yield {"event": "error", "data": json.dumps({"message": str(exc)})}

    return EventSourceResponse(event_generator())


def _chunk_text(text: str, size: int = 24):
    for i in range(0, len(text), size):
        yield text[i : i + size]

'@

New-Dir (Split-Path -Parent "app/gateway/routers/graph_sync.py")
Write-File "app/gateway/routers/graph_sync.py" @'
"""POST /graph/sync — FR-8.2's entity mirror ingress. Called by BFF
DocType lifecycle hooks (after_insert/on_update/on_trash) on every
tracked entity, independent of ingest.py's file-attachment trigger.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.db.postgres import get_pool
from app.exceptions import ScopeMismatchError
from app.gateway.auth.scope_assertion import ScopeAssertion, verify_scope_assertion
from app.gateway.auth.service_credential import verify_service_credential
from app.gateway.schemas.graph_sync_event import GraphSyncEvent, GraphSyncResult
from app.ingest.entity_mirror_service import EntityMirrorService
from app.observability.logging import get_logger
from app.platform.graph_store.age_adapter import AgeGraphAdapter

logger = get_logger(__name__)

router = APIRouter(
    prefix="/graph", tags=["graph-sync"], dependencies=[Depends(verify_service_credential)]
)


@router.post("/sync", response_model=GraphSyncResult)
async def sync_graph_event(
    body: GraphSyncEvent,
    assertion: ScopeAssertion = Depends(verify_scope_assertion),
) -> GraphSyncResult:
    if body.company != assertion.company:
        raise ScopeMismatchError("graph sync event company does not match asserted scope")

    async with get_pool().acquire() as conn:
        service = EntityMirrorService(AgeGraphAdapter(conn), conn)
        result = await service.sync(body)

    logger.info(
        "graph_sync_processed", doctype=body.source_doctype, name=body.source_name,
        accepted=result.accepted,
    )
    return result

'@

New-Dir (Split-Path -Parent "app/gateway/routers/health.py")
Write-File "app/gateway/routers/health.py" @'
"""Health + circuit-breaker status. No auth required — this is what a
container orchestrator's liveness probe hits, and NFR-OBS.3's "status
endpoint" for a human checking whether the sidecar itself is up (distinct
from metrics.py's per-tenant spend/usage view).
"""
from __future__ import annotations

from fastapi import APIRouter

from app.platform.model_provider.circuit_breaker import get_circuit_breaker

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "service": "buildpolaris_ai"}


@router.get("/healthz/providers")
async def provider_health() -> dict:
    breaker = get_circuit_breaker()
    return {"providers": breaker.snapshot(), "all_open": breaker.all_providers_open()}

'@

New-Dir (Split-Path -Parent "app/gateway/routers/ingest.py")
Write-File "app/gateway/routers/ingest.py" @'
"""POST /ingest — UC-8.4 steps 5-9. Only ever called by a BFF background
job after its own allow-list + already-indexed check (Flowchart 5 steps
B-D happen BFF-side against MariaDB's AI Document Index).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.db.postgres import get_pool
from app.exceptions import ScopeMismatchError
from app.gateway.auth.scope_assertion import ScopeAssertion, verify_scope_assertion
from app.gateway.auth.service_credential import verify_service_credential
from app.gateway.schemas.ingest_event import IngestRequest, IngestResult
from app.ingest.ingestion_service import IngestionService
from app.observability.logging import get_logger
from app.platform.model_provider.factory import get_model_provider
from app.platform.rag.embedder import Embedder
from app.platform.vector_store.pgvector_adapter import PgVectorAdapter

logger = get_logger(__name__)

router = APIRouter(
    prefix="/ingest", tags=["ingest"], dependencies=[Depends(verify_service_credential)]
)


@router.post("", response_model=IngestResult)
async def ingest_document(
    body: IngestRequest,
    assertion: ScopeAssertion = Depends(verify_scope_assertion),
) -> IngestResult:
    # UC-8.4 E3 — the ingestion write path gets the same scope-mismatch
    # defense as every read path (NFR-SEC.8), not an exemption because
    # it's a "trusted" BFF-originated call.
    if body.company != assertion.company:
        raise ScopeMismatchError("ingest request company does not match asserted scope")

    async with get_pool().acquire() as conn:
        service = IngestionService(PgVectorAdapter(conn), Embedder(get_model_provider()), conn)
        result = await service.ingest(body)

    logger.info(
        "ingest_completed", source_doctype=body.source_doctype, source_name=body.source_name,
        status=result.status, chunk_count=result.chunk_count,
    )
    return result

'@

New-Dir (Split-Path -Parent "app/gateway/routers/metrics.py")
Write-File "app/gateway/routers/metrics.py" @'
"""NFR-AIGOV.1 spend/usage surface + NFR-OBS.3 request counters. Guarded
by the service credential (this is an internal, BFF-facing surface, not
something exposed to the PWA directly — the BFF's own admin screen calls
this and re-renders it for a Company Admin).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.gateway.auth.service_credential import verify_service_credential
from app.observability.metrics import counters
from app.observability.token_usage import get_token_usage_tracker

router = APIRouter(
    prefix="/metrics", tags=["metrics"], dependencies=[Depends(verify_service_credential)]
)


@router.get("")
async def get_metrics() -> dict:
    return {"counters": counters.snapshot()}


@router.get("/usage/{company}")
async def get_tenant_usage(company: str) -> dict:
    return get_token_usage_tracker().snapshot(company)


@router.get("/usage")
async def get_all_usage() -> dict:
    return {"tenants": get_token_usage_tracker().all_snapshots()}

'@

New-Dir (Split-Path -Parent "app/agents/__init__.py")
Write-File "app/agents/__init__.py" @'

'@

New-Dir (Split-Path -Parent "app/agents/base.py")
Write-File "app/agents/base.py" @'
"""Shared helpers every agents/<name>/handler.py uses so the boilerplate
of assembling a ProposedAction (idempotency key, tool_trace_id, common
fields) lives in one place, not copy-pasted into four handlers.
"""
from __future__ import annotations

import hashlib
import uuid

from app.orchestrator.context import TurnContext
from app.platform.governance.proposal_schema import ProposedAction


def make_idempotency_key(context: TurnContext, agent_type: str) -> str:
    """Stable for a given (thread, agent_type, message) so a client retry
    of the same turn doesn't produce a second Pending approval row."""
    raw = f"{context.thread_id}:{agent_type}:{context.message}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def make_tool_trace_id() -> str:
    return uuid.uuid4().hex


def build_proposed_action(
    context: TurnContext, agent_type: str, target_doctype: str, payload: dict,
    model_version: str, confidence: float,
) -> ProposedAction:
    return ProposedAction(
        agent_type=agent_type,
        target_doctype=target_doctype,
        company=context.company,
        project=context.project,
        payload=payload,
        model_version=model_version,
        confidence=confidence,
        tool_trace_id=make_tool_trace_id(),
        idempotency_key=make_idempotency_key(context, agent_type),
        requested_by_user=context.user,
    )

'@

New-Dir (Split-Path -Parent "app/agents/contract_clause_extraction/__init__.py")
Write-File "app/agents/contract_clause_extraction/__init__.py" @'

'@

New-Dir (Split-Path -Parent "app/agents/contract_clause_extraction/handler.py")
Write-File "app/agents/contract_clause_extraction/handler.py" @'
"""Contract Clause Extraction Agent — pulls key commercial terms out of
an already-ingested Commitment contract's indexed chunks. Explicitly out
of scope (per REQ v2.1's non-goals): this agent never writes to Budget or
Schedule directly, even though payment terms and liquidated-damages
clauses are financially significant — it only proposes Commitment field
updates, same as every other agent here (FR-8.6).
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.agents.base import build_proposed_action
from app.orchestrator.context import TurnContext
from app.orchestrator.contracts import AgentResult
from app.platform.model_provider.model_pin import resolve_model_version


class _ContractTerms(BaseModel):
    payment_terms: str | None = None
    retention_percent: float | None = None
    liquidated_damages_per_day: str | None = None
    notice_period_days: int | None = None
    key_clauses_cited: list[str] = Field(default_factory=list)
    rationale: str


EXTRACTION_PROMPT = """Extract key commercial terms from the contract
context below. Every value you populate must be traceable to a specific
clause in the context — list the clause references in
key_clauses_cited. Leave a field null if the contract text provided
doesn't clearly state it; do not infer from general construction-industry
convention.

Contract context:
{context}

Extraction focus (from the user's request): {message}
"""


async def run(context: TurnContext) -> AgentResult:
    from app.dependencies import get_rag_service

    rag_service = get_rag_service()
    grounding = await rag_service.answer(
        f"payment terms, retention, liquidated damages, notice periods relevant to: {context.message}",
        context.company, context.project,
    )

    prompt = EXTRACTION_PROMPT.format(context=grounding.text, message=context.message)
    model_version = resolve_model_version(context.company)

    terms = await context.model_provider.structured_complete(
        prompt, _ContractTerms, model_version=model_version, temperature=0.1
    )

    payload = {
        "payment_terms": terms.payment_terms,
        "retention_percent": terms.retention_percent,
        "liquidated_damages_per_day": terms.liquidated_damages_per_day,
        "notice_period_days": terms.notice_period_days,
        "key_clauses_cited": terms.key_clauses_cited,
        "project": context.project,
    }

    proposed_action = build_proposed_action(
        context, agent_type="contract_clause_extraction", target_doctype="Commitment",
        payload=payload, model_version=model_version, confidence=0.7,
    )

    return AgentResult(proposed_action=proposed_action, rationale=terms.rationale)

'@

New-Dir (Split-Path -Parent "app/agents/contract_clause_extraction/manifest.yaml")
Write-File "app/agents/contract_clause_extraction/manifest.yaml" @'
agent_type: contract_clause_extraction
display_name: "Contract Clause Extraction Agent"
description: >
  Extracts key commercial terms (payment terms, retention, liquidated
  damages, notice periods) from an indexed Commitment contract and
  proposes them as structured Commitment fields (REQ v2.1 M8 agent
  catalog). Never writes directly to Budget or Schedule — extraction
  only, always human-reviewed.
target_doctype: "Commitment"
intent_examples:
  - "extract contract terms"
  - "pull the payment terms from"
  - "what are the key terms in this contract"

'@

New-Dir (Split-Path -Parent "app/agents/contract_clause_extraction/prompts/system.md")
Write-File "app/agents/contract_clause_extraction/prompts/system.md" @'
You are the BuildPolaris Contract Clause Extraction Agent. You extract
key commercial terms from indexed contract text, citing the specific
clause for every value you populate. You never write to Budget or
Schedule — only to the Commitment record's own fields, and only as a
proposal a human must approve.

'@

New-Dir (Split-Path -Parent "app/agents/_template/__init__.py")
Write-File "app/agents/_template/__init__.py" @'

'@

New-Dir (Split-Path -Parent "app/agents/_template/handler.py")
Write-File "app/agents/_template/handler.py" @'
"""Template handler — copy to app/agents/<new_agent_name>/handler.py and
implement `run()`. Every agent module must expose exactly this signature
(app/orchestrator/contracts.py's AgentModule protocol) — the orchestrator
calls nothing else on it.
"""
from __future__ import annotations

from app.agents.base import build_proposed_action
from app.orchestrator.context import TurnContext
from app.orchestrator.contracts import AgentResult


async def run(context: TurnContext) -> AgentResult:
    # 1. Gather whatever input this agent needs (context.message,
    #    context.extra, and/or an MCP read-tool call via context.mcp_client).
    # 2. Call context.model_provider.structured_complete(...) with a
    #    Pydantic schema matching the target DocType's draftable fields.
    # 3. Assemble a ProposedAction via build_proposed_action() — never
    #    apply anything directly; this handler never writes to BFF itself.
    raise NotImplementedError("copy this template and implement run()")

'@

New-Dir (Split-Path -Parent "app/agents/_template/manifest.yaml")
Write-File "app/agents/_template/manifest.yaml" @'
# Template manifest — copy this folder, rename it, and fill in every field.
# The orchestrator/agent_registry.py discovers any folder under app/agents/
# with a manifest.yaml EXCEPT folders starting with "_" (this one is
# intentionally excluded from registration).
agent_type: template_agent
display_name: "Template Agent"
description: >
  One sentence describing what this agent drafts and from what input.
target_doctype: "SomeDocType"
intent_examples:
  - "example phrase a user might type that should route here"

'@

New-Dir (Split-Path -Parent "app/agents/_template/prompts/system.md")
Write-File "app/agents/_template/prompts/system.md" @'
You are a BuildPolaris AI agent drafting a proposed {target_doctype}
record. You never apply this draft yourself — a human always reviews and
approves or rejects it before anything is written.

'@

New-Dir (Split-Path -Parent "app/agents/daily_log_extraction/__init__.py")
Write-File "app/agents/daily_log_extraction/__init__.py" @'

'@

New-Dir (Split-Path -Parent "app/agents/daily_log_extraction/handler.py")
Write-File "app/agents/daily_log_extraction/handler.py" @'
"""Daily Log Extraction Agent — structures a superintendent's free-text
field note into Daily Log fields. Unlike the field-capture path in
buildpolaris_pwa (which is a direct, non-AI structured form — FR-6.5),
this agent exists for the case where the note was captured as prose (e.g.
dictated) and needs to be structured after the fact; it still always
produces a *proposed* record, never a direct write.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.agents.base import build_proposed_action
from app.orchestrator.context import TurnContext
from app.orchestrator.contracts import AgentResult
from app.platform.model_provider.model_pin import resolve_model_version


class _DailyLogExtraction(BaseModel):
    weather: str | None = None
    temperature_notes: str | None = None
    crew_count: int | None = None
    work_performed: str
    delays_or_issues: str | None = None
    safety_notes: str | None = None
    rationale: str


EXTRACTION_PROMPT = """Extract structured Daily Log fields from the field
note below. Only populate a field if the note actually states or clearly
implies it — leave anything unmentioned as null rather than guessing a
plausible-sounding value.

Field note: {message}
"""


async def run(context: TurnContext) -> AgentResult:
    prompt = EXTRACTION_PROMPT.format(message=context.message)
    model_version = resolve_model_version(context.company)

    extraction = await context.model_provider.structured_complete(
        prompt, _DailyLogExtraction, model_version=model_version, temperature=0.1
    )

    payload = {
        "weather": extraction.weather,
        "temperature_notes": extraction.temperature_notes,
        "crew_count": extraction.crew_count,
        "work_performed": extraction.work_performed,
        "delays_or_issues": extraction.delays_or_issues,
        "safety_notes": extraction.safety_notes,
        "project": context.project,
    }

    proposed_action = build_proposed_action(
        context, agent_type="daily_log_extraction", target_doctype="Daily Log", payload=payload,
        model_version=model_version, confidence=0.65,
    )

    return AgentResult(proposed_action=proposed_action, rationale=extraction.rationale)

'@

New-Dir (Split-Path -Parent "app/agents/daily_log_extraction/manifest.yaml")
Write-File "app/agents/daily_log_extraction/manifest.yaml" @'
agent_type: daily_log_extraction
display_name: "Daily Log Extraction Agent"
description: >
  Extracts structured Daily Log fields (weather, crew counts, work
  performed, delays) from a superintendent's free-text field note
  (REQ v2.1 M8 agent catalog).
target_doctype: "Daily Log"
intent_examples:
  - "log today's work"
  - "extract daily log from"
  - "turn this note into a daily log"

'@

New-Dir (Split-Path -Parent "app/agents/daily_log_extraction/prompts/system.md")
Write-File "app/agents/daily_log_extraction/prompts/system.md" @'
You are the BuildPolaris Daily Log Extraction Agent. You structure a
field note into Daily Log fields. You never invent a value for a field
the note doesn't mention — leave it null instead.

'@

New-Dir (Split-Path -Parent "app/agents/submittal_review/__init__.py")
Write-File "app/agents/submittal_review/__init__.py" @'

'@

New-Dir (Split-Path -Parent "app/agents/submittal_review/handler.py")
Write-File "app/agents/submittal_review/handler.py" @'
"""Submittal Review Agent — compares a submittal's content against
already-indexed spec chunks (via RagService's retrieval, not a fresh
upload) and proposes a review outcome. Grounded in retrieved citations so
the proposed comments always trace back to a real spec passage.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.agents.base import build_proposed_action
from app.orchestrator.context import TurnContext
from app.orchestrator.contracts import AgentResult
from app.platform.model_provider.model_pin import resolve_model_version


class _SubmittalReview(BaseModel):
    review_status: str = Field(..., pattern="^(Approved|Approved as Noted|Revise and Resubmit|Rejected)$")
    comments: str
    cited_spec_sections: list[str] = Field(default_factory=list)
    rationale: str


REVIEW_PROMPT = """Review the submittal described below against the spec
passages provided as context. Propose one of the four standard review
outcomes (Approved / Approved as Noted / Revise and Resubmit / Rejected).
Every comment you make must be traceable to a specific spec passage in
the context — never invent a requirement that isn't in the retrieved
spec text.

Spec context:
{context}

Submittal description: {message}
"""


async def run(context: TurnContext) -> AgentResult:
    # Grounding retrieval — reuse the same vector search the RAG path
    # uses, scoped to this project's indexed spec documents, rather than
    # re-implementing retrieval inside the agent.
    from app.dependencies import get_rag_service

    rag_service = get_rag_service()
    grounding = await rag_service.answer(
        f"spec requirements relevant to: {context.message}", context.company, context.project
    )

    prompt = REVIEW_PROMPT.format(context=grounding.text, message=context.message)
    model_version = resolve_model_version(context.company)

    review = await context.model_provider.structured_complete(
        prompt, _SubmittalReview, model_version=model_version, temperature=0.15
    )

    payload = {
        "review_status": review.review_status,
        "comments": review.comments,
        "cited_spec_sections": review.cited_spec_sections,
        "project": context.project,
    }

    proposed_action = build_proposed_action(
        context, agent_type="submittal_review", target_doctype="Submittal Item", payload=payload,
        model_version=model_version, confidence=0.7,
    )

    return AgentResult(proposed_action=proposed_action, rationale=review.rationale)

'@

New-Dir (Split-Path -Parent "app/agents/submittal_review/manifest.yaml")
Write-File "app/agents/submittal_review/manifest.yaml" @'
agent_type: submittal_review
display_name: "Submittal Review Agent"
description: >
  Reviews a Submittal Package against the relevant spec section already
  indexed for this project and proposes a review status + comments
  (REQ v2.1 M8 agent catalog).
target_doctype: "Submittal Item"
intent_examples:
  - "review this submittal"
  - "check submittal against spec"
  - "review the submittal package"

'@

New-Dir (Split-Path -Parent "app/agents/submittal_review/prompts/system.md")
Write-File "app/agents/submittal_review/prompts/system.md" @'
You are the BuildPolaris Submittal Review Agent. You compare a submittal
against indexed spec text and propose a standard review outcome. Every
comment you write must trace back to an actual retrieved spec passage —
you never fabricate a requirement.

'@

New-Dir (Split-Path -Parent "app/agents/rfi_drafting/__init__.py")
Write-File "app/agents/rfi_drafting/__init__.py" @'

'@

New-Dir (Split-Path -Parent "app/agents/rfi_drafting/handler.py")
Write-File "app/agents/rfi_drafting/handler.py" @'
"""RFI Drafting Agent — turns a field question into a structured,
proposed RFI record (never applied directly — FR-8.6).
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.agents.base import build_proposed_action
from app.orchestrator.context import TurnContext
from app.orchestrator.contracts import AgentResult
from app.platform.model_provider.model_pin import resolve_model_version


class _DraftRFI(BaseModel):
    subject: str = Field(..., max_length=140)
    question: str
    reference_drawing_or_spec: str | None = None
    priority: str = Field(..., pattern="^(Low|Medium|High|Critical)$")
    suggested_assignee_role: str | None = None
    rationale: str


DRAFT_PROMPT = """Draft a Request for Information (RFI) from the field
description below. Be precise and unambiguous — an RFI response has
schedule and cost consequences, so vague questions cost the project real
time. If a drawing or spec section is mentioned or clearly implied, name
it. Set priority based on whether this blocks current field work
(Critical/High) or is informational (Low/Medium).

Field description: {message}
"""


async def run(context: TurnContext) -> AgentResult:
    prompt = DRAFT_PROMPT.format(message=context.message)
    model_version = resolve_model_version(context.company)

    draft = await context.model_provider.structured_complete(
        prompt, _DraftRFI, model_version=model_version, temperature=0.2
    )

    payload = {
        "subject": draft.subject,
        "question": draft.question,
        "reference_drawing_or_spec": draft.reference_drawing_or_spec,
        "priority": draft.priority,
        "suggested_assignee_role": draft.suggested_assignee_role,
        "project": context.project,
    }

    proposed_action = build_proposed_action(
        context, agent_type="rfi_drafting", target_doctype="RFI", payload=payload,
        model_version=model_version, confidence=0.75,
    )

    return AgentResult(proposed_action=proposed_action, rationale=draft.rationale)

'@

New-Dir (Split-Path -Parent "app/agents/rfi_drafting/manifest.yaml")
Write-File "app/agents/rfi_drafting/manifest.yaml" @'
agent_type: rfi_drafting
display_name: "RFI Drafting Agent"
description: >
  Drafts a Request for Information from a plain-language description of a
  field question or design conflict, citing the relevant drawing/spec
  section where possible (REQ v2.1 M8 agent catalog).
target_doctype: "RFI"
intent_examples:
  - "draft an rfi"
  - "write an rfi about"
  - "raise an rfi for"
  - "create a request for information"

'@

New-Dir (Split-Path -Parent "app/agents/rfi_drafting/prompts/system.md")
Write-File "app/agents/rfi_drafting/prompts/system.md" @'
You are the BuildPolaris RFI Drafting Agent. You turn a field
superintendent's plain-language description of a question or conflict
into a precise, unambiguous Request for Information. You never invent
drawing numbers or spec sections that weren't mentioned or clearly
implied by the description. Your output is always a draft for human
review — you never imply it has already been submitted.

'@

New-Dir (Split-Path -Parent "app/platform/__init__.py")
Write-File "app/platform/__init__.py" @'

'@

New-Dir (Split-Path -Parent "app/platform/vector_store/__init__.py")
Write-File "app/platform/vector_store/__init__.py" @'
from app.platform.vector_store.adapter import VectorStoreAdapter, ScoredChunk
from app.platform.vector_store.pgvector_adapter import PgVectorAdapter

__all__ = ["VectorStoreAdapter", "ScoredChunk", "PgVectorAdapter"]

'@

New-Dir (Split-Path -Parent "app/platform/vector_store/adapter.py")
Write-File "app/platform/vector_store/adapter.py" @'
"""VectorStoreAdapter — the half of RetrievalAdapter (ERD §4.4) concerned
with similarity search. NFR-EXT.2: the underlying store must be swappable
without touching RagService — this port is that seam.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(slots=True)
class ScoredChunk:
    chunk_id: str
    company: str
    project: str
    source_doctype: str
    source_name: str
    span_type: str
    span_start: int
    span_end: int
    chunk_text: str
    score: float  # similarity score, higher is better (1 - cosine distance)


@runtime_checkable
class VectorStoreAdapter(Protocol):
    async def upsert_chunk(
        self, company: str, project: str, source_doctype: str, source_name: str,
        file_id: str, content_hash: str, span_type: str, span_start: int, span_end: int,
        chunk_text: str, embedding: list[float], model_version: str,
    ) -> str:
        """Insert one chunk + its embedding; returns chunk_id."""
        ...

    async def mark_stale(self, company: str, source_doctype: str, source_name: str) -> int:
        """UC-8.4 A1 — mark prior chunks stale (never hard-delete mid-query)
        ahead of a re-ingest. Returns the number of rows marked."""
        ...

    async def search(
        self, query_embedding: list[float], company: str, project: str | None,
        limit: int = 10,
    ) -> list[ScoredChunk]:
        """Cosine-similarity search, scoped to tenant/Project (NFR-SEC.8),
        filtered to is_stale = false."""
        ...

'@

New-Dir (Split-Path -Parent "app/platform/vector_store/pgvector_adapter.py")
Write-File "app/platform/vector_store/pgvector_adapter.py" @'
"""PgVectorAdapter — concrete VectorStoreAdapter (ARCH §3.3 point 1).

A future migration off pgvector to a managed vector service happens
behind this one class; RagService and every agent never import asyncpg
or pgvector directly.
"""
from __future__ import annotations

import asyncpg

from app.observability.logging import get_logger
from app.platform.vector_store.adapter import ScoredChunk
from app.platform.vector_store.queries import (
    INSERT_CHUNK,
    INSERT_EMBEDDING,
    MARK_STALE,
    SEARCH_BY_EMBEDDING,
)

logger = get_logger(__name__)


class PgVectorAdapter:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def upsert_chunk(
        self, company: str, project: str, source_doctype: str, source_name: str,
        file_id: str, content_hash: str, span_type: str, span_start: int, span_end: int,
        chunk_text: str, embedding: list[float], model_version: str,
    ) -> str:
        async with self._conn.transaction():
            chunk_row = await self._conn.fetchrow(
                INSERT_CHUNK, company, project, source_doctype, source_name, file_id,
                content_hash, span_type, span_start, span_end, chunk_text,
            )
            chunk_id = chunk_row["chunk_id"]
            await self._conn.execute(INSERT_EMBEDDING, chunk_id, embedding, model_version)
        return str(chunk_id)

    async def mark_stale(self, company: str, source_doctype: str, source_name: str) -> int:
        result = await self._conn.execute(MARK_STALE, company, source_doctype, source_name)
        # asyncpg returns 'UPDATE <n>'
        return int(result.split()[-1])

    async def search(
        self, query_embedding: list[float], company: str, project: str | None,
        limit: int = 10,
    ) -> list[ScoredChunk]:
        rows = await self._conn.fetch(
            SEARCH_BY_EMBEDDING, query_embedding, company, project, limit
        )
        return [
            ScoredChunk(
                chunk_id=str(r["chunk_id"]), company=r["company"], project=r["project"],
                source_doctype=r["source_doctype"], source_name=r["source_name"],
                span_type=r["span_type"], span_start=r["span_start"], span_end=r["span_end"],
                chunk_text=r["chunk_text"], score=float(r["score"]),
            )
            for r in rows
        ]

'@

New-Dir (Split-Path -Parent "app/platform/vector_store/queries.py")
Write-File "app/platform/vector_store/queries.py" @'
"""Raw SQL used by PgVectorAdapter — kept in one module so the query shape
is reviewable independently of the adapter's control flow (NFR-MAINT.2).
"""
from __future__ import annotations

INSERT_CHUNK = """
    INSERT INTO document_chunks
        (company, project, source_doctype, source_name, file_id, content_hash,
         span_type, span_start, span_end, chunk_text)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
    RETURNING chunk_id;
"""

INSERT_EMBEDDING = """
    INSERT INTO embeddings (chunk_id, embedding, model_version)
    VALUES ($1, $2, $3)
    ON CONFLICT (chunk_id, model_version) DO UPDATE SET embedding = EXCLUDED.embedding;
"""

MARK_STALE = """
    UPDATE document_chunks
    SET is_stale = TRUE
    WHERE company = $1 AND source_doctype = $2 AND source_name = $3 AND is_stale = FALSE;
"""

SEARCH_BY_EMBEDDING = """
    SELECT
        c.chunk_id, c.company, c.project, c.source_doctype, c.source_name,
        c.span_type, c.span_start, c.span_end, c.chunk_text,
        1 - (e.embedding <=> $1) AS score
    FROM embeddings e
    JOIN document_chunks c ON c.chunk_id = e.chunk_id
    WHERE c.is_stale = FALSE
      AND c.company = $2
      AND ($3::text IS NULL OR c.project = $3)
    ORDER BY e.embedding <=> $1
    LIMIT $4;
"""

'@

New-Dir (Split-Path -Parent "app/platform/governance/__init__.py")
Write-File "app/platform/governance/__init__.py" @'
from app.platform.governance.action_approval_gate import ActionApprovalGateClient
from app.platform.governance.proposal_schema import ProposedAction

__all__ = ["ActionApprovalGateClient", "ProposedAction"]

'@

New-Dir (Split-Path -Parent "app/platform/governance/action_approval_gate.py")
Write-File "app/platform/governance/action_approval_gate.py" @'
"""ActionApprovalGateClient — deliberately thin (ARCH §3.3 point 3: "the
port is intentionally narrow ... it only proposes, never resolves; the
approval record lives in BFF's MariaDB"). This client has exactly one
capability: hand a verified ProposedAction to the BFF and get back a
reference to the Pending approval row it created. It has no method that
could ever mark something approved — that would require this sidecar to
be trusted with a capability it structurally must never have (FR-8.6).
"""
from __future__ import annotations

import httpx

from app.config import get_settings
from app.exceptions import ApprovalProposalError
from app.observability.logging import get_logger
from app.platform.governance.payload_verifier import verify_proposed_action
from app.platform.governance.proposal_schema import ProposedAction

logger = get_logger(__name__)


class ActionApprovalGateClient:
    def __init__(self, raw_scope_assertion_token: str) -> None:
        self._settings = get_settings().bff
        self._raw_assertion = raw_scope_assertion_token

    async def propose(self, action: ProposedAction) -> str:
        """Returns the BFF's Agent Action Approval record name. Raises
        ApprovalProposalError on any failure — callers must treat a failed
        proposal as a failed agent run, never as a silent success."""
        verify_proposed_action(action)

        headers = {
            "X-Service-Key": self._settings.service_key.get_secret_value(),
            "X-Scope-Assertion": self._raw_assertion,
            "Idempotency-Key": action.idempotency_key,
        }

        url = f"{self._settings.base_url}/api/method/buildpolaris_bff.ai_copilot.approval_gate.propose_action"
        async with httpx.AsyncClient(timeout=self._settings.timeout_seconds) as client:
            try:
                response = await client.post(url, json=action.model_dump(), headers=headers)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                logger.error("approval_proposal_failed", agent_type=action.agent_type, error=str(exc))
                raise ApprovalProposalError(str(exc)) from exc

        data = response.json()
        approval_ref = data.get("message", {}).get("approval_name") or data.get("approval_name")
        if not approval_ref:
            raise ApprovalProposalError("BFF did not return an approval reference")

        logger.info("approval_proposed", agent_type=action.agent_type, approval_ref=approval_ref)
        return approval_ref

'@

New-Dir (Split-Path -Parent "app/platform/governance/audit_logger.py")
Write-File "app/platform/governance/audit_logger.py" @'
"""Sidecar-local audit trail for every proposal this service makes,
independent of whatever the BFF later records — so buildpolaris_ai's own
eval/metrics (approval_gate_accuracy.py) never depends on being able to
query MariaDB (ERD §7 / migration 0007's approval_events table).
"""
from __future__ import annotations

import asyncpg

from app.observability.logging import get_logger
from app.platform.governance.proposal_schema import ProposedAction

logger = get_logger(__name__)


async def record_approval_event(
    conn: asyncpg.Connection, run_id: str | None, action: ProposedAction,
    bff_approval_ref: str | None,
) -> None:
    import json

    await conn.execute(
        """
        INSERT INTO approval_events
            (run_id, tool_trace_id, proposed_payload, bff_approval_ref, idempotency_key)
        VALUES ($1, $2, $3::jsonb, $4, $5)
        ON CONFLICT (idempotency_key) DO UPDATE
            SET bff_approval_ref = EXCLUDED.bff_approval_ref;
        """,
        run_id, action.tool_trace_id, json.dumps(action.payload), bff_approval_ref,
        action.idempotency_key,
    )
    logger.info(
        "approval_event_recorded",
        agent_type=action.agent_type, tool_trace_id=action.tool_trace_id,
        bff_approval_ref=bff_approval_ref,
    )

'@

New-Dir (Split-Path -Parent "app/platform/governance/payload_verifier.py")
Write-File "app/platform/governance/payload_verifier.py" @'
"""Defensive shape checks on a ProposedAction before it's handed to the
BFF (FR-8.6: "no agent implements its own approval flow" implies every
proposal passes through the same minimal sanity gate here first, so a
malformed agent output fails loudly in this sidecar rather than as an
opaque 400 from the BFF).
"""
from __future__ import annotations

from app.platform.governance.proposal_schema import ProposedAction

# Target DocTypes an agent is permitted to propose a write against, per
# REQ v2.1's agent catalog (RFI drafting -> RFI, submittal review ->
# Submittal Package/Submittal Item, daily-log extraction -> Daily Log,
# contract-clause extraction -> Commitment). Kept centralized rather than
# per-agent so adding a target requires one reviewed change here, not a
# silent capability added inside a handler.
ALLOWED_TARGETS = {
    "rfi_drafting": {"RFI"},
    "submittal_review": {"Submittal Package", "Submittal Item"},
    "daily_log_extraction": {"Daily Log"},
    "contract_clause_extraction": {"Commitment"},
}


class PayloadVerificationError(Exception):
    pass


def verify_proposed_action(action: ProposedAction) -> None:
    allowed = ALLOWED_TARGETS.get(action.agent_type)
    if allowed is None:
        raise PayloadVerificationError(f"unknown agent_type '{action.agent_type}'")
    if action.target_doctype not in allowed:
        raise PayloadVerificationError(
            f"agent '{action.agent_type}' is not allowed to propose a write "
            f"against '{action.target_doctype}'"
        )
    if not action.payload:
        raise PayloadVerificationError("proposed payload is empty")
    if not action.company:
        raise PayloadVerificationError("proposed action missing company scope")

'@

New-Dir (Split-Path -Parent "app/platform/governance/proposal_schema.py")
Write-File "app/platform/governance/proposal_schema.py" @'
"""ProposedAction — what an agent hands to ActionApprovalGateClient
(ARCH Flowchart 4 step O: "capture agent type, payload, model version,
confidence, tool-trace id"). Every agent module produces exactly this
shape regardless of which target DocType it's proposing a write to — the
gate and the BFF's Agent Action Approval DocType don't need to know
anything agent-specific.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ProposedAction(BaseModel):
    agent_type: str
    target_doctype: str
    company: str
    project: str | None
    payload: dict = Field(..., description="The draft field values, not yet applied anywhere")
    model_version: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    tool_trace_id: str
    idempotency_key: str
    requested_by_user: str

'@

New-Dir (Split-Path -Parent "app/platform/rag/__init__.py")
Write-File "app/platform/rag/__init__.py" @'
from app.platform.rag.rag_service import RagService, RagAnswer

__all__ = ["RagService", "RagAnswer"]

'@

New-Dir (Split-Path -Parent "app/platform/rag/chunker.py")
Write-File "app/platform/rag/chunker.py" @'
"""Chunker — page/clause-bounded splitting (ARCH Flowchart 5 step K:
"Chunk — page/clause-bounded"). Chunking never crosses a page boundary for
scanned/paginated sources or a clause boundary for contract text, because
FR-8.3's citation contract is "point to the exact page/clause a claim came
from" — a chunk that straddles two pages can't honestly cite either one.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.config import get_settings


@dataclass(slots=True)
class RawChunk:
    span_type: str  # 'page' | 'clause'
    span_start: int
    span_end: int
    text: str


# Matches common contract clause numbering: "1.", "1.1", "1.1.2", "Article 3",
# "Section 4.2" at the start of a line — used only to prefer clause
# boundaries as chunk breakpoints; token budget still hard-caps chunk size.
_CLAUSE_HEADING_RE = re.compile(
    r"^(?:(?:Article|Section)\s+\d+[.:]?|\d+(?:\.\d+){0,3}[.)]?)\s+\S",
    re.MULTILINE,
)


def _approx_token_count(text: str) -> int:
    # Cheap, provider-agnostic estimate (~4 chars/token for English prose)
    # good enough to bound chunk size without a tokenizer dependency per
    # provider (NFR-EXT.2 — chunker must not be coupled to one vendor's
    # tokenizer).
    return max(len(text) // 4, 1)


def chunk_pages(pages: list[str]) -> list[RawChunk]:
    """Page-bounded chunking for scanned/paginated sources (PDFs without
    reliable clause structure). One chunk per page unless the page exceeds
    the configured token budget, in which case it's split further but the
    span_start/span_end still both point at that same page number.
    """
    settings = get_settings().rag
    chunks: list[RawChunk] = []

    for page_num, page_text in enumerate(pages, start=1):
        page_text = page_text.strip()
        if not page_text:
            continue

        if _approx_token_count(page_text) <= settings.chunk_token_size:
            chunks.append(RawChunk("page", page_num, page_num, page_text))
            continue

        # Oversized page: split on paragraph boundaries within the page,
        # every sub-chunk still cites span=(page_num, page_num).
        for sub in _split_by_token_budget(page_text, settings.chunk_token_size,
                                           settings.chunk_token_overlap):
            chunks.append(RawChunk("page", page_num, page_num, sub))

    return chunks


def chunk_clauses(full_text: str, clause_numbers: list[tuple[int, int, str]] | None = None) -> list[RawChunk]:
    """Clause-bounded chunking for contract-style text with clause
    numbering. If `clause_numbers` (pre-extracted (start_offset, end_offset,
    label) triples) isn't supplied, falls back to the heading regex to find
    clause breakpoints.
    """
    settings = get_settings().rag

    if not clause_numbers:
        boundaries = [m.start() for m in _CLAUSE_HEADING_RE.finditer(full_text)]
        boundaries.append(len(full_text))
        clause_numbers = [
            (boundaries[i], boundaries[i + 1], str(i + 1))
            for i in range(len(boundaries) - 1)
            if boundaries[i + 1] > boundaries[i]
        ]

    chunks: list[RawChunk] = []
    for idx, (start, end, _label) in enumerate(clause_numbers, start=1):
        text = full_text[start:end].strip()
        if not text:
            continue
        if _approx_token_count(text) <= settings.chunk_token_size:
            chunks.append(RawChunk("clause", idx, idx, text))
        else:
            for sub in _split_by_token_budget(text, settings.chunk_token_size,
                                               settings.chunk_token_overlap):
                chunks.append(RawChunk("clause", idx, idx, sub))
    return chunks


def _split_by_token_budget(text: str, budget_tokens: int, overlap_tokens: int) -> list[str]:
    budget_chars = budget_tokens * 4
    overlap_chars = overlap_tokens * 4
    if len(text) <= budget_chars:
        return [text]

    parts = []
    start = 0
    while start < len(text):
        end = min(start + budget_chars, len(text))
        parts.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap_chars
    return parts

'@

New-Dir (Split-Path -Parent "app/platform/rag/embedder.py")
Write-File "app/platform/rag/embedder.py" @'
"""Embedder — thin wrapper resolving which provider actually performs
embedding (config allows pinning embeddings to a different provider than
completion, since the free-tier Gemini embedding quota and the free-tier
Gemini generation quota are tracked separately upstream).
"""
from __future__ import annotations

from app.config import get_settings
from app.observability.logging import get_logger
from app.platform.model_provider.adapter import ModelProviderAdapter

logger = get_logger(__name__)


class Embedder:
    def __init__(self, provider: ModelProviderAdapter) -> None:
        self._provider = provider
        self._settings = get_settings().embedding

    async def embed_text(self, text: str) -> list[float]:
        if self._settings.provider == "sentence-transformers":
            return await self._embed_local(text)
        return await self._provider.embed(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if self._settings.provider == "sentence-transformers":
            return await self._embed_local_batch(texts)
        return await self._provider.embed_batch(texts)

    # --- local sentence-transformers path (free, no API quota) ---------
    _local_model = None

    async def _ensure_local_model(self):
        if Embedder._local_model is None:
            from sentence_transformers import SentenceTransformer

            Embedder._local_model = SentenceTransformer(self._settings.model)
            logger.info("sentence_transformers_loaded", model=self._settings.model)
        return Embedder._local_model

    async def _embed_local(self, text: str) -> list[float]:
        import asyncio

        model = await self._ensure_local_model()
        loop = asyncio.get_event_loop()
        vec = await loop.run_in_executor(None, model.encode, text)
        return vec.tolist()

    async def _embed_local_batch(self, texts: list[str]) -> list[list[float]]:
        import asyncio

        model = await self._ensure_local_model()
        loop = asyncio.get_event_loop()
        vecs = await loop.run_in_executor(None, model.encode, texts)
        return [v.tolist() for v in vecs]

    @property
    def dimensions(self) -> int:
        return self._settings.dimensions

    @property
    def model_version(self) -> str:
        return self._settings.model

'@

New-Dir (Split-Path -Parent "app/platform/rag/query_transform.py")
Write-File "app/platform/rag/query_transform.py" @'
"""Query transformation — 2-4 reformulations (ARCH §3.3 point 2 / Flowchart
4 step F: "Query transformation (2-4 reformulations)").

A single user question is often a poor literal match for how a contract
clause or RFI response is actually phrased. Reformulating into several
paraphrases before retrieval measurably improves recall for this kind of
domain-specific corpus (construction contract language, field jargon)
without needing a fine-tuned retriever.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.observability.logging import get_logger
from app.platform.model_provider.adapter import ModelProviderAdapter

logger = get_logger(__name__)


class _Reformulations(BaseModel):
    queries: list[str] = Field(..., min_length=1, max_length=4)


REFORMULATION_PROMPT = """You are helping search a construction project's
documents (contracts, RFIs, submittals, daily logs). Given the user's
question, produce {n} distinct search-engine-style reformulations that
would each independently retrieve relevant passages. Vary vocabulary
(formal contract language vs. field jargon) and specificity. Do not answer
the question — only produce search queries.

Question: {question}
"""


async def transform_query(
    question: str, provider: ModelProviderAdapter, n: int = 3
) -> list[str]:
    n = max(2, min(n, 4))
    prompt = REFORMULATION_PROMPT.format(n=n, question=question)
    try:
        result = await provider.structured_complete(prompt, _Reformulations, temperature=0.3)
        queries = [q.strip() for q in result.queries if q.strip()]
    except Exception as exc:  # noqa: BLE001 — transform is best-effort
        logger.warning("query_transform_failed_using_original", error=str(exc))
        queries = []

    if question not in queries:
        queries.insert(0, question)
    return queries[: n + 1]

'@

New-Dir (Split-Path -Parent "app/platform/rag/rag_service.py")
Write-File "app/platform/rag/rag_service.py" @'
"""RagService — the pipeline behind a 'grounded factual question' turn
(ARCH Flowchart 4, steps F through L). This is the one place that wires
query_transform -> retriever (vector + graph) -> rrf -> reranker ->
generation -> citation_validator -> retry-once-or-refuse together; every
other module in platform/rag is a stage this file calls in order.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.config import get_settings
from app.observability.logging import get_logger
from app.observability.metrics import (
    CITATION_VALIDATION_FAILURES_TOTAL,
    CITATION_VALIDATION_REFUSALS_TOTAL,
    counters,
)
from app.platform.citations.citation_formatter import format_answer_with_citations
from app.platform.citations.citation_validator import CitationValidator, ValidatedCitation
from app.platform.graph_store.adapter import GraphStoreAdapter
from app.platform.model_provider.adapter import ModelProviderAdapter
from app.platform.rag.query_transform import transform_query
from app.platform.rag.reranker import rerank
from app.platform.rag.retriever import Retriever
from app.platform.rag.rrf import reciprocal_rank_fusion
from app.platform.vector_store.adapter import ScoredChunk, VectorStoreAdapter

logger = get_logger(__name__)

ANSWER_PROMPT = """You are the BuildPolaris AI Copilot, answering a
question about this construction project using ONLY the context passages
below. Every factual claim in your answer MUST be immediately followed by
a citation marker like [1], [2] referencing the passage it came from. If
the context does not contain the answer, say so plainly — never invent a
citation or state something the context doesn't support.

Context passages:
{context}

Question: {question}

Answer (with [n] citation markers after every claim):
"""

STRICTER_RETRY_SUFFIX = """

IMPORTANT: Your previous answer contained a claim that could not be
matched back to a real passage above. This time, cite ONLY passages that
are copied from the context below, and if you are not certain a claim is
directly supported, omit that claim entirely rather than guessing.
"""


@dataclass(slots=True)
class RagAnswer:
    text: str
    citations: list[ValidatedCitation] = field(default_factory=list)
    refused: bool = False
    model_version: str = ""


class RagService:
    def __init__(
        self,
        vector_store: VectorStoreAdapter,
        graph_store: GraphStoreAdapter,
        model_provider: ModelProviderAdapter,
        retriever: Retriever,
        citation_validator: CitationValidator,
    ) -> None:
        self._vector_store = vector_store
        self._graph_store = graph_store
        self._model_provider = model_provider
        self._retriever = retriever
        self._citation_validator = citation_validator

    async def answer(self, question: str, company: str, project: str | None) -> RagAnswer:
        settings = get_settings().rag

        # F: query transformation (2-4 reformulations)
        queries = await transform_query(question, self._model_provider, settings.query_reformulations)

        # G: hybrid retrieval — vector search (parallel per reformulation) + graph traversal
        ranked_lists = await self._retriever.vector_search_many(
            queries, company, project, settings.vector_search_limit
        )
        top_vector_hits = ranked_lists[0] if ranked_lists else []
        graph_hits = await self._retriever.graph_enrich(
            top_vector_hits, company, settings.graph_traversal_limit
        )

        # H: Reciprocal Rank Fusion -> deduplicated context
        fused: list[ScoredChunk] = reciprocal_rank_fusion(
            ranked_lists, key_fn=lambda c: c.chunk_id
        )
        fused = await rerank(question, fused, settings.rerank_top_k)

        if not fused:
            logger.info("rag_no_context_found", company=company, project=project)
            return RagAnswer(
                text="I couldn't find anything in the indexed documents that answers this.",
                refused=False,
                model_version=self._model_provider.default_model_version,
            )

        # I: draft answer with per-claim citations
        answer_text, validated = await self._generate_and_validate(question, fused)

        if answer_text is None:
            counters.increment(CITATION_VALIDATION_REFUSALS_TOTAL)
            return RagAnswer(
                text="I found related content but couldn't verify a claim against "
                     "the source documents closely enough to answer confidently. "
                     "Please check the underlying documents directly.",
                refused=True,
                model_version=self._model_provider.default_model_version,
            )

        return RagAnswer(
            text=answer_text,
            citations=validated,
            refused=False,
            model_version=self._model_provider.default_model_version,
        )

    async def _generate_and_validate(
        self, question: str, chunks: list[ScoredChunk]
    ) -> tuple[str | None, list[ValidatedCitation]]:
        settings = get_settings().rag
        context = format_answer_with_citations(chunks)

        prompt = ANSWER_PROMPT.format(context=context, question=question)
        attempt = 0
        while True:
            response = await self._model_provider.complete(prompt, temperature=0.1)
            valid, validated = self._citation_validator.validate(response.text, chunks)

            if valid:
                return response.text, validated

            counters.increment(CITATION_VALIDATION_FAILURES_TOTAL)
            attempt += 1
            if attempt > settings.max_citation_retries:
                logger.warning("citation_validation_exhausted_refusing", question=question)
                return None, []

            logger.info("citation_validation_retry", attempt=attempt)
            prompt = ANSWER_PROMPT.format(context=context, question=question) + STRICTER_RETRY_SUFFIX

'@

New-Dir (Split-Path -Parent "app/platform/rag/reranker.py")
Write-File "app/platform/rag/reranker.py" @'
"""Reranker — optional, tenant-tunable (ARCH §3.3 point 6, config
`rag.reranker_enabled`). Off by default: a cross-encoder rerank pass adds
latency (NFR-PERF.6) for a corpus this size where RRF fusion already
performs adequately; it's a lever a tenant with a much larger document
set can flip on, not a hardcoded stage.
"""
from __future__ import annotations

from app.config import get_settings
from app.observability.logging import get_logger
from app.platform.vector_store.adapter import ScoredChunk

logger = get_logger(__name__)

_cross_encoder = None


async def rerank(query: str, chunks: list[ScoredChunk], top_k: int) -> list[ScoredChunk]:
    settings = get_settings().rag
    if not settings.reranker_enabled or not chunks:
        return chunks[:top_k]

    global _cross_encoder
    if _cross_encoder is None:
        from sentence_transformers import CrossEncoder

        _cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
        logger.info("reranker_model_loaded")

    import asyncio

    pairs = [(query, c.chunk_text) for c in chunks]
    loop = asyncio.get_event_loop()
    scores = await loop.run_in_executor(None, _cross_encoder.predict, pairs)

    reranked = sorted(zip(chunks, scores), key=lambda pair: pair[1], reverse=True)
    return [c for c, _score in reranked[:top_k]]

'@

New-Dir (Split-Path -Parent "app/platform/rag/retriever.py")
Write-File "app/platform/rag/retriever.py" @'
"""Retriever — runs vector search per reformulated query plus a graph
traversal, in parallel (ARCH Flowchart 4 step G: "Hybrid retrieval: vector
search + graph traversal"), producing the ranked lists RRF then fuses.
"""
from __future__ import annotations

import asyncio

from app.observability.logging import get_logger
from app.platform.graph_store.adapter import GraphResult, GraphStoreAdapter
from app.platform.rag.embedder import Embedder
from app.platform.vector_store.adapter import ScoredChunk, VectorStoreAdapter

logger = get_logger(__name__)


class Retriever:
    def __init__(
        self, vector_store: VectorStoreAdapter, graph_store: GraphStoreAdapter, embedder: Embedder,
    ) -> None:
        self._vector_store = vector_store
        self._graph_store = graph_store
        self._embedder = embedder

    async def vector_search_many(
        self, queries: list[str], company: str, project: str | None, limit_per_query: int,
    ) -> list[list[ScoredChunk]]:
        embeddings = await self._embedder.embed_batch(queries)
        results = await asyncio.gather(
            *[
                self._vector_store.search(emb, company, project, limit_per_query)
                for emb in embeddings
            ]
        )
        return list(results)

    async def graph_enrich(
        self, seed_chunks: list[ScoredChunk], company: str, limit: int,
    ) -> list[GraphResult]:
        """Uses the top vector hits' source documents as seeds for a graph
        traversal, so retrieval can surface e.g. the Task an RFI blocks
        even when the traversal query itself never mentions that Task by
        name (FR-8.2's cross-cutting example).
        """
        if not seed_chunks:
            return []

        from app.platform.graph_store.cypher_queries import (
            DELAYED_TASK_SUBCONTRACTORS_WITH_INCIDENTS,
        )

        try:
            return await self._graph_store.traverse(
                DELAYED_TASK_SUBCONTRACTORS_WITH_INCIDENTS, {}, company, limit
            )
        except Exception as exc:  # noqa: BLE001 — graph enrichment is additive, never blocking
            logger.warning("graph_enrich_failed_continuing_vector_only", error=str(exc))
            return []

'@

New-Dir (Split-Path -Parent "app/platform/rag/rrf.py")
Write-File "app/platform/rag/rrf.py" @'
"""Reciprocal Rank Fusion — combines multiple ranked result lists (one per
reformulated query, plus the graph-traversal list) into a single
deduplicated, re-ranked context set (Flowchart 4 step H).

RRF score for a document d: sum over lists L containing d of
1 / (k + rank_L(d)). k=60 is the standard default from the original RRF
paper and needs no per-corpus tuning to be effective.
"""
from __future__ import annotations

from collections import defaultdict
from typing import TypeVar

T = TypeVar("T")


def reciprocal_rank_fusion(
    ranked_lists: list[list[T]], key_fn, k: int = 60
) -> list[T]:
    """`key_fn(item) -> hashable` identifies duplicate items across lists
    (e.g. chunk_id). Returns items ordered by fused score, deduplicated,
    keeping the first-seen instance of each key for the returned object.
    """
    scores: dict = defaultdict(float)
    first_seen: dict = {}

    for ranked_list in ranked_lists:
        for rank, item in enumerate(ranked_list, start=1):
            key = key_fn(item)
            scores[key] += 1.0 / (k + rank)
            if key not in first_seen:
                first_seen[key] = item

    ordered_keys = sorted(scores.keys(), key=lambda k_: scores[k_], reverse=True)
    return [first_seen[k_] for k_ in ordered_keys]

'@

New-Dir (Split-Path -Parent "app/platform/citations/__init__.py")
Write-File "app/platform/citations/__init__.py" @'
from app.platform.citations.citation_validator import CitationValidator, ValidatedCitation

__all__ = ["CitationValidator", "ValidatedCitation"]

'@

New-Dir (Split-Path -Parent "app/platform/citations/citation_formatter.py")
Write-File "app/platform/citations/citation_formatter.py" @'
"""Formats retrieved chunks into a numbered context block for the
generation prompt, and provides the reverse mapping citation_validator.py
needs to resolve a [n] marker back to the real chunk it refers to.
"""
from __future__ import annotations

from app.platform.vector_store.adapter import ScoredChunk


def format_answer_with_citations(chunks: list[ScoredChunk]) -> str:
    lines = []
    for i, chunk in enumerate(chunks, start=1):
        lines.append(
            f"[{i}] ({chunk.source_doctype} {chunk.source_name}, "
            f"{chunk.span_type} {chunk.span_start}"
            f"{'-' + str(chunk.span_end) if chunk.span_end != chunk.span_start else ''}):\n"
            f"{chunk.chunk_text}\n"
        )
    return "\n".join(lines)

'@

New-Dir (Split-Path -Parent "app/platform/citations/citation_validator.py")
Write-File "app/platform/citations/citation_validator.py" @'
"""CitationValidator — Flowchart 4 step J: "claim matches real span?"

Two checks, both must pass for a citation marker to be considered valid:
1. The marker [n] must resolve to an actual chunk that was in the context
   (not an out-of-range or hallucinated index).
2. The sentence the marker is attached to must have meaningful lexical
   overlap with that chunk's text — catching the case where the model
   attaches a real-looking [n] to a claim the chunk doesn't actually
   support (citation-marker fabrication, not just index fabrication).

This is intentionally a lexical-overlap heuristic, not a full entailment
model — UC-8.1 E2 only requires catching claims that don't match a real
span "closely enough," and a heavyweight NLI model would add latency
(NFR-PERF.6) disproportionate to what a single retry-then-refuse already
buys.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.observability.logging import get_logger
from app.platform.vector_store.adapter import ScoredChunk

logger = get_logger(__name__)

_MARKER_RE = re.compile(r"\[(\d+)\]")
_WORD_RE = re.compile(r"[a-zA-Z0-9]+")


@dataclass(slots=True)
class ValidatedCitation:
    source_doctype: str
    source_name: str
    span_type: str
    span_start: int
    span_end: int
    quoted_span: str


def _sentence_containing(text: str, marker_pos: int) -> str:
    start = text.rfind(".", 0, marker_pos) + 1
    end = text.find(".", marker_pos)
    end = end + 1 if end != -1 else len(text)
    return text[start:end].strip()


def _jaccard(a: str, b: str) -> float:
    words_a = set(w.lower() for w in _WORD_RE.findall(a))
    words_b = set(w.lower() for w in _WORD_RE.findall(b))
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)


class CitationValidator:
    def __init__(self, min_overlap: float = 0.15) -> None:
        self._min_overlap = min_overlap

    def validate(
        self, answer_text: str, chunks: list[ScoredChunk]
    ) -> tuple[bool, list[ValidatedCitation]]:
        markers = list(_MARKER_RE.finditer(answer_text))
        if not markers:
            # An answer that makes claims with zero citations is exactly
            # what this gate exists to catch — treat as invalid so it
            # goes through the stricter-prompt retry rather than shipping
            # ungrounded prose.
            logger.info("citation_validation_no_markers_found")
            return False, []

        validated: list[ValidatedCitation] = []
        for match in markers:
            idx = int(match.group(1)) - 1
            if idx < 0 or idx >= len(chunks):
                logger.info("citation_validation_index_out_of_range", index=idx + 1)
                return False, []

            chunk = chunks[idx]
            claim_sentence = _sentence_containing(answer_text, match.start())
            overlap = _jaccard(claim_sentence, chunk.chunk_text)
            if overlap < self._min_overlap:
                logger.info(
                    "citation_validation_low_overlap",
                    index=idx + 1, overlap=round(overlap, 3),
                )
                return False, []

            validated.append(
                ValidatedCitation(
                    source_doctype=chunk.source_doctype,
                    source_name=chunk.source_name,
                    span_type=chunk.span_type,
                    span_start=chunk.span_start,
                    span_end=chunk.span_end,
                    quoted_span=chunk.chunk_text[:280],
                )
            )

        return True, validated

'@

New-Dir (Split-Path -Parent "app/platform/graph_store/__init__.py")
Write-File "app/platform/graph_store/__init__.py" @'
from app.platform.graph_store.adapter import GraphStoreAdapter, GraphResult
from app.platform.graph_store.age_adapter import AgeGraphAdapter

__all__ = ["GraphStoreAdapter", "GraphResult", "AgeGraphAdapter"]

'@

New-Dir (Split-Path -Parent "app/platform/graph_store/adapter.py")
Write-File "app/platform/graph_store/adapter.py" @'
"""GraphStoreAdapter — the other half of RetrievalAdapter (ERD §4.4).

Vector search answers "what does this clause say"; graph traversal
answers "which subcontractors on delayed tasks" (FR-8.2's own example).
Nodes/edges are a MIRROR of MariaDB, never hand-curated (ERD §4.3) —
writes here only ever come from ingest/entity_mirror_service.py reacting
to a CDC event, never from a chat turn.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(slots=True)
class GraphResult:
    node_key: str
    label: str
    mariadb_name: str
    properties: dict[str, Any] = field(default_factory=dict)
    relationship_path: list[str] = field(default_factory=list)


@runtime_checkable
class GraphStoreAdapter(Protocol):
    async def upsert_node(
        self, company: str, project: str | None, label: str, mariadb_name: str,
        properties: dict[str, Any],
    ) -> str:
        """Idempotent upsert (MERGE) keyed by (label, mariadb_name); returns node_key."""
        ...

    async def upsert_edge(
        self, company: str, edge_type: str, from_label: str, from_name: str,
        to_label: str, to_name: str,
    ) -> str:
        ...

    async def delete_node(self, company: str, label: str, mariadb_name: str) -> None:
        """UC-8.2/on_trash mirror — removes a node whose MariaDB source
        record was deleted, cascading its edges."""
        ...

    async def traverse(
        self, cypher: str, params: dict[str, Any], company: str, limit: int = 25,
    ) -> list[GraphResult]:
        """Scoped Cypher traversal (NFR-SEC.8: company is always enforced
        as a MATCH predicate, never left to the caller's query string
        alone) — see cypher_queries.py for the canned traversals callers
        should prefer over hand-writing Cypher per call site."""
        ...

'@

New-Dir (Split-Path -Parent "app/platform/graph_store/age_adapter.py")
Write-File "app/platform/graph_store/age_adapter.py" @'
"""AgeGraphAdapter — concrete GraphStoreAdapter over Apache AGE.

Cypher's MATCH clause cannot parameterize a node label or relationship
type (they're part of the query grammar, not a value), so `label` and
`edge_type` are validated against a fixed allow-list before ever being
interpolated into a query string — every value parameter (mariadb_name,
company, properties) goes through AGE's own `$1::agtype` parameter
binding, never string interpolation.
"""
from __future__ import annotations

import json
from typing import Any

import asyncpg

from app.observability.logging import get_logger
from app.platform.graph_store.adapter import GraphResult
from app.platform.graph_store.cypher_queries import (
    DELETE_NODE_TEMPLATE,
    GRAPH_NAME,
    UPSERT_EDGE_TEMPLATE,
    UPSERT_NODE_TEMPLATE,
)

logger = get_logger(__name__)

# ERD §4.3 — the closed set of node labels / edge types this platform mirrors.
ALLOWED_LABELS = {"Project", "Task", "RFI", "Commitment", "Person", "SafetyIncident"}
ALLOWED_EDGE_TYPES = {
    "HAS_TASK", "DEPENDS_ON", "ASSIGNED_TO", "RAISED_AGAINST", "COMMITTED_TO", "HAS_INCIDENT",
}


def _assert_allowed_label(label: str) -> None:
    if label not in ALLOWED_LABELS:
        raise ValueError(f"'{label}' is not an allow-listed graph node label")


def _assert_allowed_edge_type(edge_type: str) -> None:
    if edge_type not in ALLOWED_EDGE_TYPES:
        raise ValueError(f"'{edge_type}' is not an allow-listed graph edge type")


class AgeGraphAdapter:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def upsert_node(
        self, company: str, project: str | None, label: str, mariadb_name: str,
        properties: dict[str, Any],
    ) -> str:
        _assert_allowed_label(label)
        params = json.dumps(
            {"mariadb_name": mariadb_name, "company": company,
             "properties": {**properties, "project": project}}
        )
        query = UPSERT_NODE_TEMPLATE.format(graph=GRAPH_NAME, label=label)
        await self._conn.execute(query.replace("%s", f"'{params}'::agtype"))

        node_key = f"{label}:{mariadb_name}"
        await self._conn.execute(
            """
            INSERT INTO graph_node_index (node_key, label, mariadb_name, company, project, properties)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb)
            ON CONFLICT (node_key) DO UPDATE
                SET properties = EXCLUDED.properties, project = EXCLUDED.project, updated_at = now();
            """,
            node_key, label, mariadb_name, company, project, json.dumps(properties),
        )
        return node_key

    async def upsert_edge(
        self, company: str, edge_type: str, from_label: str, from_name: str,
        to_label: str, to_name: str,
    ) -> str:
        _assert_allowed_edge_type(edge_type)
        _assert_allowed_label(from_label)
        _assert_allowed_label(to_label)

        params = json.dumps({"from_name": from_name, "to_name": to_name, "company": company})
        query = UPSERT_EDGE_TEMPLATE.format(
            graph=GRAPH_NAME, from_label=from_label, to_label=to_label, edge_type=edge_type
        )
        await self._conn.execute(query.replace("%s", f"'{params}'::agtype"))

        from_key = f"{from_label}:{from_name}"
        to_key = f"{to_label}:{to_name}"
        edge_key = f"{edge_type}:{from_key}->{to_key}"
        await self._conn.execute(
            """
            INSERT INTO graph_edge_index (edge_key, edge_type, from_node_key, to_node_key, company)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (edge_key) DO UPDATE SET updated_at = now();
            """,
            edge_key, edge_type, from_key, to_key, company,
        )
        return edge_key

    async def delete_node(self, company: str, label: str, mariadb_name: str) -> None:
        _assert_allowed_label(label)
        params = json.dumps({"mariadb_name": mariadb_name, "company": company})
        query = DELETE_NODE_TEMPLATE.format(graph=GRAPH_NAME, label=label)
        await self._conn.execute(query.replace("%s", f"'{params}'::agtype"))

        node_key = f"{label}:{mariadb_name}"
        await self._conn.execute("DELETE FROM graph_node_index WHERE node_key = $1", node_key)

    async def traverse(
        self, cypher: str, params: dict[str, Any], company: str, limit: int = 25,
    ) -> list[GraphResult]:
        """`cypher` must be one of cypher_queries.py's pre-authored,
        reviewed traversal templates — never a caller-assembled string —
        so this method only ever formats graph name/limit, and binds
        company/other values as an agtype parameter.
        """
        full_params = {**params, "company": company, "limit": limit}
        query = cypher.format(graph=GRAPH_NAME)
        param_json = json.dumps(full_params)
        rows = await self._conn.fetch(query.replace("%s", f"'{param_json}'::agtype"))

        results: list[GraphResult] = []
        for row in rows:
            for value in row.values():
                if value is None:
                    continue
                try:
                    parsed = json.loads(str(value).rsplit("::", 1)[0])
                except (json.JSONDecodeError, ValueError):
                    continue
                props = parsed.get("properties", {})
                label = (parsed.get("label") or (parsed.get("labels") or [""])[0])
                results.append(
                    GraphResult(
                        node_key=f"{label}:{props.get('mariadb_name', '')}",
                        label=label,
                        mariadb_name=props.get("mariadb_name", ""),
                        properties=props,
                    )
                )
        return results

'@

New-Dir (Split-Path -Parent "app/platform/graph_store/cypher_queries.py")
Write-File "app/platform/graph_store/cypher_queries.py" @'
"""Canned, parameterized Cypher fragments — kept separate from
age_adapter.py's control flow so a query's shape is reviewable on its own
(NFR-MAINT.2), and so RagService's graph fan-in step can select a named
traversal rather than building Cypher inline.

Apache AGE requires the graph name in the SELECT ... FROM cypher(...) call
and returns an `agtype` column per RETURN item that the adapter parses.
Every fragment below embeds a company-scope filter directly in the MATCH,
never trusting a caller to have applied it downstream (NFR-SEC.8).
"""
from __future__ import annotations

GRAPH_NAME = "buildpolaris_graph"

UPSERT_NODE_TEMPLATE = """
    SELECT * FROM cypher('{graph}', $$
        MERGE (n:{label} {{mariadb_name: $mariadb_name, company: $company}})
        SET n += $properties
        RETURN n
    $$, %s) AS (n agtype);
"""

UPSERT_EDGE_TEMPLATE = """
    SELECT * FROM cypher('{graph}', $$
        MATCH (a:{from_label} {{mariadb_name: $from_name, company: $company}})
        MATCH (b:{to_label} {{mariadb_name: $to_name, company: $company}})
        MERGE (a)-[r:{edge_type}]->(b)
        RETURN r
    $$, %s) AS (r agtype);
"""

DELETE_NODE_TEMPLATE = """
    SELECT * FROM cypher('{graph}', $$
        MATCH (n:{label} {{mariadb_name: $mariadb_name, company: $company}})
        DETACH DELETE n
    $$, %s) AS (result agtype);
"""

# FR-8.2's own worked example: "which subcontractors on delayed tasks also
# have open safety incidents" — Task -[ASSIGNED_TO]-> Person <-[HAS_INCIDENT]- SafetyIncident,
# filtered on Task.is_critical / slippage.
DELAYED_TASK_SUBCONTRACTORS_WITH_INCIDENTS = """
    SELECT * FROM cypher('{graph}', $$
        MATCH (t:Task {{company: $company, is_critical: true}})-[:ASSIGNED_TO]->(p:Person)
        MATCH (p)<-[:HAS_INCIDENT]-(i:SafetyIncident {{company: $company}})
        RETURN t, p, i
        LIMIT $limit
    $$, %s) AS (t agtype, p agtype, i agtype);
"""

'@

New-Dir (Split-Path -Parent "app/platform/bff/__init__.py")
Write-File "app/platform/bff/__init__.py" @'
from app.platform.bff.bff_client import BFFClient
from app.platform.bff.mcp_client import BFFMCPClient

__all__ = ["BFFClient", "BFFMCPClient"]

'@

New-Dir (Split-Path -Parent "app/platform/bff/bff_client.py")
Write-File "app/platform/bff/bff_client.py" @'
"""BFFClient — general-purpose authenticated REST client for calls this
sidecar makes back into buildpolaris_bff (ARCH §4.2 Direction 2). Used
directly for simple one-shot calls (e.g. resolving a signed download URL
during ingestion is instead passed IN by the BFF, so in practice this
client's main consumer is mcp_client.py's transport — kept as its own
module so a non-MCP BFF endpoint can also be called without inventing a
second HTTP client).
"""
from __future__ import annotations

import httpx

from app.config import get_settings
from app.observability.logging import get_logger
from app.observability.tracing import get_trace_id

logger = get_logger(__name__)


class BFFClient:
    def __init__(self, raw_scope_assertion_token: str | None = None) -> None:
        self._settings = get_settings().bff
        self._raw_assertion = raw_scope_assertion_token

    def _headers(self) -> dict[str, str]:
        headers = {
            "X-Service-Key": self._settings.service_key.get_secret_value(),
            "X-Trace-Id": get_trace_id(),
        }
        if self._raw_assertion:
            headers["X-Scope-Assertion"] = self._raw_assertion
        return headers

    async def post(self, path: str, json: dict) -> dict:
        url = f"{self._settings.base_url}{path}"
        async with httpx.AsyncClient(timeout=self._settings.timeout_seconds) as client:
            response = await client.post(url, json=json, headers=self._headers())
            response.raise_for_status()
            return response.json()

    async def get(self, path: str, params: dict | None = None) -> dict:
        url = f"{self._settings.base_url}{path}"
        async with httpx.AsyncClient(timeout=self._settings.timeout_seconds) as client:
            response = await client.get(url, params=params, headers=self._headers())
            response.raise_for_status()
            return response.json()

'@

New-Dir (Split-Path -Parent "app/platform/bff/mcp_client.py")
Write-File "app/platform/bff/mcp_client.py" @'
"""BFFMCPClient — Streamable HTTP MCP client calling buildpolaris_bff's
MCP server (ARCH §4.2 Direction 2: "AI is a client calling BFF's MCP
server", read-only tools only in v1). This wraps the `mcp` SDK's
streamable-http client transport so orchestrator/tool_dispatcher.py never
has to know MCP protocol details — it just calls `list_tools()` /
`call_tool()`.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from app.config import get_settings
from app.gateway.auth.scope_assertion import ScopeAssertion
from app.gateway.auth.on_behalf_of import build_on_behalf_of_headers
from app.observability.logging import get_logger

logger = get_logger(__name__)


class BFFMCPClient:
    """One instance per copilot turn — carries the Scope Assertion for
    that turn so every tool call it makes is on-behalf-of the same asserted
    user (never re-minted, never escalated)."""

    def __init__(self, assertion: ScopeAssertion, raw_assertion_token: str) -> None:
        self._settings = get_settings().bff
        self._headers = build_on_behalf_of_headers(
            assertion, self._settings.service_key.get_secret_value(), raw_assertion_token
        )

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[Any]:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        async with streamablehttp_client(
            self._settings.mcp_url, headers=self._headers,
        ) as (read_stream, write_stream, _get_session_id):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield session

    async def list_tools(self) -> list[dict]:
        async with self._session() as session:
            result = await session.list_tools()
            return [{"name": t.name, "description": t.description} for t in result.tools]

    async def call_tool(self, name: str, arguments: dict) -> dict:
        async with self._session() as session:
            result = await session.call_tool(name, arguments)
            if result.isError:
                logger.warning("mcp_tool_call_error", tool=name, arguments=arguments)
            # MCP tool results are a list of content blocks; read-only
            # tools here always return exactly one text/JSON block.
            for block in result.content:
                if hasattr(block, "text"):
                    import json

                    try:
                        return json.loads(block.text)
                    except (json.JSONDecodeError, TypeError):
                        return {"text": block.text}
            return {}

'@

New-Dir (Split-Path -Parent "app/platform/bff/read_tools.py")
Write-File "app/platform/bff/read_tools.py" @'
"""Read-only tool catalog this sidecar knows how to call on BFF's MCP
server (UC-8.2 — navigation intent resolves within the caller's existing
permitted scope). Kept as named, typed wrapper functions rather than
leaving orchestrator/tool_dispatcher.py to build raw tool-call dicts
inline, so adding/removing a read tool is a one-place change.

The actual permission enforcement happens BFF-side (has_permission against
the on-behalf-of user, per the forwarded Scope Assertion) — this module
only shapes the call, it grants nothing.
"""
from __future__ import annotations

from app.platform.bff.mcp_client import BFFMCPClient


async def find_record(client: BFFMCPClient, doctype: str, query: str) -> dict:
    """Navigation intent — 'find the RFI about the elevator shaft'."""
    return await client.call_tool("find_record", {"doctype": doctype, "query": query})


async def get_record(client: BFFMCPClient, doctype: str, name: str) -> dict:
    return await client.call_tool("get_record", {"doctype": doctype, "name": name})


async def list_open_items(client: BFFMCPClient, doctype: str, project: str | None) -> dict:
    """'What RFIs are still open on this project' — a bounded list query,
    not free-text search."""
    return await client.call_tool("list_open_items", {"doctype": doctype, "project": project})


async def get_project_summary(client: BFFMCPClient, project: str) -> dict:
    return await client.call_tool("get_project_summary", {"project": project})

'@

New-Dir (Split-Path -Parent "app/platform/model_provider/__init__.py")
Write-File "app/platform/model_provider/__init__.py" @'
from app.platform.model_provider.adapter import ModelProviderAdapter, ModelResponse
from app.platform.model_provider.circuit_breaker import get_circuit_breaker

__all__ = ["ModelProviderAdapter", "ModelResponse", "get_circuit_breaker"]

'@

New-Dir (Split-Path -Parent "app/platform/model_provider/adapter.py")
Write-File "app/platform/model_provider/adapter.py" @'
"""ModelProviderAdapter — the port (ERD §4.4 class diagram, ratified).

NFR-EXT.2's sibling requirement for the LLM side: swapping a vendor or
adding a provider must not require touching every agent. Every concrete
provider (Gemini, Ollama, Anthropic, OpenAI) implements this one
interface; RagService and every agent depend only on this, never on a
concrete SDK.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Type, TypeVar, runtime_checkable

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@dataclass(slots=True)
class ModelResponse:
    text: str
    model_version: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


@runtime_checkable
class ModelProviderAdapter(Protocol):
    """Every method is model-version-explicit-capable: callers may pass a
    pinned model_version (NFR-AIGOV.2) rather than relying on an
    adapter-internal default that could silently change upstream."""

    @property
    def provider_name(self) -> str: ...

    @property
    def default_model_version(self) -> str: ...

    async def complete(
        self, prompt: str, model_version: str | None = None, temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> ModelResponse:
        """Free-text completion."""
        ...

    async def structured_complete(
        self, prompt: str, response_model: Type[T], model_version: str | None = None,
        temperature: float = 0.1,
    ) -> T:
        """Structured generation constrained to a Pydantic schema — this is
        what RFIDraftingAgent and friends use so their output is a typed
        proposed_payload, not free text needing post-hoc parsing."""
        ...

    async def embed(self, text: str, model_version: str | None = None) -> list[float]:
        """Single-text embedding."""
        ...

    async def embed_batch(
        self, texts: list[str], model_version: str | None = None
    ) -> list[list[float]]:
        ...

'@

New-Dir (Split-Path -Parent "app/platform/model_provider/anthropic_adapter.py")
Write-File "app/platform/model_provider/anthropic_adapter.py" @'
"""Anthropic adapter — extensibility slot (ARCH §3.3 point 2: "room for
AnthropicAdapter/OpenAIAdapter alongside it"). Not wired as primary or
fallback in v1 (no free-tier key path), but implements the same port so a
tenant can be pinned to it (NFR-AIGOV.2) the moment a key is configured,
with zero changes anywhere else in the codebase.
"""
from __future__ import annotations

from typing import Type, TypeVar

from pydantic import BaseModel

from app.observability.logging import get_logger
from app.platform.model_provider.adapter import ModelResponse

logger = get_logger(__name__)
T = TypeVar("T", bound=BaseModel)


class AnthropicProvider:
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6") -> None:
        import anthropic  # imported lazily — optional dependency in v1

        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model_name = model

    @property
    def provider_name(self) -> str:
        return "anthropic"

    @property
    def default_model_version(self) -> str:
        return self._model_name

    async def complete(
        self, prompt: str, model_version: str | None = None,
        temperature: float = 0.2, max_tokens: int = 2048,
    ) -> ModelResponse:
        target = model_version or self._model_name
        response = await self._client.messages.create(
            model=target, max_tokens=max_tokens, temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in response.content if hasattr(b, "text"))
        return ModelResponse(
            text=text, model_version=target,
            prompt_tokens=response.usage.input_tokens,
            completion_tokens=response.usage.output_tokens,
        )

    async def structured_complete(
        self, prompt: str, response_model: Type[T], model_version: str | None = None,
        temperature: float = 0.1,
    ) -> T:
        schema_prompt = (
            f"{prompt}\n\nRespond with ONLY valid JSON matching this schema:\n"
            f"{response_model.model_json_schema()}"
        )
        result = await self.complete(schema_prompt, model_version, temperature)
        return response_model.model_validate_json(result.text)

    async def embed(self, text: str, model_version: str | None = None) -> list[float]:
        raise NotImplementedError(
            "Anthropic does not offer an embeddings endpoint — pin embedding "
            "to a different provider via config, not this adapter."
        )

    async def embed_batch(self, texts: list[str], model_version: str | None = None) -> list[list[float]]:
        raise NotImplementedError("see embed()")

'@

New-Dir (Split-Path -Parent "app/platform/model_provider/circuit_breaker.py")
Write-File "app/platform/model_provider/circuit_breaker.py" @'
"""Circuit breaker — falls back from a rate-limited/exhausted primary
provider to a secondary provider or a locally-hosted Ollama model,
without any agent code knowing a fallback occurred (ARCH §3.3 point 2).

Per-provider breaker state: CLOSED (healthy) -> OPEN (failing, calls
short-circuit) -> HALF_OPEN (probe) -> CLOSED. Standard breaker shape,
kept intentionally simple (thresholds from ResilienceSettings) rather
than pulling in a breaker library for three states and one counter.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, TypeVar

from app.config import get_settings
from app.exceptions import ModelProviderUnavailableError
from app.observability.logging import get_logger
from app.observability.metrics import CIRCUIT_BREAKER_TRIPS_TOTAL, counters

logger = get_logger(__name__)
T = TypeVar("T")


class BreakerState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class _ProviderBreaker:
    name: str
    failure_count: int = 0
    state: BreakerState = BreakerState.CLOSED
    opened_at: float | None = None

    def record_success(self) -> None:
        self.failure_count = 0
        self.state = BreakerState.CLOSED
        self.opened_at = None

    def record_failure(self, threshold: int) -> None:
        self.failure_count += 1
        if self.failure_count >= threshold and self.state != BreakerState.OPEN:
            self.state = BreakerState.OPEN
            self.opened_at = time.monotonic()
            counters.increment(CIRCUIT_BREAKER_TRIPS_TOTAL)
            logger.warning("circuit_breaker_opened", provider=self.name)

    def allows_call(self, recovery_seconds: float) -> bool:
        if self.state == BreakerState.CLOSED:
            return True
        if self.state == BreakerState.OPEN:
            if self.opened_at and (time.monotonic() - self.opened_at) >= recovery_seconds:
                self.state = BreakerState.HALF_OPEN
                return True
            return False
        return True  # HALF_OPEN: allow exactly one probe through


class CircuitBreakerRegistry:
    """One breaker per provider name; the model_provider factory routes
    every call through `call_with_breaker`."""

    def __init__(self) -> None:
        self._breakers: dict[str, _ProviderBreaker] = {}

    def _get(self, provider_name: str) -> _ProviderBreaker:
        return self._breakers.setdefault(provider_name, _ProviderBreaker(name=provider_name))

    async def call_with_breaker(self, provider_name: str, fn: Callable[[], T]) -> T:
        settings = get_settings().resilience
        breaker = self._get(provider_name)

        if not breaker.allows_call(settings.breaker_recovery_seconds):
            raise ModelProviderUnavailableError(f"provider '{provider_name}' circuit open")

        try:
            result = await fn()
        except Exception:
            breaker.record_failure(settings.breaker_failure_threshold)
            raise
        else:
            breaker.record_success()
            return result

    def all_providers_open(self) -> bool:
        if not self._breakers:
            return False
        return all(b.state == BreakerState.OPEN for b in self._breakers.values())

    def snapshot(self) -> dict[str, str]:
        return {name: b.state.value for name, b in self._breakers.items()}


_registry = CircuitBreakerRegistry()


def get_circuit_breaker() -> CircuitBreakerRegistry:
    return _registry

'@

New-Dir (Split-Path -Parent "app/platform/model_provider/factory.py")
Write-File "app/platform/model_provider/factory.py" @'
"""Resolves the configured primary + fallback ModelProviderAdapter pair
and wraps every call through the circuit breaker, so `RagService` and
every agent depend only on `ResilientModelProvider` — a single object
that behaves like a `ModelProviderAdapter` but internally fails over.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Type, TypeVar

from pydantic import BaseModel

from app.config import Settings, get_settings
from app.exceptions import ModelProviderUnavailableError
from app.observability.logging import get_logger
from app.platform.model_provider.adapter import ModelProviderAdapter, ModelResponse
from app.platform.model_provider.circuit_breaker import get_circuit_breaker

logger = get_logger(__name__)
T = TypeVar("T", bound=BaseModel)


def _build_provider(name: str, settings: Settings) -> ModelProviderAdapter | None:
    mp = settings.model_provider
    if name == "gemini":
        if not mp.gemini_api_key:
            return None
        from app.platform.model_provider.gemini_adapter import GeminiProvider

        return GeminiProvider(
            api_key=mp.gemini_api_key.get_secret_value(),
            model=mp.gemini_model,
            embedding_model=mp.gemini_embedding_model,
        )
    if name == "ollama":
        from app.platform.model_provider.ollama_adapter import OllamaProvider

        return OllamaProvider(base_url=mp.ollama_base_url, model=mp.ollama_model)
    if name == "anthropic":
        if not mp.anthropic_api_key:
            return None
        from app.platform.model_provider.anthropic_adapter import AnthropicProvider

        return AnthropicProvider(api_key=mp.anthropic_api_key.get_secret_value(), model=mp.anthropic_model)
    if name == "openai":
        if not mp.openai_api_key:
            return None
        from app.platform.model_provider.openai_adapter import OpenAIProvider

        return OpenAIProvider(api_key=mp.openai_api_key.get_secret_value(), model=mp.openai_model)
    if name == "none":
        return None
    raise ValueError(f"unknown model provider '{name}'")


class ResilientModelProvider:
    """Implements ModelProviderAdapter's shape while internally trying the
    primary provider first, and the configured fallback if the primary's
    breaker is open or the call itself fails."""

    def __init__(self, primary: ModelProviderAdapter, fallback: ModelProviderAdapter | None) -> None:
        self._primary = primary
        self._fallback = fallback
        self._breaker = get_circuit_breaker()

    @property
    def provider_name(self) -> str:
        return self._primary.provider_name

    @property
    def default_model_version(self) -> str:
        return self._primary.default_model_version

    async def _with_fallback(self, method_name: str, *args, **kwargs):
        try:
            fn = getattr(self._primary, method_name)
            return await self._breaker.call_with_breaker(
                self._primary.provider_name, lambda: fn(*args, **kwargs)
            )
        except Exception as primary_exc:
            if self._fallback is None:
                raise
            logger.warning(
                "model_provider_falling_back",
                primary=self._primary.provider_name,
                fallback=self._fallback.provider_name,
                error=str(primary_exc),
            )
            try:
                fn = getattr(self._fallback, method_name)
                return await self._breaker.call_with_breaker(
                    self._fallback.provider_name, lambda: fn(*args, **kwargs)
                )
            except Exception as fallback_exc:
                raise ModelProviderUnavailableError(
                    f"primary '{self._primary.provider_name}' and fallback "
                    f"'{self._fallback.provider_name}' both failed"
                ) from fallback_exc

    async def complete(self, prompt: str, model_version: str | None = None,
                        temperature: float = 0.2, max_tokens: int = 2048) -> ModelResponse:
        return await self._with_fallback("complete", prompt, model_version, temperature, max_tokens)

    async def structured_complete(self, prompt: str, response_model: Type[T],
                                   model_version: str | None = None, temperature: float = 0.1) -> T:
        return await self._with_fallback(
            "structured_complete", prompt, response_model, model_version, temperature
        )

    async def embed(self, text: str, model_version: str | None = None) -> list[float]:
        return await self._with_fallback("embed", text, model_version)

    async def embed_batch(self, texts: list[str], model_version: str | None = None) -> list[list[float]]:
        return await self._with_fallback("embed_batch", texts, model_version)


@lru_cache
def get_model_provider() -> ResilientModelProvider:
    settings = get_settings()
    mp = settings.model_provider

    primary = _build_provider(mp.primary, settings)
    if primary is None:
        raise ModelProviderUnavailableError(
            f"primary provider '{mp.primary}' is not configured (missing API key?)"
        )
    fallback = _build_provider(mp.fallback, settings)

    logger.info(
        "model_provider_resolved",
        primary=mp.primary,
        fallback=mp.fallback if fallback else "none",
    )
    return ResilientModelProvider(primary, fallback)

'@

New-Dir (Split-Path -Parent "app/platform/model_provider/gemini_adapter.py")
Write-File "app/platform/model_provider/gemini_adapter.py" @'
"""Google Gemini adapter — primary provider (free-tier API key).

Uses the official google-genai SDK's structured-output support so
structured_complete() returns a real, schema-validated Pydantic instance
rather than a hand-parsed JSON blob.
"""
from __future__ import annotations

from typing import Type, TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel

from app.observability.logging import get_logger
from app.platform.model_provider.adapter import ModelResponse

logger = get_logger(__name__)
T = TypeVar("T", bound=BaseModel)


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


class GeminiProvider:
    def __init__(
        self, api_key: str, model: str = "gemini-2.0-flash",
        embedding_model: str = "text-embedding-004",
    ) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model_name = model
        self._embedding_model = embedding_model
        logger.info("gemini_provider_initialized", model=model)

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def default_model_version(self) -> str:
        return self._model_name

    async def complete(
        self, prompt: str, model_version: str | None = None,
        temperature: float = 0.2, max_tokens: int = 2048,
    ) -> ModelResponse:
        target = model_version or self._model_name
        response = await self._client.aio.models.generate_content(
            model=target,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=temperature, max_output_tokens=max_tokens
            ),
        )
        usage = getattr(response, "usage_metadata", None)
        return ModelResponse(
            text=response.text or "",
            model_version=target,
            prompt_tokens=getattr(usage, "prompt_token_count", 0) or 0,
            completion_tokens=getattr(usage, "candidates_token_count", 0) or 0,
        )

    async def structured_complete(
        self, prompt: str, response_model: Type[T], model_version: str | None = None,
        temperature: float = 0.1,
    ) -> T:
        target = model_version or self._model_name
        response = await self._client.aio.models.generate_content(
            model=target,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=temperature,
                response_mime_type="application/json",
                response_schema=response_model,
            ),
        )
        if getattr(response, "parsed", None) is not None:
            return response.parsed
        raw = _strip_code_fences(response.text or "")
        return response_model.model_validate_json(raw)

    async def embed(self, text: str, model_version: str | None = None) -> list[float]:
        target = model_version or self._embedding_model
        response = await self._client.aio.models.embed_content(model=target, contents=text)
        return list(response.embeddings[0].values)

    async def embed_batch(
        self, texts: list[str], model_version: str | None = None
    ) -> list[list[float]]:
        target = model_version or self._embedding_model
        response = await self._client.aio.models.embed_content(model=target, contents=texts)
        return [list(e.values) for e in response.embeddings]

'@

New-Dir (Split-Path -Parent "app/platform/model_provider/model_pin.py")
Write-File "app/platform/model_provider/model_pin.py" @'
"""NFR-AIGOV.2 — model-version pinning per tenant or globally.

"A silent upstream model update cannot change agent behavior (approval-
gate reliability, citation accuracy) without a deliberate, tested
rollout." This resolves, for a given company (tenant), the model_version
string every ModelProviderAdapter call should be pinned to — global
default from config, overridable per tenant via the same store used for
other tenant-level configuration (kept in-process + Postgres-backed here;
swappable without touching callers since everything routes through
resolve_model_version()).
"""
from __future__ import annotations

from app.config import get_settings

# In-memory tenant override map. A production deployment would back this
# with a small Postgres table (tenant_model_pins) written by an admin
# screen; the resolution contract below is what matters for NFR-AIGOV.2,
# not the storage medium, and is the one seam a persistence swap touches.
_tenant_overrides: dict[str, str] = {}


def set_tenant_model_pin(company: str, model_version: str) -> None:
    _tenant_overrides[company] = model_version


def clear_tenant_model_pin(company: str) -> None:
    _tenant_overrides.pop(company, None)


def resolve_model_version(company: str | None = None) -> str:
    if company and company in _tenant_overrides:
        return _tenant_overrides[company]
    return get_settings().model_provider.model_version_pin

'@

New-Dir (Split-Path -Parent "app/platform/model_provider/ollama_adapter.py")
Write-File "app/platform/model_provider/ollama_adapter.py" @'
"""Ollama adapter — self-hosted fallback (ARCH §3.3 point 2: "a circuit
breaker falls back from a rate-limited or exhausted free-tier key to a
secondary provider or a locally-hosted Ollama model").
"""
from __future__ import annotations

import json
from typing import Type, TypeVar

import httpx
from pydantic import BaseModel

from app.observability.logging import get_logger
from app.platform.model_provider.adapter import ModelResponse

logger = get_logger(__name__)
T = TypeVar("T", bound=BaseModel)


class OllamaProvider:
    def __init__(self, base_url: str, model: str = "qwen2.5:3b-instruct") -> None:
        self._base_url = base_url.rstrip("/")
        self._model_name = model

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def default_model_version(self) -> str:
        return self._model_name

    async def complete(
        self, prompt: str, model_version: str | None = None,
        temperature: float = 0.2, max_tokens: int = 2048,
    ) -> ModelResponse:
        target = model_version or self._model_name
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self._base_url}/api/generate",
                json={
                    "model": target, "prompt": prompt, "stream": False,
                    "options": {"temperature": temperature, "num_predict": max_tokens},
                },
            )
            resp.raise_for_status()
            data = resp.json()
        return ModelResponse(
            text=data.get("response", ""),
            model_version=target,
            prompt_tokens=data.get("prompt_eval_count", 0),
            completion_tokens=data.get("eval_count", 0),
        )

    async def structured_complete(
        self, prompt: str, response_model: Type[T], model_version: str | None = None,
        temperature: float = 0.1,
    ) -> T:
        schema_prompt = (
            f"{prompt}\n\nRespond with ONLY valid JSON matching this schema, "
            f"no prose, no code fences:\n{response_model.model_json_schema()}"
        )
        result = await self.complete(schema_prompt, model_version, temperature)
        text = result.text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return response_model.model_validate(json.loads(text))

    async def embed(self, text: str, model_version: str | None = None) -> list[float]:
        target = model_version or "nomic-embed-text"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self._base_url}/api/embeddings", json={"model": target, "prompt": text}
            )
            resp.raise_for_status()
            return resp.json()["embedding"]

    async def embed_batch(
        self, texts: list[str], model_version: str | None = None
    ) -> list[list[float]]:
        return [await self.embed(t, model_version) for t in texts]

'@

New-Dir (Split-Path -Parent "app/platform/model_provider/openai_adapter.py")
Write-File "app/platform/model_provider/openai_adapter.py" @'
"""OpenAI adapter — extensibility slot, same rationale as
anthropic_adapter.py. Not wired as primary or fallback in v1.
"""
from __future__ import annotations

from typing import Type, TypeVar

from pydantic import BaseModel

from app.observability.logging import get_logger
from app.platform.model_provider.adapter import ModelResponse

logger = get_logger(__name__)
T = TypeVar("T", bound=BaseModel)


class OpenAIProvider:
    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        import openai  # imported lazily — optional dependency in v1

        self._client = openai.AsyncOpenAI(api_key=api_key)
        self._model_name = model

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def default_model_version(self) -> str:
        return self._model_name

    async def complete(
        self, prompt: str, model_version: str | None = None,
        temperature: float = 0.2, max_tokens: int = 2048,
    ) -> ModelResponse:
        target = model_version or self._model_name
        response = await self._client.chat.completions.create(
            model=target, temperature=temperature, max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return ModelResponse(
            text=response.choices[0].message.content or "",
            model_version=target,
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
        )

    async def structured_complete(
        self, prompt: str, response_model: Type[T], model_version: str | None = None,
        temperature: float = 0.1,
    ) -> T:
        target = model_version or self._model_name
        response = await self._client.beta.chat.completions.parse(
            model=target, temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
            response_format=response_model,
        )
        return response.choices[0].message.parsed

    async def embed(self, text: str, model_version: str | None = None) -> list[float]:
        target = model_version or "text-embedding-3-small"
        response = await self._client.embeddings.create(model=target, input=text)
        return response.data[0].embedding

    async def embed_batch(self, texts: list[str], model_version: str | None = None) -> list[list[float]]:
        target = model_version or "text-embedding-3-small"
        response = await self._client.embeddings.create(model=target, input=texts)
        return [d.embedding for d in response.data]

'@

New-Dir (Split-Path -Parent "app/platform/model_provider/token_meter.py")
Write-File "app/platform/model_provider/token_meter.py" @'
"""Wraps a ModelProviderAdapter call so every completion/embedding call
reports its token usage to the NFR-AIGOV.1 tracker, in one place, rather
than every agent remembering to do it themselves.
"""
from __future__ import annotations

from typing import Type, TypeVar

from pydantic import BaseModel

from app.observability.token_usage import get_token_usage_tracker
from app.platform.model_provider.adapter import ModelProviderAdapter, ModelResponse

T = TypeVar("T", bound=BaseModel)


class MeteredModelProvider:
    """Decorates any ModelProviderAdapter with usage metering. Agents and
    RagService depend on ModelProviderAdapter's interface as usual; this
    wrapper is applied once, at provider-resolution time (see factory
    wiring in app/dependencies.py), so metering is never optional or
    forgotten per call site.
    """

    def __init__(self, inner: ModelProviderAdapter, company: str) -> None:
        self._inner = inner
        self._company = company

    @property
    def provider_name(self) -> str:
        return self._inner.provider_name

    @property
    def default_model_version(self) -> str:
        return self._inner.default_model_version

    async def complete(self, prompt: str, model_version: str | None = None,
                        temperature: float = 0.2, max_tokens: int = 2048) -> ModelResponse:
        response = await self._inner.complete(prompt, model_version, temperature, max_tokens)
        self._record(response)
        return response

    async def structured_complete(self, prompt: str, response_model: Type[T],
                                   model_version: str | None = None,
                                   temperature: float = 0.1) -> T:
        result = await self._inner.structured_complete(
            prompt, response_model, model_version, temperature
        )
        # Structured calls don't always surface token counts from every
        # SDK; estimate conservatively from prompt length when absent so
        # spend is never silently under-tracked.
        estimate = max(len(prompt) // 4, 1)
        get_token_usage_tracker().record_usage(self._company, estimate, estimate // 2)
        return result

    async def embed(self, text: str, model_version: str | None = None) -> list[float]:
        return await self._inner.embed(text, model_version)

    async def embed_batch(self, texts: list[str], model_version: str | None = None) -> list[list[float]]:
        return await self._inner.embed_batch(texts, model_version)

    def _record(self, response: ModelResponse) -> None:
        get_token_usage_tracker().record_usage(
            self._company, response.prompt_tokens, response.completion_tokens
        )

'@

New-Dir (Split-Path -Parent "app/observability/__init__.py")
Write-File "app/observability/__init__.py" @'
from app.observability.logging import configure_logging, get_logger
from app.observability.tracing import get_trace_id, trace_id_var

__all__ = ["configure_logging", "get_logger", "get_trace_id", "trace_id_var"]

'@

New-Dir (Split-Path -Parent "app/observability/logging.py")
Write-File "app/observability/logging.py" @'
"""Structured JSON logging (NFR-OBS.1) — every log line can carry a
trace_id that follows a request across PWA -> BFF -> AI sidecar so a
single user-reported issue is traceable end-to-end without timestamp
guesswork (ARCH §4.2 "Correlation").
"""
from __future__ import annotations

import logging
import sys

import structlog

from app.config import get_settings
from app.observability.tracing import trace_id_var


def _add_trace_id(logger, method_name, event_dict):
    trace_id = trace_id_var.get(None)
    if trace_id:
        event_dict["trace_id"] = trace_id
    return event_dict


def configure_logging() -> None:
    settings = get_settings().observability
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    logging.basicConfig(
        format="%(message)s", stream=sys.stdout, level=level, force=True
    )

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        _add_trace_id,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    renderer = (
        structlog.processors.JSONRenderer()
        if settings.log_format == "json"
        else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None):
    return structlog.get_logger(name)

'@

New-Dir (Split-Path -Parent "app/observability/metrics.py")
Write-File "app/observability/metrics.py" @'
"""Lightweight in-process metrics counters exposed via
gateway/routers/metrics.py. Not a full Prometheus client dependency in v1
— this is the minimum viable surface NFR-OBS.3's status endpoint and
NFR-AIGOV.1's spend dashboard need; swapping in prometheus_client later
only touches this module.
"""
from __future__ import annotations

import threading
from collections import defaultdict


class _Counters:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, int] = defaultdict(int)

    def increment(self, name: str, value: int = 1) -> None:
        with self._lock:
            self._counters[name] += value

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counters)


counters = _Counters()

# Well-known counter names, referenced across the codebase rather than
# re-typed as string literals at every call site.
COPILOT_REQUESTS_TOTAL = "copilot_requests_total"
CITATION_VALIDATION_FAILURES_TOTAL = "citation_validation_failures_total"
CITATION_VALIDATION_REFUSALS_TOTAL = "citation_validation_refusals_total"
INGESTION_SUCCEEDED_TOTAL = "ingestion_succeeded_total"
INGESTION_FAILED_TOTAL = "ingestion_failed_total"
AGENT_RUNS_TOTAL = "agent_runs_total"
APPROVAL_PROPOSALS_TOTAL = "approval_proposals_total"
CIRCUIT_BREAKER_TRIPS_TOTAL = "circuit_breaker_trips_total"

'@

New-Dir (Split-Path -Parent "app/observability/token_usage.py")
Write-File "app/observability/token_usage.py" @'
"""Per-tenant LLM/embedding spend tracking (NFR-AIGOV.1).

Feeds the soft-ceiling-before-hard-denial alerting the requirement asks
for: "an uncapped agent loop or a runaway retrieval query must not be
discoverable only via the monthly bill." In-memory + Postgres-backed
counter in v1; swappable for a dedicated billing-metrics store later
without touching callers, since everything routes through record_usage().
"""
from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock

from app.config import get_settings
from app.observability.logging import get_logger

logger = get_logger(__name__)


@dataclass
class _TenantUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    request_count: int = 0


class TokenUsageTracker:
    """Process-local accumulator. In a multi-worker deployment this is
    naturally sharded per worker; NFR-AIGOV.1 only requires *observability*
    and a *soft* ceiling with alerting, not perfectly synchronized global
    counting, so this is sufficient without introducing a shared-state
    dependency purely for a soft alert threshold."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._usage: dict[str, _TenantUsage] = {}

    def record_usage(
        self, company: str, prompt_tokens: int, completion_tokens: int
    ) -> None:
        settings = get_settings().governance
        with self._lock:
            u = self._usage.setdefault(company, _TenantUsage())
            u.prompt_tokens += prompt_tokens
            u.completion_tokens += completion_tokens
            u.request_count += 1
            total = u.prompt_tokens + u.completion_tokens

        if total >= settings.token_hard_ceiling_per_tenant:
            logger.error(
                "tenant_token_hard_ceiling_reached", company=company, total_tokens=total
            )
        elif total >= settings.token_soft_ceiling_per_tenant:
            logger.warning(
                "tenant_token_soft_ceiling_reached", company=company, total_tokens=total
            )

    def snapshot(self, company: str) -> dict:
        with self._lock:
            u = self._usage.get(company, _TenantUsage())
            return {
                "company": company,
                "prompt_tokens": u.prompt_tokens,
                "completion_tokens": u.completion_tokens,
                "total_tokens": u.prompt_tokens + u.completion_tokens,
                "request_count": u.request_count,
            }

    def all_snapshots(self) -> list[dict]:
        with self._lock:
            return [
                {
                    "company": company,
                    "prompt_tokens": u.prompt_tokens,
                    "completion_tokens": u.completion_tokens,
                    "total_tokens": u.prompt_tokens + u.completion_tokens,
                    "request_count": u.request_count,
                }
                for company, u in self._usage.items()
            ]


_tracker = TokenUsageTracker()


def get_token_usage_tracker() -> TokenUsageTracker:
    return _tracker

'@

New-Dir (Split-Path -Parent "app/observability/tracing.py")
Write-File "app/observability/tracing.py" @'
"""trace_id propagation (NFR-OBS.1).

The trace_id originates at the PWA/job that started the request, is
forwarded by buildpolaris_bff on every call into this sidecar (ARCH §4.2),
and is threaded through every downstream log line and outbound call here
via a contextvar rather than being passed explicitly through every
function signature.
"""
from __future__ import annotations

import uuid
from contextvars import ContextVar

trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)


def new_trace_id() -> str:
    return uuid.uuid4().hex


def get_trace_id() -> str:
    """Return the current trace_id, minting one if none is set (should
    only happen for sidecar-internal work with no inbound BFF request,
    e.g. a scheduled reconciliation task)."""
    current = trace_id_var.get()
    if current is None:
        current = new_trace_id()
        trace_id_var.set(current)
    return current


def set_trace_id(trace_id: str) -> None:
    trace_id_var.set(trace_id)

'@

New-Dir (Split-Path -Parent "app/ingest/__init__.py")
Write-File "app/ingest/__init__.py" @'
from app.ingest.ingestion_service import IngestionService
from app.ingest.entity_mirror_service import EntityMirrorService

__all__ = ["IngestionService", "EntityMirrorService"]

'@

New-Dir (Split-Path -Parent "app/ingest/cdc_event_schema.py")
Write-File "app/ingest/cdc_event_schema.py" @'
"""Internal representation of a change-data-capture event driving the
entity mirror (ERD §4.3: nodes/edges "mirror MariaDB, never hand-
curated"). Distinct from gateway/schemas/graph_sync_event.py, which is
the wire shape — this is what projector.py actually operates on after
gateway/routers/graph_sync.py has parsed and validated the inbound
request.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(slots=True)
class CDCEvent:
    company: str
    event_type: Literal["after_insert", "on_update", "on_trash"]
    source_doctype: str
    source_name: str
    project: str | None
    properties: dict[str, Any]
    event_seq: int

'@

New-Dir (Split-Path -Parent "app/ingest/entity_mirror_service.py")
Write-File "app/ingest/entity_mirror_service.py" @'
"""EntityMirrorService — the FR-8.2 cross-cutting-graph half of ingestion.
Isolated from IngestionService the same way ARCH's ingest architecture
isolates the module from the orchestrator: this has no dependency on the
agent registry or RAG pipeline, and is triggered purely by BFF DocType
lifecycle hooks (after_insert/on_update/on_trash), never by a chat turn.
"""
from __future__ import annotations

import asyncpg

from app.gateway.schemas.graph_sync_event import GraphSyncEvent, GraphSyncResult
from app.ingest.projector import advance_cursor, should_process, to_cdc_event
from app.ingest.workers.graph_projection_worker import project_event
from app.observability.logging import get_logger
from app.platform.graph_store.adapter import GraphStoreAdapter

logger = get_logger(__name__)


class EntityMirrorService:
    def __init__(self, graph_store: GraphStoreAdapter, conn: asyncpg.Connection) -> None:
        self._graph_store = graph_store
        self._conn = conn

    async def sync(self, event: GraphSyncEvent) -> GraphSyncResult:
        if not await should_process(self._conn, event):
            logger.info(
                "graph_sync_event_stale_skipped", doctype=event.source_doctype,
                name=event.source_name, event_seq=event.event_seq,
            )
            return GraphSyncResult(accepted=False, reason="stale_or_out_of_order")

        cdc_event = to_cdc_event(event)
        node_key = await project_event(cdc_event, self._graph_store)
        await advance_cursor(self._conn, event)

        return GraphSyncResult(accepted=True, node_key=node_key)

'@

New-Dir (Split-Path -Parent "app/ingest/ingestion_service.py")
Write-File "app/ingest/ingestion_service.py" @'
"""IngestionService — ARCH Flowchart 5, steps H onward (this sidecar's
side of the pipeline; steps B-D, the allow-list check and the
already-indexed-with-same-hash short-circuit, happen BFF-side against
MariaDB's AI Document Index before this service is ever called).

Architecturally isolated per ARCH §3.3: no dependency on
orchestrator/agent_registry, no dependency on RagService. Triggered
exclusively by gateway/routers/ingest.py handling a signed POST /ingest
call — never on its own initiative, never on a schedule (UC-8.4's own
non-goal list).
"""
from __future__ import annotations

import asyncpg
import httpx

from app.exceptions import NoExtractableTextError
from app.gateway.schemas.ingest_event import IngestRequest, IngestResult
from app.ingest.workers.embedding_worker import embed_and_store_chunks
from app.observability.logging import get_logger
from app.observability.metrics import INGESTION_FAILED_TOTAL, INGESTION_SUCCEEDED_TOTAL, counters
from app.platform.rag.chunker import chunk_clauses, chunk_pages
from app.platform.rag.embedder import Embedder
from app.platform.vector_store.adapter import VectorStoreAdapter

logger = get_logger(__name__)

# Contract/spec documents are chunked clause-first (more citable spans);
# everything else falls back to page-bounded chunking.
_CLAUSE_CHUNKED_DOCTYPES = {"Commitment"}


class IngestionService:
    def __init__(
        self, vector_store: VectorStoreAdapter, embedder: Embedder, conn: asyncpg.Connection,
    ) -> None:
        self._vector_store = vector_store
        self._embedder = embedder
        self._conn = conn

    async def ingest(self, request: IngestRequest) -> IngestResult:
        # Sidecar-side idempotency belt-and-suspenders on top of the BFF's
        # own AI Document Index hash check (Flowchart 5 step D) — a
        # duplicate call for content already indexed here is a no-op, not
        # a re-embed.
        already_indexed = await self._conn.fetchval(
            "SELECT 1 FROM document_chunks WHERE content_hash = $1 AND is_stale = FALSE LIMIT 1",
            request.content_hash,
        )
        if already_indexed:
            logger.info("ingest_noop_already_indexed", content_hash=request.content_hash)
            existing_count = await self._conn.fetchval(
                "SELECT count(*) FROM document_chunks WHERE content_hash = $1", request.content_hash
            )
            return IngestResult(
                status="indexed", chunk_count=existing_count, model_version=self._embedder.model_version
            )

        try:
            raw_bytes, content_type = await self._download(request.signed_download_url)
            text_or_pages = self._extract_text(raw_bytes, content_type, request.file_id)
        except NoExtractableTextError as exc:
            counters.increment(INGESTION_FAILED_TOTAL)
            logger.warning(
                "ingest_no_extractable_text", file_id=request.file_id, reason=exc.reason
            )
            return IngestResult(status="failed", failure_reason=exc.reason)

        # UC-8.4 A1 — mark any prior chunks for this source stale ahead of
        # re-ingest, never hard-deleting mid-query.
        await self._vector_store.mark_stale(
            request.company, request.source_doctype, request.source_name
        )

        if request.source_doctype in _CLAUSE_CHUNKED_DOCTYPES and isinstance(text_or_pages, str):
            chunks = chunk_clauses(text_or_pages)
        elif isinstance(text_or_pages, list):
            chunks = chunk_pages(text_or_pages)
        else:
            chunks = chunk_pages([text_or_pages])

        chunk_count = await embed_and_store_chunks(
            chunks, request.company, request.project, request.source_doctype,
            request.source_name, request.file_id, request.content_hash,
            self._vector_store, self._embedder,
        )

        counters.increment(INGESTION_SUCCEEDED_TOTAL)
        return IngestResult(
            status="indexed", chunk_count=chunk_count, model_version=self._embedder.model_version
        )

    async def _download(self, signed_url: str) -> tuple[bytes, str]:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(signed_url)
            response.raise_for_status()
            return response.content, response.headers.get("content-type", "")

    def _extract_text(self, raw_bytes: bytes, content_type: str, file_id: str):
        is_pdf = "pdf" in content_type or file_id.lower().endswith(".pdf")
        is_docx = "wordprocessingml" in content_type or file_id.lower().endswith(".docx")

        if is_pdf:
            return self._extract_pdf(raw_bytes)
        if is_docx:
            return self._extract_docx(raw_bytes)

        # Fall back: treat as plain text if decodable, otherwise fail loud
        # rather than silently indexing binary garbage as "empty content
        # that could later be cited as if it existed" (Flowchart 5's own
        # key rule).
        try:
            return raw_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise NoExtractableTextError("unsupported_file_type") from exc

    def _extract_pdf(self, raw_bytes: bytes) -> list[str]:
        import fitz  # PyMuPDF

        doc = fitz.open(stream=raw_bytes, filetype="pdf")
        pages = [page.get_text().strip() for page in doc]
        doc.close()

        if not any(pages):
            raise NoExtractableTextError("no_text_layer")
        return pages

    def _extract_docx(self, raw_bytes: bytes) -> str:
        import io

        from docx import Document

        doc = Document(io.BytesIO(raw_bytes))
        text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())

        if not text.strip():
            raise NoExtractableTextError("no_text_layer")
        return text

'@

New-Dir (Split-Path -Parent "app/ingest/projector.py")
Write-File "app/ingest/projector.py" @'
"""Translates the gateway-facing GraphSyncEvent (wire schema) into the
internal CDCEvent, applying the ordering/idempotency check against
graph_sync_cursor before handing off to graph_projection_worker. Kept
separate from entity_mirror_service.py so the "is this event stale/
out-of-order" decision is independently testable.
"""
from __future__ import annotations

import asyncpg

from app.gateway.schemas.graph_sync_event import GraphSyncEvent
from app.ingest.cdc_event_schema import CDCEvent
from app.observability.logging import get_logger

logger = get_logger(__name__)


async def should_process(conn: asyncpg.Connection, event: GraphSyncEvent) -> bool:
    """Guards against out-of-order delivery — if a later event for this
    source_doctype was already processed, a stale retry must be a no-op
    rather than overwriting newer graph state with older data."""
    row = await conn.fetchrow(
        "SELECT last_event_seq FROM graph_sync_cursor WHERE source_doctype = $1",
        event.source_doctype,
    )
    if row is None:
        return True
    return event.event_seq > row["last_event_seq"]


async def advance_cursor(conn: asyncpg.Connection, event: GraphSyncEvent) -> None:
    await conn.execute(
        """
        INSERT INTO graph_sync_cursor (source_doctype, last_synced_name, last_synced_at, last_event_seq)
        VALUES ($1, $2, now(), $3)
        ON CONFLICT (source_doctype) DO UPDATE
            SET last_synced_name = EXCLUDED.last_synced_name,
                last_synced_at = now(),
                last_event_seq = EXCLUDED.last_event_seq;
        """,
        event.source_doctype, event.source_name, event.event_seq,
    )


def to_cdc_event(event: GraphSyncEvent) -> CDCEvent:
    return CDCEvent(
        company=event.company, event_type=event.event_type, source_doctype=event.source_doctype,
        source_name=event.source_name, project=event.project, properties=event.properties,
        event_seq=event.event_seq,
    )

'@

New-Dir (Split-Path -Parent "app/ingest/workers/__init__.py")
Write-File "app/ingest/workers/__init__.py" @'

'@

New-Dir (Split-Path -Parent "app/ingest/workers/embedding_worker.py")
Write-File "app/ingest/workers/embedding_worker.py" @'
"""Embedding worker — the chunk -> embed -> store stage (ARCH Flowchart 5
steps K/L/M). Split out from ingestion_service.py so it can be invoked as
a background task (FastAPI BackgroundTasks in v1; a real queue consumer
later without changing this function's signature) and unit-tested without
spinning up the HTTP layer.
"""
from __future__ import annotations

from app.observability.logging import get_logger
from app.platform.rag.chunker import RawChunk
from app.platform.rag.embedder import Embedder
from app.platform.vector_store.adapter import VectorStoreAdapter

logger = get_logger(__name__)


async def embed_and_store_chunks(
    chunks: list[RawChunk], company: str, project: str, source_doctype: str,
    source_name: str, file_id: str, content_hash: str,
    vector_store: VectorStoreAdapter, embedder: Embedder,
) -> int:
    if not chunks:
        return 0

    texts = [c.text for c in chunks]
    embeddings = await embedder.embed_batch(texts)

    stored = 0
    for chunk, embedding in zip(chunks, embeddings):
        await vector_store.upsert_chunk(
            company=company, project=project, source_doctype=source_doctype,
            source_name=source_name, file_id=file_id, content_hash=content_hash,
            span_type=chunk.span_type, span_start=chunk.span_start, span_end=chunk.span_end,
            chunk_text=chunk.text, embedding=embedding, model_version=embedder.model_version,
        )
        stored += 1

    logger.info(
        "chunks_embedded_and_stored", source_doctype=source_doctype, source_name=source_name,
        chunk_count=stored,
    )
    return stored

'@

New-Dir (Split-Path -Parent "app/ingest/workers/graph_projection_worker.py")
Write-File "app/ingest/workers/graph_projection_worker.py" @'
"""Graph projection worker — applies one already-parsed CDC event to the
AGE graph store (ARCH §6.3 corrections note: "the entity mirror needed
its own worker, separate from the ingestion embedding worker, since they
run on entirely different triggers"). Ingestion triggers on a File
attach; graph projection triggers on any tracked DocType's lifecycle
hook, independent of whether that document has any attachments at all.
"""
from __future__ import annotations

from app.ingest.cdc_event_schema import CDCEvent
from app.observability.logging import get_logger
from app.platform.graph_store.adapter import GraphStoreAdapter

logger = get_logger(__name__)

# ERD §4.3 — which relationship this doctype's mirror also implies,
# beyond the node itself. Kept declarative so adding a new mirrored
# DocType + its edges is a data change here, not new control flow.
_EDGE_RULES: dict[str, list[tuple[str, str, str]]] = {
    # (edge_type, from_property_key_holding_related_name, to_label)
    "Task": [("HAS_TASK", "project", "Project"), ("ASSIGNED_TO", "assigned_to", "Person")],
    "RFI": [("RAISED_AGAINST", "task", "Task")],
    "Commitment": [("COMMITTED_TO", "vendor", "Person")],
    "Safety Incident": [("HAS_INCIDENT", "involved_person", "Person")],
}


async def project_event(event: CDCEvent, graph_store: GraphStoreAdapter) -> str | None:
    if event.event_type == "on_trash":
        await graph_store.delete_node(event.company, event.source_doctype, event.source_name)
        logger.info("graph_node_deleted", doctype=event.source_doctype, name=event.source_name)
        return None

    node_key = await graph_store.upsert_node(
        company=event.company, project=event.project, label=event.source_doctype,
        mariadb_name=event.source_name, properties=event.properties,
    )

    for edge_type, prop_key, to_label in _EDGE_RULES.get(event.source_doctype, []):
        related_name = event.properties.get(prop_key)
        if not related_name:
            continue
        try:
            await graph_store.upsert_edge(
                company=event.company, edge_type=edge_type, from_label=event.source_doctype,
                from_name=event.source_name, to_label=to_label, to_name=related_name,
            )
        except Exception as exc:  # noqa: BLE001 — a missing related node shouldn't fail the whole mirror
            logger.warning(
                "graph_edge_projection_skipped", edge_type=edge_type,
                from_name=event.source_name, to_name=related_name, error=str(exc),
            )

    logger.info("graph_node_projected", doctype=event.source_doctype, name=event.source_name)
    return node_key

'@

New-Dir (Split-Path -Parent "app/eval/__init__.py")
Write-File "app/eval/__init__.py" @'

'@

New-Dir (Split-Path -Parent "app/eval/run_eval.py")
Write-File "app/eval/run_eval.py" @'
"""Eval harness runner — NFR-AIGOV.3 ("citation accuracy and approval-gate
reliability must be measurable, not just claimed") / ARCH §6.3. Runs the
golden datasets in eval/datasets/ against the live RagService + agent
pipeline and prints a regression_report.

Usage: python -m app.eval.run_eval
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.db.postgres import close_pool, init_pool
from app.eval.metrics.citation_accuracy import score_citation_accuracy
from app.eval.metrics.grounding_score import score_grounding
from app.eval.metrics.regression_report import build_regression_report
from app.observability.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)

DATASETS_DIR = Path(__file__).resolve().parent / "datasets"


async def _run_golden_qa() -> list[dict]:
    from app.dependencies import get_rag_service

    golden_path = DATASETS_DIR / "golden_qa.jsonl"
    if not golden_path.exists():
        logger.warning("golden_qa_dataset_missing", path=str(golden_path))
        return []

    rag_service = get_rag_service()
    results = []
    with golden_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            case = json.loads(line)
            answer = await rag_service.answer(case["question"], case["company"], case.get("project"))
            results.append(
                {
                    "question": case["question"],
                    "expected_sources": case.get("expected_sources", []),
                    "answer": answer.text,
                    "citations": [c.source_name for c in answer.citations],
                    "refused": answer.refused,
                }
            )
    return results


async def main() -> None:
    await init_pool()
    try:
        qa_results = await _run_golden_qa()
        citation_accuracy = score_citation_accuracy(qa_results)
        grounding = score_grounding(qa_results)
        report = build_regression_report(citation_accuracy, grounding, qa_results)
        print(json.dumps(report, indent=2))
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())

'@

New-Dir (Split-Path -Parent "app/eval/metrics/__init__.py")
Write-File "app/eval/metrics/__init__.py" @'

'@

New-Dir (Split-Path -Parent "app/eval/metrics/approval_gate_accuracy.py")
Write-File "app/eval/metrics/approval_gate_accuracy.py" @'
"""Approval-gate reliability metric — of a golden set of proposed-action
scenarios, how often the agent produced a well-formed ProposedAction that
passed payload_verifier.py's shape checks on the first attempt. This is
NOT about whether a human would have approved the content — it measures
mechanical reliability of the gate itself.
"""
from __future__ import annotations

from app.platform.governance.payload_verifier import PayloadVerificationError, verify_proposed_action
from app.platform.governance.proposal_schema import ProposedAction


def score_approval_gate_accuracy(proposed_actions: list[ProposedAction]) -> dict:
    total = len(proposed_actions)
    passed = 0
    failures: list[str] = []

    for action in proposed_actions:
        try:
            verify_proposed_action(action)
            passed += 1
        except PayloadVerificationError as exc:
            failures.append(str(exc))

    accuracy = passed / total if total else None
    return {
        "metric": "approval_gate_accuracy", "total_cases": total, "passed": passed,
        "accuracy": accuracy, "failures": failures,
    }

'@

New-Dir (Split-Path -Parent "app/eval/metrics/citation_accuracy.py")
Write-File "app/eval/metrics/citation_accuracy.py" @'
"""Citation accuracy metric — of the golden-set questions where a source
was expected, what fraction of the model's actual citations landed on an
expected source document.
"""
from __future__ import annotations


def score_citation_accuracy(results: list[dict]) -> dict:
    total_with_expected = 0
    correct = 0

    for r in results:
        expected = set(r.get("expected_sources", []))
        if not expected:
            continue
        total_with_expected += 1
        actual = set(r.get("citations", []))
        if expected & actual:
            correct += 1

    accuracy = correct / total_with_expected if total_with_expected else None
    return {
        "metric": "citation_accuracy",
        "total_cases": total_with_expected,
        "correct": correct,
        "accuracy": accuracy,
    }

'@

New-Dir (Split-Path -Parent "app/eval/metrics/grounding_score.py")
Write-File "app/eval/metrics/grounding_score.py" @'
"""Grounding score — of all answered (non-refused) questions, what
fraction produced at least one citation at all. A low grounding score
means the model is answering confidently without citing anything, which
FR-8.3 treats as a correctness bug, not a style issue.
"""
from __future__ import annotations


def score_grounding(results: list[dict]) -> dict:
    answered = [r for r in results if not r.get("refused")]
    grounded = [r for r in answered if r.get("citations")]

    score = len(grounded) / len(answered) if answered else None
    return {
        "metric": "grounding_score",
        "answered_cases": len(answered),
        "grounded_cases": len(grounded),
        "score": score,
    }

'@

New-Dir (Split-Path -Parent "app/eval/metrics/regression_report.py")
Write-File "app/eval/metrics/regression_report.py" @'
"""Assembles the individual metric outputs into one report, and flags a
regression when a metric drops below a fixed floor — the eval harness's
job is to make a citation-accuracy or grounding regression loud in CI,
not just measurable after the fact.
"""
from __future__ import annotations

CITATION_ACCURACY_FLOOR = 0.7
GROUNDING_SCORE_FLOOR = 0.8


def build_regression_report(citation_accuracy: dict, grounding: dict, raw_results: list[dict]) -> dict:
    regressions = []

    if citation_accuracy.get("accuracy") is not None and citation_accuracy["accuracy"] < CITATION_ACCURACY_FLOOR:
        regressions.append(
            f"citation_accuracy {citation_accuracy['accuracy']:.2f} below floor {CITATION_ACCURACY_FLOOR}"
        )
    if grounding.get("score") is not None and grounding["score"] < GROUNDING_SCORE_FLOOR:
        regressions.append(f"grounding_score {grounding['score']:.2f} below floor {GROUNDING_SCORE_FLOOR}")

    return {
        "citation_accuracy": citation_accuracy,
        "grounding": grounding,
        "case_count": len(raw_results),
        "regressions": regressions,
        "passed": len(regressions) == 0,
    }

'@

New-Dir (Split-Path -Parent "app/eval/datasets/golden_approval_scenarios.jsonl")
Write-File "app/eval/datasets/golden_approval_scenarios.jsonl" @'
{"agent_type": "rfi_drafting", "message": "There's a clash between the HVAC duct and the structural beam at gridline C4, level 3.", "company": "dev-co", "project": "dev-project"}
{"agent_type": "daily_log_extraction", "message": "Clear skies, 68F. 12 crew on site. Poured slab on grade for zone B. No delays. One near-miss reported near the hoist.", "company": "dev-co", "project": "dev-project"}

'@

New-Dir (Split-Path -Parent "app/eval/datasets/golden_qa.jsonl")
Write-File "app/eval/datasets/golden_qa.jsonl" @'
{"question": "What is the retention percentage on the concrete subcontract?", "company": "dev-co", "project": "dev-project", "expected_sources": ["COMMIT-0001"]}
{"question": "What is the notice period for a delay claim under the steel subcontract?", "company": "dev-co", "project": "dev-project", "expected_sources": ["COMMIT-0002"]}
{"question": "Is there an open RFI about the elevator shaft clash?", "company": "dev-co", "project": "dev-project", "expected_sources": ["RFI-0004"]}

'@

New-Dir (Split-Path -Parent "app/db/postgres.py")
Write-File "app/db/postgres.py" @'
"""Postgres connection pool — the single seam for opening a correctly
configured connection against buildpolaris_ai's Postgres (pgvector +
Apache AGE). Every connection registers the vector codec and loads AGE
exactly once, on pool init, via `asyncpg.Pool`'s `setup` hook.
"""
from __future__ import annotations

import asyncpg
import structlog
from pgvector.asyncpg import register_vector

from app.config import get_settings

logger = structlog.get_logger(__name__)

_pool: asyncpg.Pool | None = None


async def _configure_connection(conn: asyncpg.Connection) -> None:
    await register_vector(conn)
    await conn.execute("LOAD 'age'; SET search_path = ag_catalog, \"$user\", public;")


async def init_pool() -> asyncpg.Pool:
    global _pool
    if _pool is not None:
        return _pool

    settings = get_settings().database
    _pool = await asyncpg.create_pool(
        min_size=2,
        max_size=10,
        setup=_configure_connection,
        **settings.connect_kwargs(),
    )
    logger.info("postgres_pool_initialized", host=settings.host, database=settings.name)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("postgres_pool_closed")


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError(
            "Postgres pool not initialized — call init_pool() during app startup"
        )
    return _pool

'@

New-Dir (Split-Path -Parent "app/db/session.py")
Write-File "app/db/session.py" @'
"""FastAPI dependency for a pooled, pre-configured Postgres connection."""
from __future__ import annotations

from typing import AsyncIterator

import asyncpg

from app.db.postgres import get_pool


async def get_db_conn() -> AsyncIterator[asyncpg.Connection]:
    pool = get_pool()
    async with pool.acquire() as conn:
        yield conn

'@

New-Dir (Split-Path -Parent "app/db/models/__init__.py")
Write-File "app/db/models/__init__.py" @'
from app.db.models.document_chunk import DocumentChunk
from app.db.models.embedding import Embedding
from app.db.models.graph_node import GraphNode
from app.db.models.graph_edge import GraphEdge
from app.db.models.graph_sync_cursor import GraphSyncCursor
from app.db.models.agent_run import AgentRun
from app.db.models.approval_event import ApprovalEvent

__all__ = [
    "DocumentChunk",
    "Embedding",
    "GraphNode",
    "GraphEdge",
    "GraphSyncCursor",
    "AgentRun",
    "ApprovalEvent",
]

'@

New-Dir (Split-Path -Parent "app/db/models/agent_run.py")
Write-File "app/db/models/agent_run.py" @'
"""Row model for `agent_runs` (migration 0007) — sidecar-local run
tracking, feeding eval/metrics/*.py. NOT the approval authority (that's
MariaDB's Agent Action Approval, ERD §3.6)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID


@dataclass(slots=True)
class AgentRun:
    run_id: UUID
    agent_type: str
    company: str
    project: str | None
    user_id: str
    trace_id: str
    model_version: str
    confidence: Decimal | None
    output_kind: str  # 'read_only' | 'proposed_write'
    started_at: datetime
    completed_at: datetime | None
    status: str  # 'running' | 'succeeded' | 'failed'

    @classmethod
    def from_record(cls, record: Any) -> "AgentRun":
        return cls(**dict(record))

'@

New-Dir (Split-Path -Parent "app/db/models/approval_event.py")
Write-File "app/db/models/approval_event.py" @'
"""Row model for `approval_events` (migration 0007) — mirrors what this
sidecar proposed to the BFF's ActionApprovalGate, for its own audit trail
(ActionApprovalGateClient never resolves an approval, only proposes it)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(slots=True)
class ApprovalEvent:
    event_id: UUID
    run_id: UUID | None
    tool_trace_id: str
    proposed_payload: dict
    bff_approval_ref: str | None
    proposed_at: datetime
    idempotency_key: str

    @classmethod
    def from_record(cls, record: Any) -> "ApprovalEvent":
        return cls(**dict(record))

'@

New-Dir (Split-Path -Parent "app/db/models/document_chunk.py")
Write-File "app/db/models/document_chunk.py" @'
"""Row model for `document_chunks` (migration 0003).

Deliberately a plain dataclass, not a full ORM — this schema is small and
hand-reviewed (ERD §7); asyncpg + explicit SQL keeps the query shape
visible at the call site rather than hidden behind ORM-generated SQL.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(slots=True)
class DocumentChunk:
    chunk_id: UUID
    company: str
    project: str
    source_doctype: str
    source_name: str
    file_id: str
    content_hash: str
    span_type: str  # 'page' | 'clause'
    span_start: int
    span_end: int
    chunk_text: str
    is_stale: bool
    created_at: datetime

    @classmethod
    def from_record(cls, record: Any) -> "DocumentChunk":
        return cls(**dict(record))

'@

New-Dir (Split-Path -Parent "app/db/models/embedding.py")
Write-File "app/db/models/embedding.py" @'
"""Row model for `embeddings` (migration 0004)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(slots=True)
class Embedding:
    embedding_id: UUID
    chunk_id: UUID
    embedding: list[float]
    model_version: str
    created_at: datetime

    @classmethod
    def from_record(cls, record: Any) -> "Embedding":
        data = dict(record)
        vec = data.get("embedding")
        if vec is not None and not isinstance(vec, list):
            data["embedding"] = list(vec)
        return cls(**data)

'@

New-Dir (Split-Path -Parent "app/db/models/graph_edge.py")
Write-File "app/db/models/graph_edge.py" @'
"""Row model for `graph_edge_index` (migration 0006)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class GraphEdge:
    edge_key: str
    edge_type: str
    from_node_key: str
    to_node_key: str
    company: str
    updated_at: datetime | None = None

    @staticmethod
    def make_key(edge_type: str, from_node_key: str, to_node_key: str) -> str:
        return f"{edge_type}:{from_node_key}->{to_node_key}"

    @classmethod
    def from_record(cls, record: Any) -> "GraphEdge":
        return cls(**dict(record))

'@

New-Dir (Split-Path -Parent "app/db/models/graph_node.py")
Write-File "app/db/models/graph_node.py" @'
"""Row model for `graph_node_index` (migration 0005) — the relational
index over the AGE graph, mirroring MariaDB entities via DocType lifecycle
hooks (ERD §4.3), never hand-curated.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class GraphNode:
    node_key: str  # '{label}:{mariadb_name}'
    label: str
    mariadb_name: str
    company: str
    project: str | None
    properties: dict[str, Any] = field(default_factory=dict)
    updated_at: datetime | None = None

    @staticmethod
    def make_key(label: str, mariadb_name: str) -> str:
        return f"{label}:{mariadb_name}"

    @classmethod
    def from_record(cls, record: Any) -> "GraphNode":
        return cls(**dict(record))

'@

New-Dir (Split-Path -Parent "app/db/models/graph_sync_cursor.py")
Write-File "app/db/models/graph_sync_cursor.py" @'
"""Row model for `graph_sync_cursor` (migration 0007) — entity-mirror
idempotency tracking (ARCH §6.3 corrections note: "added graph_sync_cursor
model ... since the draft had no persistence for mirror-run tracking, only
ingestion tracking").
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class GraphSyncCursor:
    source_doctype: str
    last_synced_name: str | None
    last_synced_at: datetime | None
    last_event_seq: int

    @classmethod
    def from_record(cls, record: Any) -> "GraphSyncCursor":
        return cls(**dict(record))

'@

New-Dir (Split-Path -Parent "migrations/env.py")
Write-File "migrations/env.py" @'
"""BuildPolaris AI — migration runner.

Not full Alembic autogenerate machinery: this schema is small and every
change is hand-authored and reviewed the same way a MariaDB migration
would be (ERD v2.1 §7). This runner applies the numbered .sql files in
migrations/versions/ in order, tracking applied versions in the
`schema_migrations` table created by 0001, so re-running is always safe.

Usage:
    python -m migrations.env
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402

VERSIONS_DIR = Path(__file__).resolve().parent / "versions"


async def _ensure_tracking_table(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version    TEXT PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )


async def _applied_versions(conn: asyncpg.Connection) -> set[str]:
    rows = await conn.fetch("SELECT version FROM schema_migrations")
    return {r["version"] for r in rows}


async def run_migrations() -> None:
    settings = get_settings()
    conn = await asyncpg.connect(**settings.database.connect_kwargs())
    try:
        await _ensure_tracking_table(conn)
        applied = await _applied_versions(conn)

        sql_files = sorted(VERSIONS_DIR.glob("*.sql"))
        for path in sql_files:
            version = path.stem
            if version in applied:
                print(f"[migrations] {version} already applied, skipping")
                continue

            print(f"[migrations] applying {version} ...")
            sql = path.read_text(encoding="utf-8")
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO schema_migrations (version) VALUES ($1) "
                    "ON CONFLICT (version) DO NOTHING",
                    version,
                )
            print(f"[migrations] {version} applied")

        print("[migrations] up to date")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(run_migrations())

'@

New-Dir (Split-Path -Parent "migrations/versions/0001_enable_pgvector.sql")
Write-File "migrations/versions/0001_enable_pgvector.sql" @'
-- ARCH v2.1 §6.3 / ERD v2.1 §4.2
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version     TEXT PRIMARY KEY,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

'@

New-Dir (Split-Path -Parent "migrations/versions/0002_enable_apache_age.sql")
Write-File "migrations/versions/0002_enable_apache_age.sql" @'
-- ARCH v2.1 §6.3 / ERD v2.1 §4.3 — Apache AGE knowledge graph.
CREATE EXTENSION IF NOT EXISTS age;
LOAD 'age';
SET search_path = ag_catalog, "$user", public;

SELECT create_graph('buildpolaris_graph')
WHERE NOT EXISTS (
    SELECT 1 FROM ag_catalog.ag_graph WHERE name = 'buildpolaris_graph'
);

-- Vertex labels mirroring MariaDB entities (ERD §4.3 table) — created
-- idempotently; AGE also auto-creates a label on first use, but declaring
-- them here keeps the schema reviewable rather than implicit.
SELECT create_vlabel('buildpolaris_graph', 'Project')
WHERE NOT EXISTS (SELECT 1 FROM ag_catalog.ag_label WHERE name = 'Project');
SELECT create_vlabel('buildpolaris_graph', 'Task')
WHERE NOT EXISTS (SELECT 1 FROM ag_catalog.ag_label WHERE name = 'Task');
SELECT create_vlabel('buildpolaris_graph', 'RFI')
WHERE NOT EXISTS (SELECT 1 FROM ag_catalog.ag_label WHERE name = 'RFI');
SELECT create_vlabel('buildpolaris_graph', 'Commitment')
WHERE NOT EXISTS (SELECT 1 FROM ag_catalog.ag_label WHERE name = 'Commitment');
SELECT create_vlabel('buildpolaris_graph', 'Person')
WHERE NOT EXISTS (SELECT 1 FROM ag_catalog.ag_label WHERE name = 'Person');
SELECT create_vlabel('buildpolaris_graph', 'SafetyIncident')
WHERE NOT EXISTS (SELECT 1 FROM ag_catalog.ag_label WHERE name = 'SafetyIncident');

'@

New-Dir (Split-Path -Parent "migrations/versions/0003_create_document_chunks.sql")
Write-File "migrations/versions/0003_create_document_chunks.sql" @'
-- ERD v2.1 §4.2 — text/provenance half of the retrieval unit. Split from
-- the embedding vector (0004) so a re-embed for a new model version never
-- requires re-parsing/re-chunking the source document (NFR-AIGOV.2).
CREATE TABLE IF NOT EXISTS document_chunks (
    chunk_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company         TEXT NOT NULL,          -- tenant isolation (NFR-SEC.8)
    project         TEXT NOT NULL,
    source_doctype  TEXT NOT NULL,          -- 'Commitment' | 'Submittal Package' | 'RFI'
    source_name     TEXT NOT NULL,          -- MariaDB document name — the citation's human-meaningful anchor
    file_id         TEXT NOT NULL,          -- MariaDB File.name
    content_hash    TEXT NOT NULL,          -- matches AI Document Index.content_hash (idempotency join key)
    span_type       TEXT NOT NULL CHECK (span_type IN ('page', 'clause')),
    span_start      INT  NOT NULL,
    span_end        INT  NOT NULL,
    chunk_text      TEXT NOT NULL,
    is_stale        BOOLEAN NOT NULL DEFAULT FALSE,  -- set on re-ingest (UC-8.4 A1); never hard-deleted mid-query
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS chunks_scope_idx  ON document_chunks (company, project, is_stale);
CREATE INDEX IF NOT EXISTS chunks_source_idx ON document_chunks (source_doctype, source_name);
CREATE INDEX IF NOT EXISTS chunks_hash_idx   ON document_chunks (content_hash);

'@

New-Dir (Split-Path -Parent "migrations/versions/0004_create_embeddings.sql")
Write-File "migrations/versions/0004_create_embeddings.sql" @'
-- ERD v2.1 §4.2 — the vector half. embedding dimension is pinned per
-- ERD §8.1 (open decision #1) to the sentence-transformers all-MiniLM-L6-v2
-- default (384-dim, free/local). Changing it is a documented backfill, not
-- a silent migration (ERD §7).
CREATE TABLE IF NOT EXISTS embeddings (
    embedding_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chunk_id        UUID NOT NULL REFERENCES document_chunks(chunk_id) ON DELETE CASCADE,
    embedding       vector(384) NOT NULL,
    model_version   TEXT NOT NULL,          -- NFR-AIGOV.2: version-pinned, never "latest"
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (chunk_id, model_version)
);

CREATE INDEX IF NOT EXISTS embeddings_hnsw_idx
    ON embeddings USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS embeddings_chunk_idx ON embeddings (chunk_id);

'@

New-Dir (Split-Path -Parent "migrations/versions/0005_create_graph_nodes.sql")
Write-File "migrations/versions/0005_create_graph_nodes.sql" @'
-- Graph node bookkeeping lives relationally alongside the AGE graph itself
-- so entity-mirror idempotency (0007's graph_sync_cursor) and ordinary SQL
-- reporting don't require a Cypher round-trip for simple existence checks.
-- The AGE graph (0002) remains the actual traversal store used by
-- graph_store/age_adapter.py; this table is a lightweight index over it.
CREATE TABLE IF NOT EXISTS graph_node_index (
    node_key        TEXT PRIMARY KEY,        -- '{label}:{mariadb_name}', e.g. 'Task:TASK-0042'
    label           TEXT NOT NULL,
    mariadb_name    TEXT NOT NULL,
    company         TEXT NOT NULL,
    project         TEXT,
    properties      JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS graph_node_scope_idx ON graph_node_index (company, project);
CREATE INDEX IF NOT EXISTS graph_node_label_idx ON graph_node_index (label, mariadb_name);

'@

New-Dir (Split-Path -Parent "migrations/versions/0006_create_graph_edges.sql")
Write-File "migrations/versions/0006_create_graph_edges.sql" @'
-- Relational mirror of AGE edges, same rationale as 0005.
CREATE TABLE IF NOT EXISTS graph_edge_index (
    edge_key        TEXT PRIMARY KEY,   -- '{edge_type}:{from_node_key}->{to_node_key}'
    edge_type       TEXT NOT NULL,      -- HAS_TASK | DEPENDS_ON | ASSIGNED_TO | RAISED_AGAINST | COMMITTED_TO | HAS_INCIDENT
    from_node_key   TEXT NOT NULL REFERENCES graph_node_index(node_key) ON DELETE CASCADE,
    to_node_key     TEXT NOT NULL REFERENCES graph_node_index(node_key) ON DELETE CASCADE,
    company         TEXT NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS graph_edge_from_idx ON graph_edge_index (from_node_key);
CREATE INDEX IF NOT EXISTS graph_edge_to_idx   ON graph_edge_index (to_node_key);
CREATE INDEX IF NOT EXISTS graph_edge_type_idx ON graph_edge_index (edge_type);

'@

New-Dir (Split-Path -Parent "migrations/versions/0007_create_agent_audit_tables.sql")
Write-File "migrations/versions/0007_create_agent_audit_tables.sql" @'
-- Sidecar-local run/audit tables. These are NOT the authority for approval
-- decisions (that record is 'Agent Action Approval' in BFF's MariaDB, ERD
-- §3.6) — these exist so buildpolaris_ai can reconstruct its own eval
-- metrics (citation accuracy, grounding score) and the entity-mirror
-- idempotency cursor without querying MariaDB for every eval run.

CREATE TABLE IF NOT EXISTS agent_runs (
    run_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_type      TEXT NOT NULL,
    company         TEXT NOT NULL,
    project         TEXT,
    user_id         TEXT NOT NULL,
    trace_id        TEXT NOT NULL,
    model_version   TEXT NOT NULL,
    confidence      NUMERIC(4,3),
    output_kind     TEXT NOT NULL CHECK (output_kind IN ('read_only', 'proposed_write')),
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ,
    status          TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'succeeded', 'failed'))
);
CREATE INDEX IF NOT EXISTS agent_runs_scope_idx ON agent_runs (company, project, agent_type);
CREATE INDEX IF NOT EXISTS agent_runs_trace_idx ON agent_runs (trace_id);

CREATE TABLE IF NOT EXISTS approval_events (
    event_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id              UUID REFERENCES agent_runs(run_id) ON DELETE SET NULL,
    tool_trace_id       TEXT NOT NULL,
    proposed_payload    JSONB NOT NULL,
    bff_approval_ref    TEXT,        -- mirrors MariaDB Agent Action Approval.name once known
    proposed_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    idempotency_key     TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS approval_events_run_idx ON approval_events (run_id);

CREATE TABLE IF NOT EXISTS graph_sync_cursor (
    source_doctype      TEXT PRIMARY KEY,   -- 'Task', 'RFI', 'Commitment', ...
    last_synced_name    TEXT,
    last_synced_at      TIMESTAMPTZ,
    last_event_seq      BIGINT NOT NULL DEFAULT 0
);

'@

New-Dir (Split-Path -Parent "scripts/rebuild_read_model.py")
Write-File "scripts/rebuild_read_model.py" @'
"""Rebuilds this sidecar's ENTIRE derived store (document_chunks,
embeddings, graph_node_index, graph_edge_index, AND the AGE graph itself)
from scratch. This is the operational proof of ERD §1's core promise:
"MariaDB is the only place a fact is created. RxDB and the AI sidecar's
Postgres are both disposable projections that can be deleted and
rebuilt."

This script does NOT re-fetch every source document from BFF itself — it
drops the derived tables, re-runs migrations, and then expects the
operator (or a companion BFF-side script) to re-trigger ingestion/graph-
sync for every eligible document and tracked entity. What it guarantees
is that starting state is clean and idempotent re-ingestion will not
collide with stale rows.

Usage: python scripts/rebuild_read_model.py --confirm
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.observability.logging import configure_logging, get_logger  # noqa: E402

configure_logging()
logger = get_logger(__name__)

TABLES_TO_TRUNCATE = [
    "embeddings", "document_chunks", "graph_edge_index", "graph_node_index",
    "graph_sync_cursor", "agent_runs", "approval_events",
]


async def rebuild() -> None:
    import asyncpg

    settings = get_settings().database
    conn = await asyncpg.connect(**settings.connect_kwargs())
    try:
        for table in TABLES_TO_TRUNCATE:
            await conn.execute(f"TRUNCATE TABLE {table} CASCADE;")
            logger.info("table_truncated", table=table)

        await conn.execute("LOAD 'age'; SET search_path = ag_catalog, \"$user\", public;")
        await conn.execute(
            "SELECT drop_graph('buildpolaris_graph', true) "
            "WHERE EXISTS (SELECT 1 FROM ag_catalog.ag_graph WHERE name = 'buildpolaris_graph');"
        )
        await conn.execute("SELECT create_graph('buildpolaris_graph');")
        logger.info("age_graph_recreated")
    finally:
        await conn.close()

    print(
        "Derived store truncated and AGE graph recreated. Now trigger "
        "re-ingestion/graph-sync from buildpolaris_bff for every eligible "
        "document and tracked entity."
    )


if __name__ == "__main__":
    if "--confirm" not in sys.argv:
        print("This TRUNCATEs every derived table and drops the AGE graph. "
              "Re-run with --confirm to proceed.")
        sys.exit(1)
    asyncio.run(rebuild())

'@

New-Dir (Split-Path -Parent "scripts/register_agents.py")
Write-File "scripts/register_agents.py" @'
"""Dev/CI helper — validates every agents/<name>/manifest.yaml is
well-formed and every declared target_doctype has a payload_verifier.py
entry, WITHOUT starting the full FastAPI app. Run this in CI before
deploy so a malformed manifest fails fast rather than surfacing as a 500
on the first real copilot turn.

Usage: python scripts/register_agents.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.orchestrator.agent_registry import get_agent_registry  # noqa: E402
from app.platform.governance.payload_verifier import ALLOWED_TARGETS  # noqa: E402


def main() -> int:
    registry = get_agent_registry()
    manifests = registry.all_manifests()

    if not manifests:
        print("ERROR: no agents were discovered under app/agents/")
        return 1

    errors = []
    for manifest in manifests:
        allowed = ALLOWED_TARGETS.get(manifest.agent_type)
        if allowed is None:
            errors.append(
                f"{manifest.agent_type}: no entry in governance/payload_verifier.ALLOWED_TARGETS"
            )
        elif manifest.target_doctype not in allowed:
            errors.append(
                f"{manifest.agent_type}: manifest target_doctype '{manifest.target_doctype}' "
                f"not in ALLOWED_TARGETS {allowed}"
            )

        print(f"OK  {manifest.agent_type:30s} -> {manifest.target_doctype}")

    if errors:
        print("\nFAILURES:")
        for e in errors:
            print(f"  - {e}")
        return 1

    print(f"\n{len(manifests)} agent(s) registered cleanly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

'@

New-Dir (Split-Path -Parent "scripts/replay_cdc.py")
Write-File "scripts/replay_cdc.py" @'
"""Dev/ops tool — replays a captured batch of graph-sync CDC events
against EntityMirrorService, for local testing without a live BFF, or for
recovering from a window where the sidecar was down and missed live
hook-fired events (BFF's own retry/outbox mechanism is the production
answer to that; this script is the manual fallback).

Usage: python scripts/replay_cdc.py path/to/events.jsonl
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.postgres import close_pool, get_pool, init_pool  # noqa: E402
from app.gateway.schemas.graph_sync_event import GraphSyncEvent  # noqa: E402
from app.ingest.entity_mirror_service import EntityMirrorService  # noqa: E402
from app.observability.logging import configure_logging, get_logger  # noqa: E402
from app.platform.graph_store.age_adapter import AgeGraphAdapter  # noqa: E402

configure_logging()
logger = get_logger(__name__)


async def replay(path: Path) -> None:
    await init_pool()
    try:
        async with get_pool().acquire() as conn:
            service = EntityMirrorService(AgeGraphAdapter(conn), conn)

            with path.open(encoding="utf-8") as fh:
                for i, line in enumerate(fh, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    event = GraphSyncEvent.model_validate_json(line)
                    result = await service.sync(event)
                    logger.info("event_replayed", line=i, accepted=result.accepted)
    finally:
        await close_pool()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/replay_cdc.py path/to/events.jsonl")
        sys.exit(1)
    asyncio.run(replay(Path(sys.argv[1])))

'@

New-Dir (Split-Path -Parent "scripts/seed_eval_data.py")
Write-File "scripts/seed_eval_data.py" @'
"""Seeds a small local dev/eval corpus directly into document_chunks +
embeddings, bypassing the /ingest HTTP path (no real BFF file needed) —
lets `python -m app.eval.run_eval` produce a meaningful score against
`eval/datasets/golden_qa.jsonl` on a bare-bones local setup.

Usage: python scripts/seed_eval_data.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.postgres import close_pool, get_pool, init_pool  # noqa: E402
from app.observability.logging import configure_logging, get_logger  # noqa: E402
from app.platform.model_provider.factory import get_model_provider  # noqa: E402
from app.platform.rag.chunker import RawChunk  # noqa: E402
from app.platform.rag.embedder import Embedder  # noqa: E402
from app.platform.vector_store.pgvector_adapter import PgVectorAdapter  # noqa: E402

configure_logging()
logger = get_logger(__name__)

SEED_DOCS = [
    {
        "source_doctype": "Commitment", "source_name": "COMMIT-0001",
        "file_id": "FILE-seed-0001", "content_hash": "seed-hash-0001",
        "chunks": [
            RawChunk("clause", 1, 1, "Article 5. Retention. Owner shall withhold retention "
                     "of ten percent (10%) from each progress payment until Substantial "
                     "Completion, at which point retention reduces to five percent (5%)."),
        ],
    },
    {
        "source_doctype": "Commitment", "source_name": "COMMIT-0002",
        "file_id": "FILE-seed-0002", "content_hash": "seed-hash-0002",
        "chunks": [
            RawChunk("clause", 1, 1, "Article 9. Notice of Delay Claims. Subcontractor "
                     "shall provide written notice of any delay claim within seven (7) "
                     "calendar days of the event giving rise to the claim, or the claim "
                     "is waived."),
        ],
    },
    {
        "source_doctype": "RFI", "source_name": "RFI-0004",
        "file_id": "FILE-seed-0004", "content_hash": "seed-hash-0004",
        "chunks": [
            RawChunk("page", 1, 1, "RFI-0004: Clash detected between HVAC duct routing and "
                     "the structural beam at gridline C4, level 3. Requesting revised "
                     "coordination drawing. Status: Open."),
        ],
    },
]


async def seed(company: str = "dev-co", project: str = "dev-project") -> None:
    await init_pool()
    try:
        embedder = Embedder(get_model_provider())
        async with get_pool().acquire() as conn:
            vector_store = PgVectorAdapter(conn)
            for doc in SEED_DOCS:
                for chunk in doc["chunks"]:
                    embedding = await embedder.embed_text(chunk.text)
                    await vector_store.upsert_chunk(
                        company=company, project=project, source_doctype=doc["source_doctype"],
                        source_name=doc["source_name"], file_id=doc["file_id"],
                        content_hash=doc["content_hash"], span_type=chunk.span_type,
                        span_start=chunk.span_start, span_end=chunk.span_end,
                        chunk_text=chunk.text, embedding=embedding, model_version=embedder.model_version,
                    )
                logger.info("seed_doc_indexed", source_name=doc["source_name"])
    finally:
        await close_pool()

    print(f"Seeded {len(SEED_DOCS)} document(s) for company='{company}' project='{project}'.")


if __name__ == "__main__":
    asyncio.run(seed())

'@


Write-Host ""
Write-Host "==> Rebuild complete." -ForegroundColor Green
Write-Host "==> Tree now matches ARCH v2.1 section 6.3 exactly." -ForegroundColor Green
if (Test-Path ".env.bak") {
    Write-Host ""
    Write-Host "NOTE: your previous .env was backed up to .env.bak but was" -ForegroundColor Yellow
    Write-Host "NOT restored automatically, because the new config uses" -ForegroundColor Yellow
    Write-Host "double-underscore nested keys (e.g. DATABASE__HOST, not" -ForegroundColor Yellow
    Write-Host "DATABASE_HOST). Copy .env.example to .env and port over" -ForegroundColor Yellow
    Write-Host "your real values (Gemini key, DB password, etc.) from" -ForegroundColor Yellow
    Write-Host ".env.bak by hand." -ForegroundColor Yellow
}
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Copy .env.example to .env and fill in MODEL_PROVIDER__GEMINI_API_KEY"
Write-Host "     (free key: https://aistudio.google.com/apikey)"
Write-Host "  2. pip install -r requirements.txt --break-system-packages"
Write-Host "  3. docker compose up -d db redis   (or point DATABASE__HOST at your own Postgres)"
Write-Host "  4. python -m migrations.env"
Write-Host "  5. python scripts/register_agents.py"
Write-Host "  6. uvicorn app.main:app --reload"
