#!/usr/bin/env bash
# Verify the 1.14.1 fixes against a running instance, RC by default.
#
# Each check states what a PASS and a FAIL look like, because a check whose
# verdict has to be interpreted is a check nobody trusts.
#
# Usage: bash scripts/check-1_14_1-rc-fixes.sh [port] [host]
set -uo pipefail
PORT="${1:-5766}"
HOST="${2:-root@192.168.178.36}"
CONTAINER="sublarr-rc"
[ "$PORT" = "5765" ] && CONTAINER="sublarr"
[ "$PORT" = "5767" ] && CONTAINER="sublarr-beta"
DB="${CONTAINER}-postgres"

api() { ssh -o ConnectTimeout=20 "$HOST" "docker exec $CONTAINER sh -c 'curl -s -m 30 -H \"X-Api-Key: \$SUBLARR_API_KEY\" $1'"; }
psql() { ssh -o ConnectTimeout=20 "$HOST" "docker exec $DB psql -U sublarr -d sublarr -Atc \"$1\""; }

echo "=== 1.14.1 fix check on :$PORT ($CONTAINER) — $(date '+%Y-%m-%d %H:%M:%S %Z') ==="
echo

echo "--- running version (want 1.14.1-rc.N) ---"
api "http://localhost:$PORT/api/v1/health" | head -c 200
echo
ssh -o ConnectTimeout=20 "$HOST" "docker exec $CONTAINER sh -c 'echo \$SUBLARR_VERSION'"

echo
echo "--- #205: AniDB season-range mappings ---"
echo "Trigger a sync, then read Bleach (TVDB 74796) back out of the table."
api "-X POST http://localhost:$PORT/api/v1/anidb-mapping/refresh" | head -c 200
echo
echo "PASS = the counts below are non-zero and S02E01 reads 21."
echo "FAIL = zero rows for 74796; the range expansion is not in this image."
sleep 45
psql "SELECT 'mappings total: '||COUNT(*) FROM anidb_absolute_mappings;"
psql "SELECT 'bleach rows: '||COUNT(*) FROM anidb_absolute_mappings WHERE tvdb_id=74796;"
psql "SELECT 'S'||lpad(season::text,2,'0')||'E'||lpad(episode::text,2,'0')||' -> '||anidb_absolute_episode
      FROM anidb_absolute_mappings
      WHERE tvdb_id=74796 AND ((season=1 AND episode=1) OR (season=2 AND episode IN (1,21)) OR (season=3 AND episode=1))
      ORDER BY season, episode;"

echo
echo "--- #14a: completing onboarding satisfies the first-run modal ---"
echo "PASS = both flags read true. FAIL = setup_wizard_completed stays false,"
echo "which is what made the welcome modal come back on a finished install."
psql "SELECT key||' = '||value FROM config_entries WHERE key IN ('onboarding_completed','setup_wizard_completed') ORDER BY key;"

echo
echo "--- #14b: has_providers follows the provider list ---"
echo "PASS = has_providers true while providers are enabled below."
api "http://localhost:$PORT/api/v1/onboarding/status"
echo
api "http://localhost:$PORT/api/v1/providers/health" | tr ',' '\n' | grep -c '"enabled":true' | sed 's/^/enabled providers: /'

echo
echo "--- #24: the webhook receivers answer on the singular path ---"
echo "PASS = /webhook/sonarr answers 400/401/403 (reached the route)."
echo "FAIL = 404 or 405 (the path the docs used to print)."
for p in webhook/sonarr webhooks/sonarr; do
  code=$(ssh -o ConnectTimeout=20 "$HOST" "docker exec $CONTAINER sh -c 'curl -s -o /dev/null -w %{http_code} -m 15 -X POST -H \"Content-Type: application/json\" -d {} http://localhost:$PORT/api/v1/$p'")
  printf '  /api/v1/%-18s -> %s\n' "$p" "$code"
done

echo
echo "--- #25 / #16 / #20: shipped in the bundle, verified in the browser ---"
echo "  Settings -> Connections : the path-mapping table with a Test button"
echo "                            (not a bare semicolon-separated text field)"
echo "  Settings -> General     : a 'Re-run onboarding' entry linking /onboarding"
echo "  Languages & Profiles    : saving a duplicate profile name shows the"
echo "                            server's own 409 text, not 'could not save'"
