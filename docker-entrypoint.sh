#!/bin/sh
# Runs pending Postgres migrations (pgvector + AGE + BuildPolaris schema)
# before starting the sidecar. Never exposed to the public internet
# directly (ARCH Â§4.2) â€” this container only listens on the private
# network segment reachable from buildpolaris_bff.
set -e

echo "[buildpolaris_ai] applying migrations..."
python -m migrations.env

echo "[buildpolaris_ai] starting: $@"
exec "$@"
