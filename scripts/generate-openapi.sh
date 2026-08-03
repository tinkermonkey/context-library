#!/usr/bin/env bash
# Exports the FastAPI-generated OpenAPI spec to openapi.json at the repo root.
#
# Builds the schema straight from the route definitions in create_app() — it
# does not start the server or touch SQLite/ChromaDB, so no CTX_* env vars
# are required. Run this whenever server/routes/*.py or server/schemas.py
# change, and commit the resulting openapi.json so the API surface is
# diffable without running the server.
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHONPATH="src:${PYTHONPATH:-}" python3 -c "
import json
from context_library.server.app import app

with open('openapi.json', 'w') as f:
    json.dump(app.openapi(), f, indent=2)
    f.write('\n')
"

echo "Wrote openapi.json"
