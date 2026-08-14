-- Sidecar-local run/audit tables. These are NOT the authority for approval
-- decisions (that record is 'Agent Action Approval' in BFF's MariaDB, ERD
-- Â§3.6) â€” these exist so buildpolaris_ai can reconstruct its own eval
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
