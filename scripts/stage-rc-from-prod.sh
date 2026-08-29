#!/usr/bin/env bash
# Clone the prod Sublarr Postgres DB into the RC Postgres. DESTRUCTIVE on the
# target. Guarded so it can only ever hit sublarr-rc-postgres, and only with
# FORCE=1. See docs/superpowers/specs/2026-07-09-sublarr-3tier-design.md.
set -euo pipefail

# NB: rely on ssh's default key discovery (~/.ssh/id_ed25519) rather than an
# explicit -i path — a HOME with spaces (Windows git-bash "Dennis Wittke")
# word-splits inside the unquoted $SSH expansion and breaks the -i argument.
SSH="ssh -o ConnectTimeout=10 root@192.168.178.36"
SOURCE_PG="sublarr-postgres"
TARGET_PG="${TARGET_PG:-sublarr-rc-postgres}"
DB="sublarr"
DBUSER="sublarr"
RC_COMPOSE_DIR="/mnt/user/appdata/sublarr-rc"
RC_PROJECT="sublarr-rc"
RC_APP="sublarr-rc"
RC_PORT="5766"  # RC's port on the Cardinal host (container itself listens on 5765)
# Config-at-rest encryption key lives in {config_dir}/.encryption_key, deliberately
# OUTSIDE the DB — so a DB clone alone can't decrypt prod's encrypted config values
# and the RC app crashes on boot ("Failed to decrypt"). Copy prod's key too.
PROD_KEY="/mnt/user/appdata/sublarr/config/.encryption_key"
RC_KEY="/mnt/user/appdata/sublarr-rc/config/.encryption_key"

# --- Guards (the critical safety logic; run BEFORE any docker/ssh) ---
if [[ "${FORCE:-}" != "1" ]]; then
  echo "REFUSE: set FORCE=1 to run the destructive prod->RC clone" >&2
  exit 2
fi
case "$TARGET_PG" in
  sublarr-postgres | sublarr-beta-postgres)
    echo "REFUSE: target '$TARGET_PG' is prod/beta — never clone onto it" >&2
    exit 3
    ;;
  sublarr-rc-postgres) : ;; # the only allowed target
  *)
    echo "REFUSE: unknown target '$TARGET_PG' (allowed: sublarr-rc-postgres)" >&2
    exit 4
    ;;
esac
if [[ "$TARGET_PG" == "$SOURCE_PG" ]]; then
  echo "REFUSE: target equals source" >&2
  exit 5
fi

# --- Clone: stop RC app (release connections) -> drop+recreate -> dump|restore -> start ---
echo "Cloning $SOURCE_PG -> $TARGET_PG ..."
$SSH "cd $RC_COMPOSE_DIR && docker compose -p $RC_PROJECT stop $RC_APP"
$SSH "docker exec $TARGET_PG psql -U $DBUSER -d postgres -c 'DROP DATABASE IF EXISTS $DB;' -c 'CREATE DATABASE $DB;'"
$SSH "docker exec $SOURCE_PG pg_dump -U $DBUSER -d $DB --no-owner --no-privileges | docker exec -i $TARGET_PG psql -U $DBUSER -d $DB"
$SSH "cp -a '$PROD_KEY' '$RC_KEY' && chmod 600 '$RC_KEY'"
$SSH "cd $RC_COMPOSE_DIR && docker compose -p $RC_PROJECT up -d $RC_APP"

# --- Silence the automation the clone just armed -------------------------
# The dump carries config_entries, and the encryption key copied above makes
# them decryptable — so RC comes up holding prod's *real* DeepL/OpenSubtitles
# credentials, pointed at prod's full backlog (thousands of wanted items).
# subtitle_automation then re-translates that backlog on RC, billing the
# owner's live DeepL quota for work prod already paid for. Observed
# 2026-08-01: 1468 DeepL calls in six hours from a single staging round.
#
# Pause every job that can reach a paid API. Everything else (cleanup,
# stats, health sweeps) is local and stays running so the RC still behaves
# like a real instance. Unpause individually in Settings → System →
# Scheduler when a round genuinely needs to exercise translation.
# NB: 5766 is RC's port *on the host* — the container listens on 5765, but
# these curls run on Cardinal, not inside it.
echo "Waiting for RC to accept requests ..."
$SSH "for i in \$(seq 1 60); do curl -sf --max-time 3 http://localhost:${RC_PORT}/api/v1/health >/dev/null 2>&1 && exit 0; sleep 2; done; exit 1" || {
  echo "REFUSE: RC did not become healthy — pause the paid-API jobs by hand" >&2
  exit 6
}

# A pause alone does NOT hold. _apply_intervals_to_apscheduler runs on every
# settings-save and on every boot, and re-arms any job whose configured
# interval is greater than zero — so the next config write, or the next
# restart, quietly puts the paused job back on the clock with prod's live
# credentials. Setting the interval to 0 is what sticks: the boot path pauses
# on interval <= 0.
#
# wanted_scan_interval_hours and wanted_auto_translate joined this list on
# 2026-08-29, when prod switched both on. The clone carries them, and
# wanted_scanner was in nobody's pause list.
echo "Disabling the load- and quota-generating settings on RC ..."
CFG_JSON='{"wanted_search_interval_hours":0,"upgrade_scan_interval_hours":0,"wanted_scan_interval_hours":0,"wanted_auto_translate":false,"subtitle_automation_enabled":false}'
$SSH "docker exec $RC_APP sh -lc 'curl -sS -m 30 -o /dev/null -w \"  config: %{http_code}\n\" -X PUT -H \"X-Api-Key: \$SUBLARR_API_KEY\" -H \"Content-Type: application/json\" -d '\''$CFG_JSON'\'' http://localhost:5765/api/v1/config'" || \
  echo "  config write failed — set the intervals to 0 by hand" >&2

# Belt and braces: the pause bites immediately, the interval keeps it off
# across restarts. mt_reseek has no interval setting, so there the pause is
# all there is.
echo "Pausing paid-API scheduler jobs on RC ..."
for _job in subtitle_automation wanted_search wanted_scanner mt_reseek upgrade_scan; do
  $SSH "curl -sS -X POST 'http://localhost:${RC_PORT}/api/v1/scheduler/jobs/${_job}/pause' -o /dev/null -w '  ${_job}: %{http_code}\n'" || \
    echo "  ${_job}: pause failed (non-fatal — pause it by hand)" >&2
done

echo "Done. RC mirrors prod DB (config_entries included); paid-API jobs off."
