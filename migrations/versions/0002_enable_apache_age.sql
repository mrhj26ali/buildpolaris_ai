-- ARCH v2.1 Â§6.3 / ERD v2.1 Â§4.3 â€” Apache AGE knowledge graph.
CREATE EXTENSION IF NOT EXISTS age;
LOAD 'age';
SET search_path = ag_catalog, "$user", public;

SELECT create_graph('buildpolaris_graph')
WHERE NOT EXISTS (
    SELECT 1 FROM ag_catalog.ag_graph WHERE name = 'buildpolaris_graph'
);

-- Vertex labels mirroring MariaDB entities (ERD Â§4.3 table) â€” created
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
