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
