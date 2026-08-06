#!/bin/bash
set -e

# Connect to the default database to create extensions
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Enable pgvector
    CREATE EXTENSION IF NOT EXISTS vector;
    
    -- Enable Apache AGE
    CREATE EXTENSION IF NOT EXISTS age;
    
    -- Load AGE into the session (required for AGE to work in some clients)
    LOAD 'age';
    SET search_path = ag_catalog, "\$user", public;
    
    -- Create a sample graph namespace for our AI sidecar
    SELECT * FROM ag_catalog.create_graph('polaris_knowledge_graph');
EOSQL

echo "✅ Database initialized with pgvector and Apache AGE."