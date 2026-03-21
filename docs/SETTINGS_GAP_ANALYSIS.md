# Sublarr — Settings Gap Analysis

Vollständige Analyse aller Einstellungen: Backend `config.py` vs. UI Settings-Pages.

**Methode:** Jedes Feld in `backend/config.py` (Pydantic Settings) einzeln mit den tatsächlich verwendeten Config-Keys in allen Settings-TSX-Dateien verglichen.

> **Kritischer Fund:** Mehrere Settings-Pages verwenden **falsche Config-Key-Namen** die nicht in `Settings.model_fields` existieren. Das Backend validiert Keys gegen `Settings.model_fields` — unbekannte Keys werden **still verworfen** (kein Fehler, keine Speicherung). Betroffene Seiten: AutomationSettings, GeneralSettings.

---

## Legende

| Symbol | Bedeutung |
|--------|-----------|
| ✅ | In UI vorhanden, korrekter Key |
| ⚠️ | In UI vorhanden, aber **falscher Key-Name** → wird nicht gespeichert |
| ❌ | Kein UI-Feld vorhanden |
| 🔒 | Sensitiv (API-Key, Passwort) — wird im GET maskiert |
| 🔧 | Nur für Experten / Deployment — kann in ENV-Var bleiben |

---

## 1. Allgemein / Server

**Settings-Seite:** `GeneralSettings.tsx`

| Config-Feld (Backend) | UI-Key (Frontend) | Status | Anmerkung |
|----------------------|------------------|--------|-----------|
| `port` | `port` | ✅ | |
| `api_key` | — | ✅ | In SecurityTab als "require login + change password" |
| `log_level` | `log_level` | ✅ | |
| `log_file` | `log_to_file` | ⚠️ | Frontend sendet Boolean, Backend erwartet Pfad-String (`/config/sublarr.log`) |
| `log_format` | — | ❌ | text / json — kein UI-Feld |
| `media_path` | `media_path` | ✅ | |
| `db_path` | `db_path` | ✅ | |
| `cors_origins` | — | ❌ | Nur via ENV sinnvoll — kann weggelassen werden |
| `scan_metadata_engine` | — | ❌ | ffprobe / mediainfo / auto — kein UI-Feld |
| `scan_metadata_max_workers` | `workers` | ⚠️ | Frontend-Key `workers` existiert nicht im Backend |
| `translation_max_workers` | `workers` | ⚠️ | Gleicher falscher Key — beide Worker-Felder zusammengefasst |

**Fehlende Felder (General):**
- `log_format` (text/json) — sinnvoll für Docker-Setups mit Log-Aggregation
- `scan_metadata_engine` — relevant wenn mediainfo installiert ist
- Separate `scan_metadata_max_workers` und `translation_max_workers` statt einem `workers`-Feld

---

## 2. Sprachen & Untertitel

**Settings-Seite:** `GeneralSettings.tsx` + `SubtitlesSettings.tsx`

| Config-Feld (Backend) | UI-Key (Frontend) | Status | Anmerkung |
|----------------------|------------------|--------|-----------|
| `source_language` | `source_language` | ✅ | |
| `target_language` | `target_language` | ✅ | |
| `source_language_name` | — | ❌ | Name wird nicht separat gesetzt |
| `target_language_name` | — | ❌ | Name wird nicht separat gesetzt |
| `hi_preference` | `hi_preference` | ✅ | include / prefer / exclude / only |
| `forced_preference` | `forced_preference` | ✅ | include / prefer / exclude / only |
| `hi_removal_enabled` | — | ❌ | Global HI-Removal Toggle fehlt |
| `credit_threshold_sec` | — | ❌ | Ab wann Zeilen als Credits gelten (Sekunden vom Ende) |
| `op_window_sec` | — | ❌ | OP/ED-Erkennungsfenster |
| `use_embedded_subs` | — | ❌ | Eingebettete Subs in Scoring einbeziehen |
| `wanted_skip_srt_on_no_ass` | — | ❌ | SRT-Schritte überspringen wenn kein ASS gefunden |

**Fehlende Felder (Sprachen):**
- `source_language_name` / `target_language_name` — sollten aus dem Language-Dropdown auto-befüllt werden, nicht manuell getippt
- `credit_threshold_sec` und `op_window_sec` — wichtig für Anime (OP/ED-Erkennung)
- `hi_removal_enabled` — globaler Toggle für HI-Removal unabhängig von Automation

---

## 3. Provider

**Settings-Seite:** `ProvidersSettings.tsx` + `ProvidersTab.tsx`

| Config-Feld (Backend) | UI-Key (Frontend) | Status | Anmerkung |
|----------------------|------------------|--------|-----------|
| `provider_priorities` | — | ✅ | Drag & Drop in Provider-Grid |
| `providers_enabled` | — | ✅ | Toggle pro Provider-Kachel |
| `providers_hidden` | — | ❌ | Provider komplett aus UI entfernen |
| `addic7ed_username` | — | ✅ 🔒 | In Provider-Konfiguration |
| `addic7ed_password` | — | ✅ 🔒 | In Provider-Konfiguration |
| `turkcealtyazi_username` | — | ✅ 🔒 | In Provider-Konfiguration |
| `turkcealtyazi_password` | — | ✅ 🔒 | In Provider-Konfiguration |
| `opensubtitles_api_key` | — | ✅ 🔒 | |
| `opensubtitles_username` | — | ✅ 🔒 | |
| `opensubtitles_password` | — | ✅ 🔒 | |
| `jimaku_api_key` | — | ✅ 🔒 | |
| `subdl_api_key` | — | ✅ 🔒 | |
| `betaseries_api_key` | — | ✅ 🔒 | |
| `anti_captcha_provider` | `anti_captcha_provider` | ✅ | |
| `anti_captcha_api_key` | `anti_captcha_api_key` | ✅ 🔒 | |
| `provider_search_timeout` | — | ❌ | Globaler Fallback-Timeout |
| `provider_cache_ttl_minutes` | — | ❌ | Cache-Lebensdauer pro Provider |
| `provider_auto_prioritize` | — | ❌ | Automatische Priorisierung nach Erfolgsquote |
| `provider_rate_limit_enabled` | — | ❌ | Rate-Limiting ein/aus |
| `dedup_on_download` | — | ❌ | SHA-256 Deduplizierung beim Download |
| `github_token` | — | ❌ 🔒 | Für höhere Rate-Limits beim Plugin-Marketplace |
| `provider_dynamic_timeout_enabled` | — | ❌ | Dynamische Timeouts |
| `provider_dynamic_timeout_min_samples` | — | ❌ | Min. Samples für dyn. Timeout |
| `provider_dynamic_timeout_multiplier` | — | ❌ | Timeout-Multiplikator |
| `provider_dynamic_timeout_buffer_secs` | — | ❌ | Timeout-Buffer |
| `provider_dynamic_timeout_min_secs` | — | ❌ | Min. Timeout (Sekunden) |
| `provider_dynamic_timeout_max_secs` | — | ❌ | Max. Timeout (Sekunden) |
| `provider_reranking_enabled` | — | ❌ | Score-Modifier aus Download-History |
| `provider_reranking_min_downloads` | — | ❌ | Min. Downloads für Modifier |
| `provider_reranking_max_modifier` | — | ❌ | Max. Modifier (±) |
| `provider_auto_disable_cooldown_minutes` | — | ❌ | Cooldown für auto-deaktivierte Provider |

**Fehlende Felder (Provider):**
- `github_token` — sollte unter "Plugins" oder "Provider" stehen, damit Marketplace-Rate-Limits nicht anonym laufen
- `dedup_on_download` — sinnvoll für User die viele Provider haben
- `provider_reranking_enabled` — Auto-Priorisierung ist ein nützliches Feature ohne UI
- Dynamic Timeout-Felder: 5 Felder ohne UI (können als Experten-Sektion zusammengefasst werden)

---

## 4. Verbindungen (Sonarr / Radarr / Media Server)

**Settings-Seite:** `ConnectionsSettings.tsx` + `MediaServersTab.tsx`

| Config-Feld (Backend) | UI-Key (Frontend) | Status | Anmerkung |
|----------------------|------------------|--------|-----------|
| `sonarr_url` | — | ✅ | |
| `sonarr_api_key` | — | ✅ 🔒 | |
| `sonarr_instances_json` | — | ❌ | Multi-Instanz Sonarr — UI zeigt nur eine Instanz |
| `radarr_url` | — | ✅ | |
| `radarr_api_key` | — | ✅ 🔒 | |
| `radarr_instances_json` | — | ❌ | Multi-Instanz Radarr |
| `jellyfin_url` | — | ✅ | |
| `jellyfin_api_key` | — | ✅ 🔒 | |
| `media_servers_json` | — | ✅ | MediaServersTab |
| `path_mapping` | — | ✅ | |
| `ffmpeg_timeout` | — | ❌ | ffmpeg Timeout in Sekunden |
| `tmdb_api_key` | — | ❌ 🔒 | TMDB API für Metadaten |
| `tvdb_api_key` | — | ❌ 🔒 | TVDB API |
| `tvdb_pin` | — | ❌ 🔒 | TVDB PIN |
| `metadata_cache_ttl_days` | — | ❌ | Cache-Lebensdauer für Metadaten |

**Fehlende Felder (Verbindungen):**
- `sonarr_instances_json` / `radarr_instances_json` — Multi-Instanz ist im Backend implementiert, aber UI hat kein Interface dafür (nur "Default"-Instanz)
- `tmdb_api_key` / `tvdb_api_key` — für Standalone-Modus ohne Sonarr wichtig
- `ffmpeg_timeout` — sollte in einem "Erweitert"-Abschnitt erreichbar sein

---

## 5. Automation

**Settings-Seite:** `AutomationSettings.tsx`

> ⚠️ **Kritisch:** Diese Seite verwendet durchgehend falsche Config-Key-Namen. Alle unten als ⚠️ markierten Felder werden vom Backend nicht gespeichert.

| Config-Feld (Backend) | UI-Key (Frontend) | Status | Anmerkung |
|----------------------|------------------|--------|-----------|
| `wanted_search_interval_hours` | `wanted_search_frequency` | ⚠️ | Falscher Key — Backend-Feld heißt `wanted_search_interval_hours` |
| `wanted_search_on_startup` | `scan_on_start` | ⚠️ | Falscher Key |
| `wanted_search_max_items_per_run` | — | ❌ | Kein UI-Feld |
| `wanted_anime_only` | — | ❌ | Kein UI-Feld |
| `wanted_anime_movies_only` | — | ❌ | Kein UI-Feld |
| `wanted_auto_extract` | — | ❌ | Auto-Extraktion bei Wanted-Scan |
| `wanted_auto_translate` | `auto_translate` | ⚠️ | Falscher Key |
| `wanted_max_search_attempts` | — | ❌ | Max. Suchversuche pro Item |
| `wanted_adaptive_backoff_enabled` | — | ❌ | Adaptiver Backoff |
| `wanted_backoff_base_hours` | — | ❌ | Basis-Backoff-Zeit |
| `wanted_backoff_cap_hours` | — | ❌ | Max. Backoff-Zeit |
| `wanted_skip_srt_on_no_ass` | — | ❌ | |
| `upgrade_enabled` | `auto_upgrade_enabled` | ⚠️ | Falscher Key |
| `upgrade_min_score_delta` | `auto_upgrade_threshold` | ⚠️ | Falscher Key |
| `upgrade_window_days` | — | ❌ | Upgrade-Fenster in Tagen |
| `upgrade_prefer_ass` | — | ❌ | SRT→ASS immer upgraden |
| `upgrade_scan_interval_hours` | `upgrade_check_frequency` | ⚠️ | Falscher Key |
| `webhook_delay_minutes` | — | ❌ | Wartezeit nach Sonarr/Radarr Webhook |
| `webhook_auto_scan` | — | ❌ | Auto-Scan bei Webhook |
| `webhook_auto_search` | `auto_search_on_download` | ⚠️ | Falscher Key |
| `webhook_auto_translate` | — | ❌ | Auto-Übersetzen bei Webhook |
| `jellyfin_play_translate_enabled` | — | ❌ | Auto-Übersetzen bei Jellyfin-Wiedergabe |
| `auto_sync_after_download` | `auto_sync` | ⚠️ | Falscher Key |
| `auto_sync_engine` | — | ✅ | In TranslationSettings vorhanden |
| `auto_process_common_fixes` | — | ❌ | Auto Common-Fixes nach Download |
| `auto_process_hi_removal` | — | ❌ | Auto HI-Removal nach Download |
| `auto_process_credit_removal` | — | ❌ | Auto Credit-Removal |
| `auto_process_sync_threshold` | — | ❌ | Score-Schwellenwert für Auto-Sync |
| `auto_process_sync_fallback_engine` | — | ❌ | Fallback-Engine für Auto-Sync |
| `auto_nfo_export` | — | ❌ | NFO-Sidecar nach Download schreiben |
| `auto_cleanup_after_extract` | `auto_cleanup` | ⚠️ | Falscher Key (vermutlich gemeint) |
| `auto_cleanup_keep_languages` | — | ❌ | Welche Sprachen beim Cleanup behalten |
| `auto_cleanup_keep_formats` | — | ❌ | Welche Formate beim Cleanup behalten |
| `subtitle_trash_retention_days` | — | ❌ | Gelöschte Subs X Tage im Trash halten |
| `streaming_enabled` | — | ❌ | Web-Player Streaming-Endpunkt |

**Zusammenfassung AutomationSettings:**
- **8 falsche Key-Namen** → diese Einstellungen werden nie gespeichert (still ignoriert)
- **18 fehlende Felder** ohne jegliche UI
- Seite muss vollständig überarbeitet werden

---

## 6. Übersetzung

**Settings-Seite:** `TranslationSettings.tsx` + `TranslationTab.tsx` + `WhisperTab.tsx`

| Config-Feld (Backend) | UI-Key (Frontend) | Status | Anmerkung |
|----------------------|------------------|--------|-----------|
| `ollama_url` | — | ✅ | |
| `ollama_model` | — | ✅ | |
| `batch_size` | — | ❌ | Batch-Größe pro Übersetzungsauftrag |
| `request_timeout` | — | ❌ | Timeout pro Anfrage |
| `temperature` | — | ❌ | LLM Temperature |
| `max_retries` | — | ✅ | In TranslationTab |
| `backoff_base` | — | ❌ | Basis-Backoff zwischen Retries |
| `prompt_template` | — | ✅ | In TranslationSettings (Prompt Presets) |
| `glossary_enabled` | — | ✅ | In TranslationSettings |
| `glossary_max_terms` | — | ❌ | Max. Glossar-Einträge pro Übersetzung |
| `translation_max_workers` | `workers` | ⚠️ | Falscher Key in GeneralSettings |

**Fehlende Felder (Übersetzung):**
- `temperature` — wichtig für Übersetzungsqualität
- `batch_size` — beeinflusst Performance und Kosten
- `request_timeout` — Timeout für Ollama-Anfragen
- `glossary_max_terms` — sinnvoll als Slider/Zahl-Input

---

## 7. Scoring & Release Groups

**Settings-Seite:** `EventsTab.tsx` (in LegacySettings) + `SubtitlesSettings.tsx`

| Config-Feld (Backend) | UI-Key (Frontend) | Status | Anmerkung |
|----------------------|------------------|--------|-----------|
| `release_group_prefer` | — | ✅ | In EventsTab |
| `release_group_exclude` | — | ✅ | In EventsTab |
| `release_group_prefer_bonus` | — | ✅ | In EventsTab |

**Anmerkung:** Diese Felder sind in EventsTab korrekt implementiert — aber EventsTab ist tief in der LegacySettings-Navigation versteckt. Sollte prominenter zugänglich sein (z.B. unter SubtitlesSettings → Scoring).

---

## 8. Benachrichtigungen

**Settings-Seite:** `NotificationsSettings.tsx` + `NotificationTemplatesTab.tsx`

| Config-Feld (Backend) | UI-Key (Frontend) | Status | Anmerkung |
|----------------------|------------------|--------|-----------|
| `notification_urls_json` | — | ✅ | Apprise-URL(s) |
| `notify_on_download` | — | ✅ | |
| `notify_on_upgrade` | — | ✅ | |
| `notify_on_batch_complete` | — | ✅ | |
| `notify_on_error` | — | ✅ | |
| `notify_manual_actions` | — | ❌ | Manuelle Aktionen benachrichtigen |

**Fehlende Felder (Benachrichtigungen):**
- `notify_manual_actions` — fehlt als Toggle

---

## 9. System / Sicherheit

**Settings-Seite:** `SystemSettings.tsx` + `SecurityTab.tsx` + `ProtokollTab.tsx`

| Config-Feld (Backend) | UI-Key (Frontend) | Status | Anmerkung |
|----------------------|------------------|--------|-----------|
| `api_key` | — | ✅ | SecurityTab — Passwort setzen/ändern |
| `backup_dir` | — | ❌ | Backup-Verzeichnis — kein Input-Feld |
| `backup_retention_daily` | — | ❌ | Aufbewahrung täglich (Anzahl Backups) |
| `backup_retention_weekly` | — | ❌ | Aufbewahrung wöchentlich |
| `backup_retention_monthly` | — | ❌ | Aufbewahrung monatlich |

**Anmerkung aus AdvancedTab.tsx:** Ein Kommentar im Code sagt explizit `"Configure retention settings in General tab (backup_retention_daily, backup_retention_weekly, backup_retention_monthly)"` — diese Felder sind dokumentiert aber nie implementiert.

---

## 10. Standalone-Modus

**Settings-Seite:** `AdvancedTab.tsx` (Ordner-Verwaltung)

| Config-Feld (Backend) | UI-Key (Frontend) | Status | Anmerkung |
|----------------------|------------------|--------|-----------|
| `standalone_enabled` | — | ✅ | Modus-Auswahl im Onboarding + AdvancedTab |
| `standalone_scan_interval_hours` | — | ❌ | Scan-Intervall für Standalone |
| `standalone_debounce_seconds` | — | ❌ | Debounce-Zeit für File-Watcher |
| `standalone_skip_extras` | — | ❌ | Trailer/Extras überspringen |

**Fehlende Felder (Standalone):**
- `standalone_scan_interval_hours` — wie oft soll der Standalone-Scanner laufen?
- `standalone_skip_extras` — wichtig für korrekte Episode-Erkennung

---

## 11. AniDB

**Settings-Seite:** Keine.

| Config-Feld (Backend) | UI-Key (Frontend) | Status | Anmerkung |
|----------------------|------------------|--------|-----------|
| `anidb_enabled` | — | ❌ | AniDB-ID-Auflösung |
| `anidb_cache_ttl_days` | — | ❌ | Cache-Lebensdauer |
| `anidb_custom_field_name` | — | ❌ | Custom-Feld in Sonarr |
| `anidb_fallback_to_mapping` | — | ❌ | Fallback auf gespeichertes Mapping |

**Anmerkung:** AniDB ist besonders für Anime-User wichtig (Sublarrs Hauptzielgruppe). Alle 4 Felder fehlen in der UI. Sollte unter Connections oder einem eigenen Anime-Abschnitt erscheinen.

---

## 12. Remux

**Settings-Seite:** Keine.

| Config-Feld (Backend) | UI-Key (Frontend) | Status | Anmerkung |
|----------------------|------------------|--------|-----------|
| `remux_trash_dir` | — | ❌ | Trash-Verzeichnis für Backups |
| `remux_backup_retention_days` | — | ❌ | Backup-Aufbewahrung (0 = für immer) |
| `remux_use_reflink` | — | ❌ | CoW-Reflink auf Btrfs/XFS |
| `remux_arr_pause_enabled` | — | ❌ | Sonarr/Radarr während Remux pausieren |

**Anmerkung:** Das Remux-Feature ist komplett ohne UI. Diese Felder gehören in eine eigene "Remux"-Sektion.

---

## 13. Circuit Breaker & Provider-Stabilität

**Settings-Seite:** Keine.

| Config-Feld (Backend) | UI-Key (Frontend) | Status | Anmerkung |
|----------------------|------------------|--------|-----------|
| `circuit_breaker_failure_threshold` | — | ❌ | Fehler bis Circuit Breaker öffnet |
| `circuit_breaker_cooldown_seconds` | — | ❌ | Cooldown im OPEN-Zustand |
| `provider_auto_disable_cooldown_minutes` | — | ❌ | Cooldown für auto-deaktivierte Provider |

**Anmerkung:** Kann als Experten-Sektion unter Provider-Einstellungen.

---

## 14. Datenbank & Redis (Infrastructure)

**Settings-Seite:** Keine.

| Config-Feld (Backend) | UI-Key (Frontend) | Status | Anmerkung |
|----------------------|------------------|--------|-----------|
| `database_url` | — | ❌ 🔧 | PostgreSQL-URL statt SQLite |
| `db_pool_size` | — | ❌ 🔧 | SQLAlchemy Pool-Größe |
| `db_pool_max_overflow` | — | ❌ 🔧 | Max. Pool-Overflow |
| `db_pool_recycle` | — | ❌ 🔧 | Connection-Recycle-Zeit |
| `redis_url` | — | ❌ 🔧 | Redis-URL für Cache & Queue |
| `redis_cache_enabled` | — | ❌ 🔧 | Redis für Provider-Cache |
| `redis_queue_enabled` | — | ❌ 🔧 | Redis für Job-Queue |

**Empfehlung:** Diese Felder sind Deployment-Einstellungen die sinnvoll per ENV-Variable gesetzt werden. Ein einfaches "Advanced Infrastructure"-Panel mit diesen Feldern wäre hilfreich, muss aber nicht priorisiert werden.

---

## 15. Plugins

**Settings-Seite:** `ProvidersSettings.tsx` (Marketplace) — aber keine Plugin-Infrastruktur-Einstellungen.

| Config-Feld (Backend) | UI-Key (Frontend) | Status | Anmerkung |
|----------------------|------------------|--------|-----------|
| `plugins_dir` | — | ❌ | Plugin-Verzeichnis anzeigen/ändern |
| `plugin_hot_reload` | — | ❌ | Live-Reload bei Dateiänderungen |

---

## Gesamtübersicht

### Falsche Key-Namen (⚠️ — werden still ignoriert)

| Frontend-Key | Korrekter Backend-Key | Seite |
|-------------|----------------------|-------|
| `workers` | `scan_metadata_max_workers` / `translation_max_workers` | GeneralSettings |
| `log_to_file` | `log_file` (Pfad-String) | GeneralSettings |
| `translation_enabled` | — (existiert nicht) | GeneralSettings |
| `wanted_search_frequency` | `wanted_search_interval_hours` | AutomationSettings |
| `scan_on_start` | `wanted_search_on_startup` | AutomationSettings |
| `auto_upgrade_enabled` | `upgrade_enabled` | AutomationSettings |
| `auto_upgrade_threshold` | `upgrade_min_score_delta` | AutomationSettings |
| `upgrade_check_frequency` | `upgrade_scan_interval_hours` | AutomationSettings |
| `auto_translate` | `wanted_auto_translate` | AutomationSettings |
| `auto_search_on_download` | `webhook_auto_search` | AutomationSettings |
| `auto_sync` | `auto_sync_after_download` | AutomationSettings |
| `auto_cleanup` | `auto_cleanup_after_extract` | AutomationSettings |
| `keep_original_subs` | — (existiert nicht) | AutomationSettings |
| `sidecar_format` | — (existiert nicht) | AutomationSettings |

**→ 14 Config-Keys in der UI sind falsch oder nicht existent im Backend.**

### Fehlende Felder nach Priorität

**Hoch (direkt sichtbarer Nutzen):**
- Backup-Retention (daily/weekly/monthly) — Kommentar im Code verweist auf diese als "to configure in General tab" aber nie implementiert
- `wanted_search_interval_hours` (AutomationSettings fix)
- `upgrade_enabled` / `upgrade_min_score_delta` (AutomationSettings fix)
- `webhook_auto_search` / `webhook_auto_translate` (AutomationSettings fix)
- `notify_manual_actions`
- `anidb_enabled` + 3 weitere AniDB-Felder (Anime ist Hauptzielgruppe)
- `standalone_scan_interval_hours` / `standalone_skip_extras`
- Multi-Instanz Sonarr/Radarr UI

**Mittel:**
- `tmdb_api_key` / `tvdb_api_key` (für Standalone-Modus Metadaten)
- `temperature` / `batch_size` / `request_timeout` (Übersetzungsqualität)
- `dedup_on_download` / `provider_auto_prioritize`
- `auto_process_*` Felder (Post-Processing Pipeline vollständig konfigurierbar machen)
- `upgrade_window_days` / `upgrade_prefer_ass`
- `streaming_enabled`
- `github_token` (Plugin Marketplace Rate Limits)

**Niedrig / Experten:**
- Remux-Einstellungen (4 Felder)
- Circuit Breaker (2 Felder)
- Dynamic Provider Timeouts (5 Felder)
- Database/Redis Infrastructure (7 Felder)
- `plugin_hot_reload`
- `scan_yield_ms`

---

## Teil B — Konzeptionell fehlende Einstellungen

Settings die weder im Backend (`config.py`) noch in der UI existieren, aber für einen vollständigen Subtitle-Manager erwartet werden.

### B1 — Untertitel-Benennung (Dateinamen)

Aktuell gibt es keine Konfiguration wie Untertitel-Dateien benannt werden. Das ist eine häufige Quelle von Problemen bei verschiedenen Media-Playern.

| Fehlende Einstellung | Beschreibung | Beispiel |
|---------------------|-------------|---------|
| Sprachcode-Format | Welches ISO-Format für Sprachsuffixe | `de` vs `ger` vs `deu` |
| Suffix-Trennzeichen | Trennzeichen vor Sprachcode | `.de.ass` vs `_de.ass` |
| HI-Suffix | Suffix für HI-Untertitel | `.de.hi.ass` vs `.de.sdh.ass` |
| Forced-Suffix | Suffix für Forced-Untertitel | `.de.forced.ass` |
| Naming-Template | Vollständiges Template | `{title}.{lang}.{ext}` |

> Jellyfin, Plex und Kodi haben unterschiedliche Erwartungen — dieses Feature fehlt komplett.

### B2 — Ruhezeiten (Quiet Hours)

Die `NotificationsSettings.tsx` hat eine "Quiet Hours"-Sektion in der UI-Beschreibung, aber es gibt kein Config-Feld dafür im Backend.

| Fehlende Einstellung | Beschreibung |
|---------------------|-------------|
| `quiet_hours_enabled` | Ruhezeiten aktivieren |
| `quiet_hours_start` | Startzeit (z.B. `23:00`) |
| `quiet_hours_end` | Endzeit (z.B. `07:00`) |
| `quiet_hours_timezone` | Zeitzone für Ruhezeiten |

> Auch Automation (Wanted-Suche) sollte Ruhezeiten respektieren — nicht nur Benachrichtigungen.

### B3 — Interface-Einstellungen

| Fehlende Einstellung | Beschreibung |
|---------------------|-------------|
| Interface-Sprache | Deutsch / Englisch — i18n ist implementiert aber nicht in Settings konfigurierbar |
| Einträge pro Seite | Pagination-Größe (Library, History, Blacklist) — aktuell hardcodiert |
| Standard-Bibliotheksansicht | Grid oder Tabelle als Default speichern |
| Standard-Sortierung (Library) | Alphabetisch / Fehlend / Zuletzt hinzugefügt |
| Datum-/Zeitformat | ISO / Lokal / Relativ ("vor 2 Stunden") |

### B4 — Automatisches Backup

Das Backend hat Backup-Logik, aber keinen Zeitplan.

| Fehlende Einstellung | Beschreibung |
|---------------------|-------------|
| `backup_auto_enabled` | Automatisches Backup aktivieren |
| `backup_auto_interval_hours` | Intervall (z.B. alle 24h) |
| `backup_auto_on_startup` | Backup beim Start erstellen |
| `backup_notify_on_failure` | Benachrichtigung bei Backup-Fehler |

### B5 — Speicherplatz-Überwachung

| Fehlende Einstellung | Beschreibung |
|---------------------|-------------|
| `disk_warning_threshold_percent` | Warnung wenn Festplatte X% voll |
| `disk_warning_notify` | Benachrichtigung bei niedrigem Speicherplatz |

> Subtitle-Datenbanken und Backups können bei großen Bibliotheken erheblich wachsen.

### B6 — Ignore-Patterns (Bibliothek)

| Fehlende Einstellung | Beschreibung |
|---------------------|-------------|
| `scan_ignore_patterns` | Glob-Patterns für Dateien/Ordner die übersprungen werden (z.B. `**/extras/**`) |
| `scan_min_file_size_mb` | Dateien unter X MB ignorieren (Trailer-Erkennung) |
| `scan_ignore_languages` | Sprachen die nie in Wanted aufgenommen werden |

### B7 — Pro-Sprache Score-Schwellenwerte

Aktuell gibt es einen globalen Score-Schwellenwert. Verschiedene Sprachen haben aber sehr unterschiedliche Verfügbarkeit.

| Fehlende Einstellung | Beschreibung |
|---------------------|-------------|
| `score_threshold_per_language` | JSON-Map: `{"de": 60, "en": 40}` — unterschiedliche Mindestscores je Sprache |

> Für Deutsch ist ein Score von 60 realistisch, für seltene Sprachen reicht vielleicht 30.

### B8 — Download-Limits & Rate Limiting

| Fehlende Einstellung | Beschreibung |
|---------------------|-------------|
| `max_concurrent_provider_searches` | Wie viele Provider parallel suchen (Speicher/CPU) |
| `max_subtitle_file_size_kb` | Max. Dateigröße für Downloads (Schutz vor ZIP-Bomben-ähnlichen Angriffen) |
| `download_delay_between_providers_ms` | Wartezeit zwischen Provider-Anfragen (höfliches Scraping) |

### B9 — Übersetzungs-Kontext

| Fehlende Einstellung | Beschreibung |
|---------------------|-------------|
| `translation_use_episode_context` | Vorherige Episoden als Kontext einbeziehen |
| `translation_context_episodes` | Wie viele vorherige Episoden als Kontext |
| `translation_series_glossary_auto` | Automatisch Serien-Glossar aus bisherigen Übersetzungen aufbauen |

### B10 — Sicherheit (erweitert)

| Fehlende Einstellung | Beschreibung |
|---------------------|-------------|
| `session_timeout_minutes` | Automatischer Logout nach Inaktivität |
| `max_login_attempts` | Max. Fehlversuche vor Lockout (aktuell hardcodiert auf 20/60s) |
| `lockout_duration_minutes` | Lockout-Dauer nach zu vielen Fehlversuchen |
| `allowed_ip_ranges` | IP-Allowlist für Zugriff (z.B. nur LAN) |

---

## Gesamtbewertung

| Kategorie | Existiert im Backend | Hat UI | Konzeptionell erwartet |
|-----------|---------------------|--------|----------------------|
| Falsche Key-Namen (bugs) | ✅ | ⚠️ (kaputt) | — |
| Fehlende UI für Backend-Felder | ✅ | ❌ | — |
| Konzeptionell fehlend | ❌ | ❌ | ✅ |

**Priorisierung der konzeptionellen Lücken:**

| Priorität | Einstellung |
|-----------|-------------|
| Hoch | Ruhezeiten (B2) — UI-Sektion existiert schon, Backend fehlt |
| Hoch | Untertitel-Benennung (B1) — häufigste Kompatibilitätsfrage |
| Hoch | Interface-Sprache in Settings (B3) |
| Mittel | Automatisches Backup (B4) |
| Mittel | Einträge pro Seite / Standard-Ansicht (B3) |
| Mittel | Ignore-Patterns (B6) |
| Mittel | Speicherplatz-Überwachung (B5) |
| Niedrig | Pro-Sprache Score-Schwellenwerte (B7) |
| Niedrig | Übersetzungs-Kontext (B9) |
| Niedrig | Erweiterte Sicherheit (B10) |

---

*Stand: 2026-03-21 — Analyse basiert auf vollständigem Vergleich von `backend/config.py` mit allen `frontend/src/pages/Settings/*.tsx` Dateien.*
