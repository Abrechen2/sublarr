#!/bin/bash
# Sonarr Custom Script: Trigger anime subtitle translation on download/upgrade
# Ablageort: /mnt/user/appdata/sonarr/custom-scripts/anime-translate-trigger.sh
# Sonarr Container braucht Volume: /mnt/user/appdata/sonarr/custom-scripts:/custom-scripts:ro

# Test-Event von Sonarr ignorieren
[[ "$sonarr_eventtype" == "Test" ]] && exit 0

# Nur bei Download oder Upgrade
[[ "$sonarr_eventtype" != "Download" ]] && exit 0

# Sonarr-Pfad (/tv/...) auf Container-Pfad (/media/...) mappen
FILE_PATH="${sonarr_episodefile_path/\/tv\//\/media\/}"

# Nur MKV-Dateien verarbeiten
[[ "$FILE_PATH" != *.mkv ]] && exit 0

# Async Translation triggern (fire-and-forget)
curl -s -X POST "http://anime-sub-translator:5765/translate" \
  -H "Content-Type: application/json" \
  -d "{\"file_path\": \"$FILE_PATH\"}" \
  > /dev/null 2>&1 &

exit 0
