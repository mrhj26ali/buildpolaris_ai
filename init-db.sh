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
