#!/usr/bin/env bash
# Clone the prod Sublarr Postgres DB into the RC Postgres. DESTRUCTIVE on the
# target. Guarded so it can only ever hit sublarr-rc-postgres, and only with
# FORCE=1. See docs/superpowers/specs/2026-07-09-sublarr-3tier-design.md.
set -euo pipefail

SSH="ssh -o ConnectTimeout=10 -i ${HOME}/.ssh/id_ed25519 root@192.168.178.36"
SOURCE_PG="sublarr-postgres"
TARGET_PG="${TARGET_PG:-sublarr-rc-postgres}"
DB="sublarr"
DBUSER="sublarr"
RC_COMPOSE_DIR="/mnt/user/appdata/sublarr-rc"
RC_PROJECT="sublarr-rc"
RC_APP="sublarr-rc"

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
$SSH "cd $RC_COMPOSE_DIR && docker compose -p $RC_PROJECT up -d $RC_APP"
echo "Done. RC now mirrors prod DB (config_entries included)."
