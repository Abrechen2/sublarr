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

Bestehende Felder: Port, API-Key-Anzeige, Sprache — Design auf SettingsSection-Standard bringen.
Keine neuen Felder in dieser Section.

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
Fehlende Felder ergänzen:
- `wanted_search_max_items_per_run` — Number
- `wanted_max_search_attempts` — Number
- `wanted_auto_extract` — Toggle
- `wanted_anime_only` — Toggle
- `wanted_anime_movies_only` — Toggle
- `wanted_adaptive_backoff_enabled` — Toggle
- `wanted_backoff_base_hours` — Number (nur sichtbar wenn Backoff aktiv)
- `wanted_backoff_cap_hours` — Number (nur sichtbar wenn Backoff aktiv)
- `wanted_skip_srt_on_no_ass` — Toggle

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
- `auto_nfo_export` — Toggle
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
- `dedup_on_download` — Toggle
- `provider_auto_prioritize` — Toggle
- `provider_rate_limit_enabled` — Toggle
- `provider_search_timeout` — Number (Sekunden)
- `provider_cache_ttl_minutes` — Number
- `provider_auto_disable_cooldown_minutes` — Number

**Commit:** `feat: add provider config fields to ProvidersSettings installed section`

---

### Schritt 16 — ProvidersSettings › Marketplace-Section
**Datei:** `ProvidersSettings.tsx` — Section `providers-marketplace-section`

Bestehende Felder: Plugin-Marketplace.
Fehlende Felder ergänzen:
- `github_token` — Password-Input (höhere Rate-Limits beim Marketplace)

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

### Schritt 24 — NotificationsSettings › Quiet-Hours-Section (neu)
**Datei:** `NotificationsSettings.tsx` — neue Section

Neue Section mit eigener API (nicht `PATCH /config`):
- Toggle "Quiet Hours aktivieren" → `POST /api/v1/notifications/quiet-hours` bei An, `DELETE /<id>` bei Aus
- Time-Input "Von" (HH:MM) + "Bis" (HH:MM) → `PUT /api/v1/notifications/quiet-hours/<id>`
- Laden: `GET /api/v1/notifications/quiet-hours`

**Commit:** `feat: add quiet hours section to NotificationsSettings`

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

### Schritt 32 — Re-scan Series
**Dateien:** `SeriesHero.tsx` (Button verdrahten) + `backend/routes/library.py` (neue Route)

- `POST /api/v1/series/<id>/scan` implementieren
- Button: Loading-Spinner → Toast bei Erfolg/Fehler

**Commit:** `feat: wire re-scan series button to new backend route`

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

## Qualitätssicherung nach jedem Schritt

1. `docs/PROTECTED.md` aktualisieren (nach User-Bestätigung)
2. `cd frontend && npm run lint && npx tsc --noEmit`
3. Backend (wenn verändert): `cd backend && ruff check . && ruff format --check .`

---

*Spec-Status: Zur User-Freigabe bereit*
*36 Schritte — Phase 1: 2 | Phase 2: 29 | Phase 3: 5*
*Referenz: `mockups/concept-final.html`, `mockups/concept-drilldown.html`*
*Gap-Analyse: `docs/SETTINGS_GAP_ANALYSIS.md`, `docs/UI_GAP_ANALYSIS.md`*
