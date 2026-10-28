#!/usr/bin/env bash
# Stop every lab process. Usage: ./stop.sh [name ...]   (default: all; postgres only when stopping all)
source "$(dirname "$0")/env.sh"
port_of() { case $1 in orbitly) echo "$APP_PORT";; kepler) echo "$KEPLER_PORT";; prometheus) echo "$PROM_PORT";; esac; }
stop_one() {
  local n=$1 pids=""
  [ -f "$DATA/run/$n.pid" ] && pids="$(cat "$DATA/run/$n.pid")"
  local port; port=$(port_of "$n")
  [ -n "$port" ] && pids="$pids $(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null | tr '\n' ' ')"
  pids=$(echo $pids)
  if [ -n "$pids" ]; then
    kill $pids 2>/dev/null
    # uvicorn waits for open keep-alive connections (the traffic generator never closes them): don't wait forever
    for _ in 1 2 3 4 5; do kill -0 $pids 2>/dev/null || break; sleep 1; done
    kill -9 $pids 2>/dev/null
    echo "• stopped $n"
  fi
  rm -f "$DATA/run/$n.pid"
}
names=${*:-traffic orbitly prometheus kepler}
for n in $names; do stop_one "$n"; done
if [ $# -eq 0 ]; then
  "$PGBIN/pg_ctl" -D "$DATA/pg" status >/dev/null 2>&1 && "$PGBIN/pg_ctl" -D "$DATA/pg" stop -m fast >/dev/null && echo "• stopped postgres"
fi
exit 0
