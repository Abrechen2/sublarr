#!/usr/bin/env bash
# Long-term check for 1.14.0-rc.11: did decoupling the translator from
# wanted_search and subtitle_automation actually hold in production?
#
# Deployed to prod + RC on 2026-09-06 ~13:25 CEST.
#
# Baseline over the 7 days BEFORE the deploy (prod):
#
#   job                  ok     timeout  abandoned   completion
#   wanted_search        15     23       4           15/42 = 36%
#   subtitle_automation  1430   50       3           1430/1483 = 96.4%
#
#   pending sidecar_translate rows: 390
#   failed  sidecar_translate rows: 695
#   wanted: 9323, extracted: 2174
#
# What "working" looks like:
#   * wanted_search completion climbs towards ~100%; timeout_abandoned goes to 0
#   * subtitle_automation `timeout` rows go to ~0 (the budget ends the tick
#     cleanly before the JobSpec stops waiting)
#   * downloads per day stay in the same band (~250-600) — the handoff must not
#     cost throughput, only move it
#
# What a REGRESSION looks like (the risks this change introduces):
#   * pending sidecar_translate grows without bound — the search queues faster
#     than the drain can translate
#   * rows stuck in 'searching' — the new early exit skipping its bookkeeping
#   * downloads per day collapse — items queued but never actually translated
#
# Usage: bash scripts/check-rc11-decoupling.sh [host]
set -uo pipefail
HOST="${1:-root@192.168.178.36}"

psql() { ssh -o ConnectTimeout=20 "$HOST" "docker exec sublarr-postgres psql -U sublarr -d sublarr -Atc \"$1\""; }

echo "=== 1.14.0-rc.11 decoupling check — $(date '+%Y-%m-%d %H:%M:%S %Z') ==="
echo
echo "--- running version ---"
curl -s -m 10 http://192.168.178.36:5765/api/v1/health || echo "prod unreachable"
echo
curl -s -m 10 http://192.168.178.36:5766/api/v1/health || echo "rc unreachable"
echo
echo "--- job outcomes SINCE the deploy ---"
psql "SELECT job_id, status, COUNT(*), ROUND(AVG(duration_ms)/1000.0)::int AS avg_s
      FROM scheduler_job_runs
      WHERE job_id IN ('wanted_search','subtitle_automation')
        AND started_at > TIMESTAMPTZ '2026-09-06 13:25:00+02'
      GROUP BY job_id, status ORDER BY job_id, status;"

echo
echo "--- REGRESSION WATCH: queue depth (baseline pending=390, failed=695) ---"
psql "SELECT state, task_type, COUNT(*) FROM subtitle_automation_queue
      WHERE task_type='sidecar_translate' GROUP BY state, task_type ORDER BY 1;"

echo
echo "--- REGRESSION WATCH: rows STRANDED in 'searching' (must be 0) ---"
# Age matters. A handful of rows in 'searching' with an age of seconds is a
# tick doing its job; the failure mode is a row that stays there after the
# tick that owned it is gone. 30 min is comfortably longer than any single
# item takes now that the translation is handed off.
psql "SELECT COUNT(*) FROM wanted_items
      WHERE status='searching' AND updated_at < NOW() - INTERVAL '30 minutes';"
echo "^ stranded (>30 min). Currently searching, any age:"
psql "SELECT COUNT(*) FROM wanted_items WHERE status='searching';"

echo
echo "--- throughput: downloads per day (baseline band ~250-600) ---"
psql "SELECT to_char(downloaded_at,'MM-DD'), COUNT(*) FROM subtitle_downloads
      WHERE downloaded_at > NOW() - INTERVAL '5 days' GROUP BY 1 ORDER BY 1;"

echo
# CAUTION on every log count below. `docker compose up -d` builds a NEW
# container when the image tag changes, and a new container starts with an
# empty log. So `docker logs --since 24h` reaches back only to the last
# deploy, never further. A count of 0 here means "not seen since the deploy",
# which is only good news once enough time has passed for the job to have run
# at all — wanted_search fires every 4h. Check the window before reading the
# numbers.
echo "--- log window actually available ---"
ssh -o ConnectTimeout=20 "$HOST" \
  "docker inspect sublarr --format 'container started: {{.State.StartedAt}}'"

echo
echo "--- the handoff actually firing? (log evidence) ---"
ssh -o ConnectTimeout=20 "$HOST" \
  "docker logs sublarr --since 24h 2>&1 | grep -c 'queued the source-' || true"
echo "^ count of 'queued the source-<FMT> translation for the drain'"
ssh -o ConnectTimeout=20 "$HOST" \
  "docker logs sublarr --since 24h 2>&1 | grep -c 'budget spent after' || true"
echo "^ count of 'Ns budget spent after N item(s)'"

echo
echo "--- translator noise that should now be absent from wanted_search ---"
# Positive control first: the cheap sidecar probe (`translator._helpers`) must
# still show up in the thousands. If THAT reads 0 as well, the detector is
# looking at an empty window and the "expensive = 0" line below means nothing.
ssh -o ConnectTimeout=20 "$HOST" \
  "docker logs sublarr --since 24h 2>&1 | grep 'wanted_search:' | grep -c 'translator._helpers' || true"
echo "^ POSITIVE CONTROL: cheap sidecar probes (expect thousands; 0 = detector blind)"
ssh -o ConnectTimeout=20 "$HOST" \
  "docker logs sublarr --since 24h 2>&1 | grep 'wanted_search:' | grep -cE 'translator.(quality|ass_flow|srt_flow)|translation.llm_base' || true"
echo "^ EXPENSIVE translator work inside a wanted_search tick (want: 0)"
