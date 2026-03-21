# Sublarr UI Improvement Plan — Design Spec

**Datum:** 2026-03-21
**Branch:** feature/frontend-redesign
**Granularität:** Ein Schritt = ein Tab/eine Section. Jeder Schritt = ein eigener Commit.

**Quellen:** Alle Feldnamen aus `backend/config.py` via `docs/SETTINGS_GAP_ANALYSIS.md` verifiziert.

---

## Grundregeln

1. **Ein Tab = ein Commit** — Nie mehr als einen Tab auf einmal anfassen.
2. **PROTECTED.md ist bindend** — Vor jeder Änderung prüfen. Bestätigte Bereiche nur mit expliziter Freigabe anfassen.
3. **Design-Referenz** — `mockups/concept-final.html` + `mockups/concept-drilldown.html`.
4. **Keys aus Gap-Analyse** — Jeden neuen Key gegen `SETTINGS_GAP_ANALYSIS.md` abgleichen.
5. **Funktion vor Design** — Phase 1 (Bugs) muss vor Phase 2 (Design) abgeschlossen sein.
6. **Nach Bestätigung** — `PROTECTED.md` sofort aktualisieren.

---

## Design-System (Quelle: `frontend/src/index.css` — nicht verändern)

```
--accent: #0f9bb5 (light) / #1DB8D4 (dark, via .dark class)
--bg-surface: #1f2228  --bg-elevated: #282c35
--text-primary: #e0e4ec  --text-muted: #4a5168
--border: #2a2e38
```

**Kanonische Komponenten (geschützt):** `SettingsSection`, `FormGroup`, `SettingsDetailLayout`, `SettingsCard`

---

## Phase 0 — Bereits erledigt (nicht anfassen)

✅ `index.css` Design-Tokens
✅ `SettingsSection`, `FormGroup`, `SettingsDetailLayout`, `SettingsCard`
✅ `SeriesDetail.tsx` + alle Series-Komponenten
✅ `ConnectionsSettings.tsx` (Basis — Sonarr/Radarr/MediaServer)

---

## Phase 1 — Config-Key-Bugs fixen

### Schritt 1 — GeneralSettings: 3 falsche Keys
**Datei:** `GeneralSettings.tsx`

| Frontend (falsch) | Backend (korrekt) | Aktion |
|---|---|---|
| `workers` | `translation_max_workers` + `scan_metadata_max_workers` | Zwei separate Number-Inputs |
| `log_to_file` (Boolean) | `log_file` (Pfad-String) | Key + Control-Typ |
| `translation_enabled` | *(existiert nicht)* | Entfernen |

**Commit:** `fix: correct config keys in GeneralSettings`

---

### Schritt 2 — AutomationSettings: Komplett-Rewrite (8 falsche Keys)
**Datei:** `AutomationSettings.tsx`

Alle Werte werden aktuell verworfen. Neu schreiben mit korrekten Keys + SettingsSection-Pattern:

| Frontend (falsch) | Backend (korrekt) |
|---|---|
| `wanted_search_frequency` | `wanted_search_interval_hours` |
| `scan_on_start` | `wanted_search_on_startup` |
| `auto_upgrade_enabled` | `upgrade_enabled` |
| `auto_upgrade_threshold` | `upgrade_min_score_delta` |
| `upgrade_check_frequency` | `upgrade_scan_interval_hours` |
| `auto_translate` | `wanted_auto_translate` |
| `auto_search_on_download` | `webhook_auto_search` |
| `auto_sync` | `auto_sync_after_download` |
| `auto_cleanup` | `auto_cleanup_after_extract` |
| `keep_original_subs` | *(existiert nicht → entfernen)* |
| `sidecar_format` | *(existiert nicht → entfernen)* |

**Commit:** `fix: rewrite AutomationSettings with correct backend config keys`

---

## Phase 2 — Tab für Tab: Design + fehlende Felder

---

### Schritt 3 — GeneralSettings › Interface-Section
**Datei:** `GeneralSettings.tsx` — Section `section-interface`

Bestehende Felder: Port, API-Key-Anzeige, `source_language`, `target_language` — Design auf SettingsSection-Standard bringen.
Wichtig bei Sprach-Dropdowns: Wenn `source_language` oder `target_language` geändert wird, müssen **beide** Companion-Felder mitgespeichert werden:
- `source_language_name` — Anzeigename der Quellsprache (aus Select-Label ableiten, z.B. `"English"`)
- `target_language_name` — Anzeigename der Zielsprache (aus Select-Label ableiten, z.B. `"German"`)
Diese Felder existieren in `config.py` und werden via `PATCH /api/v1/config` mitgesendet.

**Commit:** `feat: align GeneralSettings interface section to design standard`

---

### Schritt 4 — GeneralSettings › Paths & Workers-Section
**Datei:** `GeneralSettings.tsx` — Section `section-paths`

Bestehende Felder: `media_path`, `db_path` — korrekt.
Fehlende Felder ergänzen:
- `scan_metadata_max_workers` — Number Input (aus Schritt 1 übernommen)
- `translation_max_workers` — Number Input (aus Schritt 1 übernommen)
- `scan_metadata_engine` — Select: `ffprobe` | `mediainfo` | `auto`

**Commit:** `feat: add worker and engine fields to GeneralSettings paths section`

---

### Schritt 5 — GeneralSettings › Logging-Section
**Datei:** `GeneralSettings.tsx` — Section `section-logging`

Bestehende Felder: `log_level`.
Fehlende Felder ergänzen:
- `log_file` — Pfad-Input (aus Schritt 1 übernommen, war `log_to_file`)
- `log_format` — Select: `text` | `json`

**Commit:** `feat: add log_file and log_format to GeneralSettings logging section`

---

### Schritt 6 — AutomationSettings › Wanted & Scan-Section
**Datei:** `AutomationSettings.tsx` — Section `section-search-scan`

Bestehende (korrigierte) Felder: `wanted_search_interval_hours`, `wanted_search_on_startup`, `wanted_auto_translate`.
Fehlende Felder ergänzen — **zwei visuelle Untergruppen** innerhalb der Section:

**Untergruppe "Bibliotheks-Scan"** (File-Watcher-Subsystem):
- `wanted_scan_interval_hours` — Number (0 = event-driven/deaktiviert)
- `wanted_scan_on_startup` — Toggle

**Untergruppe "Untertitel-Suche"** (Subtitle-Search-Subsystem):
- `wanted_search_max_items_per_run` — Number
- `wanted_max_search_attempts` — Number
- `wanted_auto_extract` — Toggle
- `wanted_anime_only` — Toggle
- `wanted_anime_movies_only` — Toggle
- `wanted_adaptive_backoff_enabled` — Toggle
- `wanted_backoff_base_hours` — Number (conditional: nur sichtbar wenn Backoff aktiv)
- `wanted_backoff_cap_hours` — Number (conditional: nur sichtbar wenn Backoff aktiv)

> `wanted_skip_srt_on_no_ass` gehört zu SubtitlesSettings (Schritt 11) — nicht hier.

**Commit:** `feat: complete AutomationSettings wanted section`

---

### Schritt 7 — AutomationSettings › Upgrade-Rules-Section
**Datei:** `AutomationSettings.tsx` — Section `section-upgrade-rules`

Bestehende (korrigierte) Felder: `upgrade_enabled`, `upgrade_min_score_delta`, `upgrade_scan_interval_hours`.
Fehlende Felder ergänzen:
- `upgrade_window_days` — Number
- `upgrade_prefer_ass` — Toggle

**Commit:** `feat: complete AutomationSettings upgrade rules section`

---

### Schritt 8 — AutomationSettings › Webhook-Section (neu)
**Datei:** `AutomationSettings.tsx` — neue Section zwischen Upgrade und Processing

Fehlende Felder (alle in `config.py`):
- `webhook_delay_minutes` — Number
- `webhook_auto_scan` — Toggle
- `webhook_auto_search` — Toggle (aus Schritt 2 übernommen)
- `webhook_auto_translate` — Toggle

**Commit:** `feat: add webhook section to AutomationSettings`

---

### Schritt 9 — AutomationSettings › Processing-Pipeline-Section
**Datei:** `AutomationSettings.tsx` — Section `section-processing-pipeline`

Bestehende Felder: `auto_sync_after_download`.
Fehlende Felder ergänzen:
- `auto_process_common_fixes` — Toggle
- `auto_process_hi_removal` — Toggle
- `auto_process_credit_removal` — Toggle
- `auto_process_sync_threshold` — Number
- `auto_process_sync_fallback_engine` — Select: `ffsubsync` | `alass`
- `auto_nfo_export` — Toggle
- `streaming_enabled` — Toggle (Web-Player Streaming-Endpunkt)
- `jellyfin_play_translate_enabled` — Toggle

**Commit:** `feat: complete AutomationSettings processing pipeline section`

---

### Schritt 10 — AutomationSettings › Cleanup-Section
**Datei:** `AutomationSettings.tsx` — Section `section-sidecar-cleanup`

Bestehende (korrigierte) Felder: `auto_cleanup_after_extract`.
Fehlende Felder ergänzen:
- `auto_cleanup_keep_languages` — Text-Input (kommagetrennte Sprachcodes)
- `auto_cleanup_keep_formats` — Text-Input (kommagetrennte Formate)
- `subtitle_trash_retention_days` — Number

**Commit:** `feat: complete AutomationSettings cleanup section`

---

### Schritt 11 — SubtitlesSettings › Embedded-Extraction-Section
**Datei:** `SubtitlesSettings.tsx` — Section `section-embedded-extraction`

Bestehende Felder: `hi_preference`, `forced_preference`.
Fehlende Felder ergänzen:
- `hi_removal_enabled` — Toggle
- `use_embedded_subs` — Toggle
- `wanted_skip_srt_on_no_ass` — Toggle

**Commit:** `feat: complete SubtitlesSettings embedded extraction section`

---

### Schritt 12 — SubtitlesSettings › Fansub-Preferences-Section
**Datei:** `SubtitlesSettings.tsx` — Section `section-fansub`

Bestehende Felder: `release_group_prefer`, `release_group_exclude`, `release_group_prefer_bonus`.
Fehlende Felder ergänzen:
- `credit_threshold_sec` — Number (Sekunden vom Ende)
- `op_window_sec` — Number (OP/ED-Erkennungsfenster)

Design auf SettingsSection-Standard bringen.

**Commit:** `feat: complete SubtitlesSettings fansub preferences section`

---

### Schritt 13 — SubtitlesSettings › Scoring-Tab
**Datei:** `EventsTab.tsx` — `ScoringTab` Komponente

Bestehende Felder prüfen, Design auf Standard bringen. Keine neuen Felder bekannt.

**Commit:** `feat: align SubtitlesSettings scoring tab to design standard`

---

### Schritt 14 — SubtitlesSettings › Format-Tools-Section
**Datei:** `SubtitlesSettings.tsx` + `AdvancedTab.tsx` — Section `section-format-tools`

Design auf Standard bringen. Keine neuen Felder bekannt.

**Commit:** `feat: align SubtitlesSettings format tools section to design standard`

---

### Schritt 15 — ProvidersSettings › Installed-Providers-Section
**Datei:** `ProvidersSettings.tsx` — Section `providers-installed-section`

Bestehende Felder: Provider-Grid, Prioritäten, Credentials pro Provider.
Fehlende Felder ergänzen:
- `providers_hidden` — Text-Input (kommagetrennte Provider-IDs; Provider aus der UI ausblenden)
- `dedup_on_download` — Toggle
- `provider_auto_prioritize` — Toggle
- `provider_rate_limit_enabled` — Toggle
- `provider_search_timeout` — Number (Sekunden)
- `provider_cache_ttl_minutes` — Number
- `provider_auto_disable_cooldown_minutes` — Number

**Commit:** `feat: add provider config fields to ProvidersSettings installed section`

---

### Schritt 16 — ProvidersSettings › Marketplace-Section + Plugin-Infrastruktur
**Datei:** `ProvidersSettings.tsx` — Section `providers-marketplace-section`

Bestehende Felder: Plugin-Marketplace.
Fehlende Felder ergänzen:
- `github_token` — Password-Input (höhere Rate-Limits beim Marketplace)
- `plugins_dir` — Pfad-Input (Plugin-Verzeichnis, read-only wenn kein custom path)
- `plugin_hot_reload` — Toggle (Live-Reload bei Dateiänderungen)

Design auf Standard bringen.

**Commit:** `feat: add github_token to ProvidersSettings marketplace section`

---

### Schritt 17 — ProvidersSettings › Anti-Captcha + Cache-Section
**Datei:** `ProvidersSettings.tsx` — Section `providers-anticaptcha-section` + `providers-cache-section`

Bestehende Felder: `anti_captcha_provider`, `anti_captcha_api_key`.
Design auf Standard bringen. Keine neuen Felder.

**Commit:** `feat: align ProvidersSettings anti-captcha and cache sections to design standard`

---

### Schritt 18 — ProvidersSettings › Reranking + Dynamic Timeouts (Advanced)
**Datei:** `ProvidersSettings.tsx` — neue Advanced-Section

Fehlende Felder (alle in `config.py`):
- `provider_reranking_enabled` — Toggle
- `provider_reranking_min_downloads` — Number
- `provider_reranking_max_modifier` — Number
- `provider_dynamic_timeout_enabled` — Toggle
- `provider_dynamic_timeout_min_samples` — Number
- `provider_dynamic_timeout_multiplier` — Number
- `provider_dynamic_timeout_buffer_secs` — Number
- `provider_dynamic_timeout_min_secs` — Number
- `provider_dynamic_timeout_max_secs` — Number
- `circuit_breaker_failure_threshold` — Number
- `circuit_breaker_cooldown_seconds` — Number

Als aufklappbare Advanced-Sektion (SettingsSection mit `advanced`-Prop).

**Commit:** `feat: add reranking, dynamic timeouts and circuit breaker to ProvidersSettings`

---

### Schritt 19 — TranslationSettings › Backends-Tab
**Datei:** `TranslationTab.tsx` — `TranslationBackendsTab`

Bestehende Felder: `ollama_url`, `ollama_model`, `max_retries`.
Fehlende Felder ergänzen:
- `request_timeout` — Number (Sekunden)
- `backoff_base` — Number

Design auf Standard bringen.

**Commit:** `feat: complete TranslationSettings backends tab`

---

### Schritt 20 — TranslationSettings › Quality-Section
**Datei:** `TranslationTab.tsx` — `TranslationQualitySection`

Fehlende Felder ergänzen:
- `temperature` — Number (0.0–1.0)
- `batch_size` — Number

Design auf Standard bringen.

**Commit:** `feat: complete TranslationSettings quality section`

---

### Schritt 21 — TranslationSettings › Glossar-Section
**Datei:** `TranslationTab.tsx` — `GlobalGlossaryPanel`

Bestehende Felder: Glossar-Anzeige.
Fehlende Felder ergänzen:
- `glossary_max_terms` — Number

Design auf Standard bringen. (CRUD-Funktionalität kommt in Schritt 33.)

**Commit:** `feat: add glossary_max_terms to TranslationSettings glossary section`

---

### Schritt 22 — TranslationSettings › Auto-Sync-Section
**Datei:** `TranslationTab.tsx` — `AutoSyncSection`

Bestehende Felder: `auto_sync_engine`.
Design auf Standard bringen. Keine neuen Felder.

**Commit:** `feat: align TranslationSettings auto-sync section to design standard`

---

### Schritt 23 — NotificationsSettings › Channels-Section
**Datei:** `NotificationsSettings.tsx` — Section `section-notification-channels`

Bestehende Felder: `notification_urls_json`, `notify_on_*` Toggles.
Fehlende Felder ergänzen:
- `notify_manual_actions` — Toggle

Design auf Standard bringen.

**Commit:** `feat: add notify_manual_actions to NotificationsSettings channels section`

---

### Schritt 24 — NotificationsSettings › Quiet-Hours-Section (Stub)
**Datei:** `NotificationsSettings.tsx` — neue Section

> **Wichtig:** Dieser Schritt baut nur den UI-Stub mit deaktivierten Controls und einem Info-Banner "Backend-Felder werden in Schritt 39 ergänzt". Keine API-Calls. Verwendet `PATCH /api/v1/config` (nicht eigene Route) — das ist konsistent mit allen anderen Settings.

Stub-Felder (disabled, Werte aus Config sobald Schritt 39 deployed):
- Toggle "Quiet Hours aktivieren" (`quiet_hours_enabled`)
- Time-Input "Von" (HH:MM) (`quiet_hours_start`)
- Time-Input "Bis" (HH:MM) (`quiet_hours_end`)
- Select Zeitzone (`quiet_hours_timezone`)

**Commit:** `feat: add quiet hours UI stub to NotificationsSettings (backend fields in Step 39)`

---

### Schritt 25 — ConnectionsSettings › Sonarr Multi-Instanz
**Datei:** `ConnectionsSettings.tsx` — `SonarrSection`

Ersetzt Einzel-Felder durch Instanz-Liste (approved Design):
- Instanz-Karte: Status-Dot, editierbarer Name (✎ bei Hover), URL, API-Key + Testen
- Status-Badges: "Standard", "Verbunden"/"Fehler"
- "Entfernen"-Button (ghost, hover → rot)
- "+ Sonarr-Instanz hinzufügen" (gestrichelter Button)
- Backend-Key: `sonarr_instances_json`

**Commit:** `feat: add Sonarr multi-instance UI to ConnectionsSettings`

---

### Schritt 26 — ConnectionsSettings › Radarr Multi-Instanz
**Datei:** `ConnectionsSettings.tsx` — `RadarrSection`

Identisch zu Schritt 25, für Radarr.
- Backend-Key: `radarr_instances_json`

**Commit:** `feat: add Radarr multi-instance UI to ConnectionsSettings`

---

### Schritt 27 — ConnectionsSettings › API-Keys (Metadaten)
**Datei:** `ApiKeysTab.tsx` oder neue Section in `ConnectionsSettings.tsx`

Fehlende Felder ergänzen (alle in `config.py`):
- `tmdb_api_key` — Password-Input
- `tvdb_api_key` — Password-Input
- `tvdb_pin` — Password-Input
- `metadata_cache_ttl_days` — Number
- `ffmpeg_timeout` — Number (Advanced)

**Commit:** `feat: add metadata API keys section to ConnectionsSettings`

---

### Schritt 28 — SystemSettings › Backup-Retention-Felder
**Datei:** `SystemSettings.tsx` — Section `section-backup-restore`

Fehlende Felder ergänzen (alle in `config.py`):
- `backup_dir` — Pfad-Input
- `backup_retention_daily` — Number
- `backup_retention_weekly` — Number
- `backup_retention_monthly` — Number

**Commit:** `feat: add backup retention fields to SystemSettings`

---

### Schritt 29 — SystemSettings › AniDB-Section (neu)
**Datei:** `SystemSettings.tsx` — neue Section

Fehlende Felder (alle in `config.py`):
- `anidb_enabled` — Toggle
- `anidb_cache_ttl_days` — Number
- `anidb_custom_field_name` — Text-Input
- `anidb_fallback_to_mapping` — Toggle

**Commit:** `feat: add AniDB section to SystemSettings`

---

### Schritt 30 — SystemSettings › Remux-Section (neu)
**Datei:** `SystemSettings.tsx` — neue Section

Fehlende Felder (alle in `config.py`):
- `remux_trash_dir` — Pfad-Input
- `remux_backup_retention_days` — Number
- `remux_use_reflink` — Toggle
- `remux_arr_pause_enabled` — Toggle

**Commit:** `feat: add remux section to SystemSettings`

---

### Schritt 31 — SystemSettings › Standalone-Section (neu)
**Datei:** `SystemSettings.tsx` — neue Section

Fehlende Felder (alle in `config.py`):
- `standalone_scan_interval_hours` — Number
- `standalone_debounce_seconds` — Number
- `standalone_skip_extras` — Toggle

**Commit:** `feat: add standalone section to SystemSettings`

---

## Phase 3 — Neue Features & Seiten

---

### Schritt 32 — Re-scan Series + NFO Export Button
**Dateien:** `SeriesHero.tsx` (Buttons verdrahten) + `backend/routes/library.py` (Re-scan-Route)

- `POST /api/v1/series/<id>/scan` implementieren (Re-scan)
- Re-scan-Button: Loading-Spinner → Toast bei Erfolg/Fehler
- NFO Export Button verdrahten → `POST /api/v1/subtitles/export-nfo` mit `series_id` Parameter (Route existiert bereits)
- Analoger Button in zukünftiger MovieDetailPage (Schritt 36) — gleiche Route

**Commit:** `feat: wire re-scan series and NFO export buttons`

---

### Schritt 33 — Glossar CRUD
**Datei:** `TranslationTab.tsx` — `GlobalGlossaryPanel`

Zu bestehender Anzeige hinzufügen:
- Hinzufügen: Modal → `POST /api/v1/glossary`
- Bearbeiten: Modal → `PUT /api/v1/glossary/<id>`
- Löschen: Dialog → `DELETE /api/v1/glossary/<id>`
- Exportieren: Button → `GET /api/v1/glossary/export`

**Commit:** `feat: add CRUD and export to GlossaryPanel`

---

### Schritt 34 — Backup-Management UI
**Datei:** `SystemSettings.tsx` — Section `section-backup-restore` erweitern

Zu bestehenden Retention-Feldern (Schritt 28) hinzufügen:
- Backup auslösen → `POST /api/v1/backup/full`
- Backup-Liste → `GET /api/v1/backup/full/list`
- Download pro Eintrag → `GET /api/v1/backup/full/download/<filename>`
- Restore pro Eintrag → Dialog → `POST /api/v1/backup/full/restore`

**Commit:** `feat: add backup management UI to SystemSettings`

---

### Schritt 35 — Sprachprofil-Verwaltungsseite
**Neue Datei:** `frontend/src/pages/LanguageProfiles.tsx`

CRUD-Seite:
- Liste aller Profile (Karten) — `GET /api/v1/language-profiles`
- Neu → Modal → `POST /api/v1/language-profiles`
- Bearbeiten → Modal → `PUT /api/v1/language-profiles/<id>`
- Löschen → Dialog → `DELETE /api/v1/language-profiles/<id>`
- Felder: Name, Sprachen (Multi-Select), Cutoff-Score, Upgrade-Score

Route: `/settings/language-profiles` in `App.tsx`

**Commit:** `feat: add Language Profiles management page`

---

### Schritt 36 — MovieDetailPage
**Neue Datei:** `frontend/src/pages/MovieDetail.tsx`

Analog zu `SeriesDetail.tsx`:
- Hero: Poster, Metadaten, Action-Buttons (Suchen, Übersetzen, Re-scan)
- Keine Season-Tabs
- Subtitle-Liste statt Episode-Grid
- Settings-Panel analog zu `SeriesSettingsPanel`

Route: `/movies/<id>` in `App.tsx`

**Commit:** `feat: add MovieDetailPage analogous to SeriesDetailPage`

---

## Phase 4 — Konzeptionell fehlende Backend-Felder + UI

> Diese Schritte erfordern neue Felder in `backend/config.py` (Pydantic Settings) UND neue UI. Keine DB-Migration nötig — neue Pydantic-Felder werden beim ersten PATCH automatisch persistiert.
>
> **Deploy-Reihenfolge:** Backend-Code MUSS vor dem Frontend deployed sein. Das Pydantic-Feld muss in `Settings.model_fields` existieren, bevor der PATCH-Endpoint es akzeptiert. Im Dev-Modus (`npm run dev`) gilt das automatisch durch gleichzeitigen Neustart.

---

### Schritt 37 — GeneralSettings › Interface-Einstellungen (B3)
**Dateien:** `backend/config.py` + `GeneralSettings.tsx`

Neue `config.py`-Felder:
- `interface_language: str = "en"` — Sprachauswahl (en/de)
- `items_per_page: int = 25` — Einträge pro Seite (25/50/100)
- `default_library_view: str = "grid"` — Standard-Bibliotheksansicht (grid/table)
- `default_library_sort: str = "alpha"` — Standard-Sortierung (alpha/missing/recent)
- `datetime_format: str = "relative"` — Datum-/Zeitformat (iso/local/relative)

**Commit:** `feat: add interface settings fields (language, pagination, view defaults)`

---

### Schritt 38 — SubtitlesSettings › Untertitel-Benennung (B1)
**Dateien:** `backend/config.py` + `SubtitlesSettings.tsx`

Neue `config.py`-Felder:
- `subtitle_language_code_format: str = "iso_639_1"` — Sprachcode-Format (iso_639_1/iso_639_2b/iso_639_2t)
- `subtitle_suffix_separator: str = "dot"` — Trennzeichen (dot/underscore)
- `subtitle_hi_suffix: str = "hi"` — HI-Suffix (z.B. `de.hi.ass`)
- `subtitle_forced_suffix: str = "forced"` — Forced-Suffix

**Commit:** `feat: add subtitle file naming configuration fields`

---

### Schritt 39 — NotificationsSettings › Ruhezeiten-Backend (B2)
**Dateien:** `backend/config.py` + `NotificationsSettings.tsx` (Schritt 24 ergänzt)

Neue `config.py`-Felder:
- `quiet_hours_enabled: bool = False`
- `quiet_hours_start: str = "23:00"`
- `quiet_hours_end: str = "07:00"`
- `quiet_hours_timezone: str = "UTC"`

> Schritt 24 hat die UI bereits als Stub — diese Felder ermöglichen nun `PATCH /api/v1/config` statt eigener Route.

**Commit:** `feat: add quiet hours backend config fields and wire to NotificationsSettings UI`

---

### Schritt 40 — SystemSettings › Automatische Backups (B4)
**Dateien:** `backend/config.py` + `SystemSettings.tsx`

Neue `config.py`-Felder:
- `backup_auto_enabled: bool = False`
- `backup_auto_interval_hours: int = 24`
- `backup_auto_on_startup: bool = False`
- `backup_notify_on_failure: bool = True`

**Commit:** `feat: add auto backup schedule fields to config and SystemSettings`

---

### Schritt 41 — SystemSettings › Speicherplatz-Überwachung (B5)
**Dateien:** `backend/config.py` + `SystemSettings.tsx`

Neue `config.py`-Felder:
- `disk_warning_threshold_percent: int = 90`
- `disk_warning_notify: bool = True`

**Commit:** `feat: add disk space monitoring config fields and UI`

---

### Schritt 42 — SubtitlesSettings › Scan Ignore-Patterns (B6)
**Dateien:** `backend/config.py` + `SubtitlesSettings.tsx`

Neue `config.py`-Felder:
- `scan_ignore_patterns: str = "[]"` — JSON-Array von Glob-Patterns
- `scan_min_file_size_mb: float = 0.0` — Min. Dateigröße
- `scan_ignore_languages: str = "[]"` — JSON-Array von Sprachcodes

**Commit:** `feat: add scan ignore patterns and filters to config and SubtitlesSettings`

---

### Schritt 43 — SubtitlesSettings › Pro-Sprache Score-Schwellenwerte (B7)
**Dateien:** `backend/config.py` + `SubtitlesSettings.tsx`

Neue `config.py`-Felder:
- `score_threshold_per_language: str = "{}"` — JSON-Map (`{"de": 60, "en": 40}`)

UI: JSON-Editor oder Sprache+Score-Zeilen mit Add/Remove.

**Commit:** `feat: add per-language score threshold config and UI`

---

### Schritt 44 — ProvidersSettings › Download-Limits (B8)
**Dateien:** `backend/config.py` + `ProvidersSettings.tsx`

Neue `config.py`-Felder:
- `max_concurrent_provider_searches: int = 3`
- `max_subtitle_file_size_kb: int = 2048`
- `download_delay_between_providers_ms: int = 0`

**Commit:** `feat: add download limits and rate controls to config and ProvidersSettings`

---

### Schritt 45 — TranslationSettings › Übersetzungskontext (B9)
**Dateien:** `backend/config.py` + `TranslationTab.tsx`

Neue `config.py`-Felder:
- `translation_use_episode_context: bool = False`
- `translation_context_episodes: int = 1`
- `translation_series_glossary_auto: bool = False`

**Commit:** `feat: add translation context settings to config and TranslationSettings`

---

### Schritt 46 — SystemSettings › Erweiterte Sicherheit (B10)
**Dateien:** `backend/config.py` + `SecurityTab.tsx`

Neue `config.py`-Felder:
- `session_timeout_minutes: int = 0` — 0 = kein Auto-Logout
- `max_login_attempts: int = 20` — Standardwert matcht `_FAIL_LIMIT = 20` in `auth.py`
- `lockout_duration_minutes: int = 60`
- `allowed_ip_ranges: str = ""` — kommagetrennte CIDR-Ranges

**Backend-Änderung erforderlich:** `backend/auth.py` muss angepasst werden, um `max_login_attempts` und `lockout_duration_minutes` aus Settings zu lesen. Das aktuelle Sliding-Window-System (`_FAIL_WINDOW = 60s`) muss zu einem konfigurierbaren Hard-Lockout geändert werden. Die config.py-Felder allein reichen nicht — `auth.py` muss die Werte aktiv einlesen.

**Commit:** `feat: add extended security settings to config + wire to auth.py`

---

## Phase 5 — Fehlende UI für vorhandene Backend-Features

> Diese Schritte benötigen keine neuen Backend-Felder — die Routen existieren bereits.

---

### Schritt 47 — SystemSettings › Einstellungen Export/Import (A8)
**Datei:** `SystemSettings.tsx` — neue Section

- Export → `GET /api/v1/config/export` → Browser-Download
- Import → File-Upload → `POST /api/v1/config/import` → Bestätigungs-Dialog

**Commit:** `feat: add settings export/import UI to SystemSettings`

---

### Schritt 48 — TranslationSettings › Translation Memory & Ollama Pull (A6)
**Datei:** `TranslationTab.tsx` — neue Section

- Stats → `GET /api/v1/translation-memory/stats` → Anzeige (Einträge, Größe)
- Cache leeren → `DELETE /api/v1/translation-memory/cache` → Bestätigungs-Dialog
- Ollama-Modell herunterladen → Eingabefeld + Button → `POST /api/v1/backends/ollama/pull` → Progress (SocketIO oder Polling)

**Commit:** `feat: add translation memory management and Ollama model pull to TranslationSettings`

---

### Schritt 49 — NotificationsSettings › Benachrichtigungsverlauf (A5)
**Datei:** `NotificationsSettings.tsx` — neue Section oder Tab

- Liste → `GET /api/v1/notifications/history` — Tabelle (Zeit, Event, Status)
- Erneut senden → `POST /api/v1/notifications/history/<id>/resend`

**Commit:** `feat: add notification history section to NotificationsSettings`

---

### Schritt 50 — Hook Manager (A4)
**Neue Datei:** `frontend/src/pages/Hooks.tsx`

CRUD + Test + Logs:
- Liste → `GET /api/v1/hooks`
- Neu/Bearbeiten → Modal → `POST`/`PUT /api/v1/hooks/<id>`
- Löschen → Dialog → `DELETE /api/v1/hooks/<id>`
- Testen → Button → `POST /api/v1/hooks/<id>/test` → Toast
- Logs → Panel → `GET /api/v1/hooks/logs` + `DELETE /api/v1/hooks/logs`

Route: `/settings/hooks` in `App.tsx`

**Commit:** `feat: add Hook Manager page with CRUD, test, and logs`

---

### Schritt 51 — Subtitle Editor › Format-Tools (A7)
**Dateien:** Subtitle-Editor-Komponente (bestehend)

Toolbar-Erweiterungen:
- Zeilen aufteilen → `POST /api/v1/split-lines`
- Timing normalisieren → `POST /api/v1/timing-normalize`
- Format konvertieren → Dropdown + Button → `POST /api/v1/convert`

**Commit:** `feat: add split-lines, timing-normalize and format-convert tools to subtitle editor`

---

## Phase 6 — Vollständige Feature-Abdeckung (bisher nicht abgedeckte Gap-Items)

> Alle restlichen Punkte aus `UI_GAP_ANALYSIS.md` A1–A9 und B1–B7. Backend-Routen existieren bereits.

---

### Schritt 52 — Library › Saison-Batch-Aktionen (B1)
**Dateien:** `SeriesDetail.tsx` + `backend/routes/library.py` (neue Route)

- Neue Backend-Route: `POST /api/v1/series/<id>/seasons/<n>/search` implementieren (existiert noch nicht)
- Button "Alle fehlenden suchen" pro Season-Tab, Loading-State, Toast bei Erfolg/Fehler

**Commit:** `feat: add season-level batch search route and UI action`

---

### Schritt 53 — Dashboard › Update-Check & Changelog (B4)
**Datei:** Neue Komponente in Dashboard oder `SystemSettings.tsx`

- Update-Check → `GET /api/v1/update` → Badge/Banner "Neue Version verfügbar"
- Changelog-Modal oder Inline-Anzeige
- Auto-Check beim App-Start (einmal pro Session)

**Commit:** `feat: add update check and changelog display to dashboard`

---

### Schritt 54 — Library › Provider Rate-Limit-Status (B4)
**Datei:** Dashboard oder neue StatusPanel-Komponente

- Verbleibende Quota pro Provider (aus Provider-Antworten)
- Route: Erweiterung von `GET /api/v1/providers/status` oder eigene Route
- Anzeige als kleine Badges im Provider-Grid

**Commit:** `feat: add provider rate limit and circuit breaker status display`

---

### Schritt 55 — System › ffprobe-Cache-Verwaltung (B4)
**Datei:** `SystemSettings.tsx` — neue Subsection unter "System"

- Stats → `GET /api/v1/cache/ffprobe/stats` — Einträge, Größe, Hit-Rate
- Cleanup → Button → `POST /api/v1/cache/ffprobe/cleanup` → Bestätigungs-Dialog

**Commit:** `feat: add ffprobe cache stats and cleanup to SystemSettings`

---

### Schritt 56 — Wanted › Batch-Übersetzen (A6)
**Datei:** Wanted-Seite (bestehend)

- "Alle übersetzen" Schaltfläche → `POST /api/v1/wanted/batch-translate`
- Progress-Anzeige via SocketIO oder Polling
- Filter: nur untranslatete Items

**Commit:** `feat: add batch translate action to Wanted page`

---

### Schritt 57 — Wanted › Cleanup & Refresh (A8)
**Datei:** Wanted-Seite (bestehend)

- "Aufräumen" → `POST /api/v1/wanted/cleanup` — verwaiste Wanted-Einträge löschen
- "Aktualisieren" → `POST /api/v1/wanted/refresh` — Wanted-Liste neu aufbauen
- Buttons als Secondary-Actions in der Wanted-Toolbar

**Commit:** `feat: add cleanup and refresh actions to Wanted page`

---

### Schritt 58 — Translation › Backend-Statistiken (B4)
**Datei:** `TranslationTab.tsx` — neue Stats-Section

- Stats → `GET /api/v1/backends/stats` — Erfolgsquote, Latenz, Token-Verbrauch pro Backend
- Anzeige als Karten/Tabelle

**Commit:** `feat: add translation backend stats section to TranslationSettings`

---

### Schritt 59 — Library › Kompatibilitäts-Check (A1)
**Datei:** `SeriesDetail.tsx` und `MovieDetail.tsx`

- Check-Button → `POST /api/v1/compat-check` (Serien) / `POST /api/v1/compat-check/single` (Film)
- Ergebnis-Modal: Kompatibilität der gefundenen Untertitel mit dem Player

**Commit:** `feat: add compatibility check button to series and movie detail pages`

---

### Schritt 60 — Import › Bazarr-Import-Wizard (B6)
**Neue Datei:** `frontend/src/pages/BazarrImport.tsx`

- Step 1: Pfad-Eingabe für Bazarr-Datenbank
- Step 2: Vorschau (wie viele Items werden importiert)
- Step 3: Import starten → `POST /api/v1/import/bazarr` → Progress
- Route: `/import/bazarr`

**Commit:** `feat: add Bazarr import wizard page`

---

### Schritt 61 — System › Datenbank-Vacuum (A8)
**Datei:** `SystemSettings.tsx` — Section "Datenbank"

- "Datenbank optimieren" → `POST /api/v1/database/vacuum` → Toast
- Info-Text: "Reduziert die Datenbankgröße und verbessert die Performance"

**Commit:** `feat: add database vacuum action to SystemSettings`

---

### Schritt 62 — SeriesDetail/MovieDetail › Whisper Transkription (B7)
**Dateien:** `SeriesDetail.tsx` / `MovieDetail.tsx`

- "Audio → Untertitel" Button bei Episode → `POST /api/v1/transcribe` mit `episode_id`
- Modell-Auswahl (Whisper-Größe) im Dialog
- Progress via SocketIO

**Commit:** `feat: add Whisper transcription action to episode detail`

---

### Schritt 63 — SeriesDetail › OP/ED-Erkennung (B7)
**Datei:** `SeriesDetail.tsx` — Episode-Aktionen

- "OP/ED erkennen" Button → `POST /api/v1/detect-opening-ending` mit `episode_id`
- Ergebnis-Anzeige: erkannte Zeitfenster
- Option: "Erkannte Fenster aus Untertiteln ausschließen"

**Commit:** `feat: add OP/ED detection action to episode detail`

---

### Schritt 64 — System › AniDB-Mapping-Verwaltung (B7)
**Datei:** `SystemSettings.tsx` — AniDB-Section (aus Schritt 29) erweitern

- Cache-Einträge → `GET /api/v1/anidb/mappings` (Route prüfen in `backend/routes/` — ggf. neu anlegen)
- Manuell überschreiben → `PUT /api/v1/anidb/mappings/<anidb_id>` → ID-Mapping-Tabelle
- Cache leeren → `DELETE /api/v1/anidb/cache`

> Falls diese Routen noch nicht existieren: in `backend/routes/anidb.py` anlegen (analog zu anderen Management-Routen).

**Commit:** `feat: add AniDB mapping cache viewer and management to SystemSettings`

---

### Schritt 65 — Settings › Eingehende Webhooks konfigurieren (A1)
**Neue Datei:** `frontend/src/pages/WebhooksSettings.tsx` (oder neue Section in `ConnectionsSettings.tsx`)

> Separate Feature von Hook Manager (Schritt 50). Eingehende Webhooks = Sonarr/Radarr/externe Systeme rufen Sublarr an. Hook Manager = Sublarr ruft externe Systeme an.

- Liste → `GET /api/v1/webhooks`
- Neu/Bearbeiten → Modal → `POST`/`PUT /api/v1/webhooks/<id>`
- Löschen → Dialog → `DELETE /api/v1/webhooks/<id>`
- Jeder Webhook: Name, Event-Typ, Secret, Aktiviert-Toggle
- Anzeige der Webhook-URL die Sonarr/Radarr konfigurieren muss

Route: `/settings/webhooks` in `App.tsx`

**Commit:** `feat: add incoming webhook configuration page`

---

### Schritt 66 — System › Remux-UI (B7)
**Datei:** `SeriesDetail.tsx` / `MovieDetail.tsx`

Routen aus `backend/routes/remux.py` (bereits vorhanden — Routen prüfen):
- Remux starten → `POST /api/v1/remux` mit `{ media_id, media_type }` — Konfigurations-Dialog vor Start
- Status abfragen → `GET /api/v1/remux/status/<job_id>` (oder SocketIO-Event)
- Ergebnis-Toast: Erfolg / Fehler mit Backup-Pfad
- Einstellungen (remux_trash_dir, remux_backup_retention_days, etc.) kommen aus Schritt 30

> Implementierungshinweis: Routen aus `backend/routes/remux.py` lesen bevor UI gebaut wird — tatsächliche Endpoint-Namen verifizieren.

**Commit:** `feat: add Remux action UI to series and movie detail pages`

---

## Qualitätssicherung nach jedem Schritt

1. `docs/PROTECTED.md` aktualisieren (nach User-Bestätigung oder bei autonomem Batch)
2. `cd frontend && npm run lint && npx tsc --noEmit`
3. Backend (wenn verändert): `cd backend && ruff check . && ruff format --check .`

---

*Spec-Status: Vollständig — alle Gap-Analysis-Punkte abgedeckt (2026-03-21)*
*66 Schritte — Phase 1: 2 | Phase 2: 29 | Phase 3: 5 | Phase 4: 10 | Phase 5: 5 | Phase 6: 15*
*Korrekturen: wanted_scan_interval_hours + wanted_scan_on_startup (Step 6), auto_process_sync_fallback_engine + streaming_enabled (Step 9), NFO-Export-Button (Step 32), Quiet Hours Stub statt eigene API (Step 24), wanted_skip_srt_on_no_ass nur in Step 11, providers_hidden (Step 15), source_language_name (Step 3), auth.py Hinweis (Step 46)*
*Referenz: `mockups/concept-final.html`, `mockups/concept-drilldown.html`*
*Gap-Analyse: `docs/SETTINGS_GAP_ANALYSIS.md`, `docs/UI_GAP_ANALYSIS.md`*
