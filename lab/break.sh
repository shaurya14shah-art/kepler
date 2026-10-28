#!/usr/bin/env bash
# Break Orbitly on purpose:  ./break.sh ios_errors|android_signups|eu_slow [minutes]   ·   ./break.sh list
source "$(dirname "$0")/env.sh"
if [ "${1:-list}" = "list" ]; then curl -s "localhost:$APP_PORT/admin/faults"; echo; exit 0; fi
curl -s -X POST "localhost:$APP_PORT/admin/faults" -H 'content-type: application/json' \
  -d "{\"name\": \"$1\", \"minutes\": ${2:-30}}"; echo
