#!/usr/bin/env bash
# Start Kepler: builds the dashboard if needed, then serves API + UI on http://localhost:8000
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x backend/.venv/bin/uvicorn ]; then
  uv venv --python 3.12 backend/.venv
  uv pip install --python backend/.venv/bin/python -e backend
fi
if [ ! -d frontend/dist ]; then
  (cd frontend && npm install && npm run build)
fi
KEPLER_DB="${KEPLER_DB:-$PWD/backend/data/kepler.db}" KEPLER_AUTH="${KEPLER_AUTH:-off}" exec backend/.venv/bin/uvicorn kepler.api:app --app-dir backend --port "${PORT:-8000}" --timeout-keep-alive 75
