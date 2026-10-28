#!/usr/bin/env bash
# Connect the real Kepler (:8001) to Prometheus and Postgres using nothing but the Kepler CLI.
set -euo pipefail
source "$(dirname "$0")/env.sh"
K() { "$KEPLER" --url "http://localhost:$KEPLER_PORT" "$@"; }

echo "── 5xx errors per platform, from Prometheus"
K connect prometheus url="http://localhost:$PROM_PORT" \
  query='sum by (platform) (increase(http_requests_total{status="500"}[5m]))' \
  labels=platform metric=api_5xx backfill_days=21 --alert-when up --every 1

echo "── p95 latency per region, from Prometheus"
K connect prometheus url="http://localhost:$PROM_PORT" \
  query='histogram_quantile(0.95, sum by (le, region) (rate(http_request_duration_seconds_bucket[5m])))' \
  labels=region metric=p95_latency_s backfill_days=21 --agg mean --alert-when up --every 1

echo "── sign-ups per platform and region, from Postgres (read-only user)"
K connect postgres dsn="postgresql://kepler_readonly@localhost:$PGPORT/orbitly" \
  query="SELECT date_bin('5 minutes', created_at, '2000-01-01') AS ts, platform, region, count(*) AS value
         FROM users WHERE created_at > now() - interval '21 days' GROUP BY 1, 2, 3" \
  metric=signups --alert-when down --every 1

echo "── first pulls (imports the history)"
for id in $(K pulls --json | "$PY" -c 'import json,sys; print(" ".join(str(p["id"]) for p in json.load(sys.stdin)))'); do
  K pulls run "$id"
done
K pulls
