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
