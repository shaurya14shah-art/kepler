#!/usr/bin/env bash
# Start everything: Postgres, Prometheus, the Orbitly app, live traffic, and a real (non-demo) Kepler on :8001.
set -euo pipefail
source "$(dirname "$0")/env.sh"
[ -d "$DATA/pg" ] || { echo "run ./setup.sh first"; exit 1; }
"$PGBIN/pg_ctl" -D "$DATA/pg" status >/dev/null 2>&1 || \
  "$PGBIN/pg_ctl" -D "$DATA/pg" -o "-p $PGPORT -c unix_socket_directories=''" -l "$DATA/logs/postgres.log" start >/dev/null
start() {  # name, workdir, command...
  local name=$1 dir=$2; shift 2
  if running "$name"; then echo "• $name already running"; return; fi
  local port=""
  case $name in orbitly) port=$APP_PORT;; kepler) port=$KEPLER_PORT;; prometheus) port=$PROM_PORT;; esac
  if [ -n "$port" ] && lsof -nP -iTCP:"$port" -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "• $name: port $port is busy (an old copy still running?) — run ./stop.sh $name first"; return
  fi
  # exec: the recorded PID is the service itself (not a wrapper shell), and no output pipe stays attached
  (cd "$dir" && exec nohup "$@" >"$DATA/logs/$name.log" 2>&1 </dev/null) &
  echo $! >"$DATA/run/$name.pid"
  echo "• $name started (log: lab/.data/logs/$name.log)"
}
start prometheus "$LAB" prometheus --config.file="$LAB/prometheus.yml" --storage.tsdb.path="$DATA/prometheus" \
  --storage.tsdb.retention.time=60d --web.listen-address="127.0.0.1:$PROM_PORT"
start orbitly "$LAB/orbitly" "$ROOT/backend/.venv/bin/uvicorn" app:app --port "$APP_PORT" --log-level warning  # one process: prometheus_client counters are per process
sleep 2
start traffic "$LAB/orbitly" "$PY" traffic.py --url "http://localhost:$APP_PORT"
start kepler "$ROOT" env KEPLER_DB="$DATA/kepler-real.db" KEPLER_DEMO=0 KEPLER_AUTH=off KEPLER_HOME="$DATA/kepler-home" \
  "$ROOT/backend/.venv/bin/uvicorn" kepler.api:app --app-dir backend --port "$KEPLER_PORT" --timeout-keep-alive 75
echo
echo "Orbitly     http://localhost:$APP_PORT/admin/faults"
echo "Prometheus  http://localhost:$PROM_PORT"
echo "Kepler      http://localhost:$KEPLER_PORT   (real data, no demo)"
