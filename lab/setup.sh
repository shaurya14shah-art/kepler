#!/usr/bin/env bash
# One-time setup: create a private Postgres + Prometheus for the lab and give Orbitly 3 weeks of history.
set -euo pipefail
source "$(dirname "$0")/env.sh"
if [ -d "$DATA/pg" ]; then echo "already set up (run ./reset.sh to start over)"; exit 0; fi
echo "• creating Postgres cluster on port $PGPORT"
"$PGBIN/initdb" -D "$DATA/pg" -U "$USER" --auth=trust -E UTF8 >/dev/null
"$PGBIN/pg_ctl" -D "$DATA/pg" -o "-p $PGPORT -c unix_socket_directories=''" -l "$DATA/logs/postgres.log" start >/dev/null
"$PGBIN/createdb" -h localhost -p "$PGPORT" orbitly
"$PGBIN/psql" -q -h localhost -p "$PGPORT" orbitly <<'SQL'
CREATE TABLE users (
  id bigserial PRIMARY KEY,
  created_at timestamptz NOT NULL DEFAULT now(),
  platform text NOT NULL,
  region text NOT NULL,
  plan text NOT NULL DEFAULT 'free'
);
CREATE INDEX users_created_at ON users (created_at);
CREATE ROLE kepler_readonly LOGIN;
GRANT SELECT ON users TO kepler_readonly;
SQL
echo "• backfilling 21 days of history"
(cd "$LAB/orbitly" && "$PY" seed_history.py --dsn "$ORBITLY_DSN" --out "$DATA/history.om" --days 21)
echo "• importing history into Prometheus with promtool"
mkdir -p "$DATA/prometheus"
promtool tsdb create-blocks-from openmetrics "$DATA/history.om" "$DATA/prometheus" >"$DATA/logs/promtool.log" 2>&1
rm -f "$DATA/history.om"
"$PGBIN/pg_ctl" -D "$DATA/pg" stop >/dev/null
echo "done. next: ./start.sh"
