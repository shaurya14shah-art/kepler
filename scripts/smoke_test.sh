#!/usr/bin/env bash
# Install the built wheel into a brand-new virtualenv and check the product works the way a customer gets it:
# version, server start with the access gate ON, sign-in, CLI with the key, billing disabled, the dashboard page.
# Every check must pass; the first failure stops the run and says why.
# Usage: scripts/smoke_test.sh [dist/kepler_watchdog-X.Y.Z-py3-none-any.whl]     (`make smoke`)
set -uo pipefail
WHEEL="${1:-$(ls -t dist/kepler_watchdog-*.whl | head -1)}"
PORT="${SMOKE_PORT:-8799}"
TMP="$(mktemp -d)"
cleanup() { if [ -n "${SERVER:-}" ]; then kill "$SERVER" 2>/dev/null; wait "$SERVER" 2>/dev/null; fi; rm -rf "$TMP"; }
trap cleanup EXIT
export KEPLER_CONFIG="$TMP/config.json" KEPLER_HOME="$TMP/home" KEPLER_WEB=off
URL="http://127.0.0.1:$PORT"

check() {  # check "what it proves" command…
  local what="$1"; shift
  if out="$("$@" 2>&1)"; then printf '  \033[32m✓\033[0m %s\n' "$what"
  else printf '  \033[31m✗ %s\033[0m\n%s\n' "$what" "$(printf '%s' "$out" | tail -8)"; exit 1; fi
}
code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }

echo "smoke test: $WHEEL"
uv venv -q --python 3.12 "$TMP/venv" && uv pip install -q --python "$TMP/venv/bin/python" "$WHEEL" || exit 1
K="$TMP/venv/bin/kepler"
check "installs: $("$K" --version)" "$K" --version

"$K" serve --port "$PORT" --db "$TMP/k.db" --demo on --log-level warning >"$TMP/serve.log" 2>&1 &
SERVER=$!
for _ in $(seq 1 90); do curl -sf "$URL/api/health" | grep -q '"seeding":false' && break; sleep 1; done

check "server starts and seeds demo data"            curl -sf "$URL/api/health"
check "prints the dashboard sign-in key"              grep -q "Dashboard sign-in key" "$TMP/serve.log"
check "access gate is on by default (401, no key)"    test "$(code "$URL/api/overview")" = 401
KEY="$("$K" key --url "$URL" --no-color)"
check "kepler key finds the local server's key"       test "${KEY:0:3}" = kp_
check "dashboard sign-in works"                       curl -sf -c "$TMP/jar" -H 'content-type: application/json' -d "{\"key\":\"$KEY\"}" "$URL/api/session"
check "signed-in browser can use the API"             test "$(code -b "$TMP/jar" "$URL/api/overview")" = 200
check "CLI works against the gated server"            "$K" status --url "$URL" --no-color
check "compares the three models (helper process)"    bash -c "'$K' compare signups --url '$URL' --no-color | grep -qi orbit"
check "billing is disabled"                           bash -c "curl -sf -b '$TMP/jar' '$URL/api/billing' | grep -q '\"enabled\":false'"
check "checkout refuses: nothing can be charged"      test "$(code -b "$TMP/jar" -H 'content-type: application/json' -d '{"plan":"pro"}' "$URL/api/billing/checkout")" = 403
check "serves the bundled dashboard"                  bash -c "curl -sf '$URL/' | grep -q 'id=\"root\"'"
check "Kepler AI answers"                             bash -c "'$K' ask --no-color 'what is 12 * 7' | grep -q 84"
echo "all good"
