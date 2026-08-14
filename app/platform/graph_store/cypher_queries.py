"""Canned, parameterized Cypher fragments â€” kept separate from
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
# have open safety incidents" â€” Task -[ASSIGNED_TO]-> Person <-[HAS_INCIDENT]- SafetyIncident,
# filtered on Task.is_critical / slippage.
DELAYED_TASK_SUBCONTRACTORS_WITH_INCIDENTS = """
    SELECT * FROM cypher('{graph}', $$
        MATCH (t:Task {{company: $company, is_critical: true}})-[:ASSIGNED_TO]->(p:Person)
        MATCH (p)<-[:HAS_INCIDENT]-(i:SafetyIncident {{company: $company}})
        RETURN t, p, i
        LIMIT $limit
    $$, %s) AS (t agtype, p agtype, i agtype);
"""
