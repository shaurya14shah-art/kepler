#!/usr/bin/env bash
# Stop everything and delete the lab's data (Postgres, Prometheus, Kepler-real database).
source "$(dirname "$0")/env.sh"
"$LAB/stop.sh"
rm -rf "$DATA" && echo "• lab data deleted; run ./setup.sh to start over"
