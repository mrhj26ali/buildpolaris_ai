# Phase 0 — As-Built vs As-Designed Architecture

This diagram makes the gap between what exists after Phase 0 and the full
target architecture (`buildpolaris_full_architecture.md` §4) explicit, so the
remaining work is visible rather than assumed.

```mermaid
flowchart TB
    subgraph BUILT["✅ BUILT — Phase 0 complete"]
        CONFIG["platform/config.py<br/>pydantic-settings single source"]
        SCHEMAS["platform/schemas.py<br/>CDCEvent / Gate / UserContext"]
        BFFPORT["platform/bff_client.py + bff_mock.py<br/>hexagonal BFF port"]
        MODELP["platform/model_provider/<br/>factory + instructor adapter<br/>(config-selected provider)"]
        RETRIEVAL["platform/retrieval/<br/>pgvector + AGE adapters<br/>parameterized + tenant-scoped"]
        CITATION["platform/retrieval/citation_validator.py"]
        WORKER["workers/graph_sync_worker.py<br/>CDC → embed → vector + graph"]
        HARNESS["tests/ + .github/workflows/ci.yml<br/>unit / integration / security + CI"]
    end

    subgraph PLANNED["🔲 PLANNED — Phases 1–7"]
        AGENTS["agents/<br/>rfi_drafting · voice · clause · onboarding"]
        ORCH["gateway/orchestrator/<br/>agent_registry · turn_runner"]
        GATEWAY["gateway/api/<br/>chat · agents endpoints"]
        GOV["platform/governance/<br/>approval_gate · risk_tiers · budget_meter"]
        MCP["platform/mcp/<br/>tool_registry (allow-listed)"]
        OBS["platform/observability/<br/>tracing · eval_runner"]
        EVAL["eval/golden_sets/<br/>CI-gated quality thresholds"]
    end

    BUILT -.->|"foundations hardening done<br/>build features on top"| PLANNED

    style BUILT fill:#e8f5e9,stroke:#1b5e20
    style PLANNED fill:#fff3e0,stroke:#e65100
```

## CI flow

```mermaid
flowchart LR
    PR["Pull Request"] --> Q["quality job<br/>ruff + bandit"]
    PR --> TF["test-fast job<br/>unit + security + coverage"]
    TF --> TI["test-integration job<br/>build AGE db → integration tests"]
    Q --> GATE{"all green?"}
    TF --> GATE
    TI --> GATE
    GATE -->|yes| MERGE["merge to main"]
    GATE -->|no| FIX["fix & re-push"]
```

## Local dev loop (§3.4)

| Command | What runs | When |
|---|---|---|
| `uv run pytest -m unit` | unit tests only (seconds) | inner loop |
| `uv run pytest -m "unit or security"` | + adversarial/boundary tests | pre-commit |
| `uv run pytest -m integration` | containerized AGE+pgvector tests | pre-merge (needs DB up) |
| `uv run pytest -m "unit or integration or security"` | full suite | CI parity |