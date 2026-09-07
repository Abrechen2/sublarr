#!/usr/bin/env bash
# Long-term check for 1.14.0-rc.12: did the language filter, the adoption
# guard and the script guards hold in production?
#
# Deployed to prod + RC on 2026-09-07 ~20:15 CEST.
#
# Baseline BEFORE the deploy (prod):
#
#   activity_log extract rows/day   09-05: 3 430   09-06: 1 308   09-07: 2 914 (calendar
#                                   days; the rolling 24h before the deploy held 4 152)
#   ']: extracted ' log lines       3 514 in the 24h before the deploy
#   'Sidecar cleanup: trashed'      3 136 in the same window
#   extracted languages             ita 211, spa 207, por 205, fre 181, chi 178 …
#   wrong-script .de.srt on disk    18 (13 Oshi no Ko, SWORD GAI, Kaguya = ar/ja;
#                                       3 HELL MODE = zh, trashed by hand)
#   translation_memory pairs        en-de, de-en, ja-de, id-de, zh-de, vi-de
#
# What "working" looks like:
#   * extract rows/day fall to a few hundred and stay there (the daily
#     re-enqueue churn is still there, but each pass is a cached probe plus an
#     exists() check — no ffmpeg run)
#   * extracted languages are only ger/eng/und (whatever the profile keeps)
#   * 'Sidecar cleanup: trashed' stays near 0 — there is nothing foreign to trash
#   * 'mislabelled sidecar' lines appear ONCE per wrong file (15 expected in the
#     first day or two), then never again
#   * no new translation_memory pair outside en/de/ja as source
#   * 'Downloaded subtitle rejected' lines are the script guard doing its job —
#     a few are fine, a flood means a provider mislabels wholesale
#
# What a REGRESSION looks like:
#   * 'does not hold what its name says' on a GERMAN or ENGLISH file (false
#     positive — check the file by hand before believing the log)
#   * extract rows/day stay in the thousands — the filter is not in the path
#   * a batch failing on 'wrong script' for a German target with German text
#   * HELL MODE S02E01/E04/E07 get a .de.srt that is Chinese again (guard blind)
#
# Usage: bash scripts/check-rc12-language-filter.sh [--disk] [host]
#   --disk  also walk the media tree for foreign sidecars newer than the deploy
#           (slow: ~10 min on the prod array)
set -uo pipefail
DISK=0
if [ "${1:-}" = "--disk" ]; then DISK=1; shift; fi
HOST="${1:-root@192.168.178.36}"
DEPLOYED="2026-09-07 20:15:00+02"

psql() { ssh -o ConnectTimeout=20 "$HOST" "docker exec sublarr-postgres psql -U sublarr -d sublarr -Atc \"$1\""; }
logs() { ssh -o ConnectTimeout=20 "$HOST" "docker logs sublarr --since 48h 2>&1 | $1"; }

echo "=== 1.14.0-rc.12 language-filter check — $(date '+%Y-%m-%d %H:%M:%S %Z') ==="
echo
echo "--- running version ---"
curl -s -m 10 http://192.168.178.36:5765/api/v1/health || echo "prod unreachable"
echo
ssh -o ConnectTimeout=20 "$HOST" "docker exec sublarr sh -c 'echo SUBLARR_VERSION=\$SUBLARR_VERSION'"

echo
echo "--- extract activity rows per day (baseline 09-05: 3430, 09-06: 1308, 09-07: 2914) ---"
psql "SELECT to_char(created_at,'MM-DD'), COUNT(*) FROM activity_log
      WHERE event_type='extract' AND created_at > NOW() - INTERVAL '6 days'
      GROUP BY 1 ORDER BY 1;"

echo
# CAUTION: a new container starts with an EMPTY log. Everything below reaches
# back only to the last deploy; check the window before reading the numbers.
echo "--- log window actually available ---"
ssh -o ConnectTimeout=20 "$HOST" "docker inspect sublarr --format 'container started: {{.State.StartedAt}}'"

echo
echo "--- POSITIVE CONTROL: extract passes since the deploy (0 = detector blind) ---"
logs "grep -c 'auto-extract item' || true"

echo
echo "--- extracted tracks by language (want: only the profile's languages) ---"
logs "grep ']: extracted ' | sed -E 's/.*extracted ([a-z-]+) .*/\1/' | sort | uniq -c | sort -rn | head -12"

echo
echo "--- 'Sidecar cleanup: trashed' since the deploy (baseline 3136/24h; want ~0) ---"
logs "grep -c 'Sidecar cleanup: trashed' || true"

echo
echo "--- adoption guard: mislabelled sidecars found (expect ~15 once, then 0) ---"
logs "grep -c 'does not hold what its name says' || true"
logs "grep 'does not hold what its name says' | sed -E 's/.*\] (.*) does not hold.*\(([^)]*)\).*/\2  <- \1/' | sed -E 's|/media/[^ ]*/||' | tail -20"

echo
echo "--- script guard on downloads / batches ---"
logs "grep -c 'Downloaded subtitle rejected' || true"
echo "^ downloads refused (a few = fine)"
logs "grep 'Downloaded subtitle rejected' | tail -5 | cut -c1-200"
logs "grep -c 'came back in the wrong script' || true"
echo "^ translation batches refused (want 0 unless the model echoes)"

echo
echo "--- translation memory pairs (baseline en-de, de-en, ja-de, id-de, zh-de, vi-de; no NEW source) ---"
psql "SELECT source_lang||'-'||target_lang||':'||n FROM (SELECT source_lang, target_lang, COUNT(*) n FROM translation_memory GROUP BY 1,2) t ORDER BY n DESC;" | tr '
' ' '; echo

echo
echo "--- HELL MODE S02E01/E04/E07: what landed as .de since the deploy ---"
ssh -o ConnectTimeout=20 "$HOST" "cd '/mnt/user/Emby-Media/_Anime/_Serien/HELL MODE The Hardcore Gamer Dominates in Another World with Garbage Balancing (2026)/Season 2/' && for e in S02E01 S02E04 S02E07; do f=\$(ls | grep \"\$e.*\.de\.srt\" | head -1); if [ -n \"\$f\" ]; then printf '%s: ' \"\$e\"; sed -n '3p' \"\$f\" | cut -c1-60; else echo \"\$e: no .de.srt (still wanted)\"; fi; done"

if [ "$DISK" = 1 ]; then
  echo
  echo "--- foreign sidecars written since the deploy (slow) ---"
  ssh -o ConnectTimeout=20 "$HOST" "cd /mnt/user/Emby-Media && find . -path './.sublarr' -prune -o -type f -newermt '$DEPLOYED' \( -name '*.srt' -o -name '*.ass' \) -print 2>/dev/null | sed -E 's/.*\.([a-zA-Z]{2,3}(-[a-zA-Z]{2,4})?)\.(srt|ass)$/\1/' | sort | uniq -c | sort -rn | head -15"
fi
