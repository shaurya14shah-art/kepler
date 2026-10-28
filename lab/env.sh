# Shared settings for the Kepler real-data lab (sourced by the other scripts).
LAB="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$LAB")"
DATA="$LAB/.data"
PY="$ROOT/backend/.venv/bin/python"
KEPLER="$ROOT/backend/.venv/bin/kepler"
PGBIN="/opt/homebrew/opt/postgresql@17/bin"
PGPORT=5433
ORBITLY_DSN="postgresql://localhost:$PGPORT/orbitly"
PROM_PORT=9090
APP_PORT=9200
KEPLER_PORT=8001
export ORBITLY_DSN
export LC_ALL="en_US.UTF-8"  # Postgres on macOS refuses to start without a valid locale
mkdir -p "$DATA/logs" "$DATA/run"
running() { [ -f "$DATA/run/$1.pid" ] && kill -0 "$(cat "$DATA/run/$1.pid")" 2>/dev/null; }
