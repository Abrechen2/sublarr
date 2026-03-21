# Sublarr UI Improvement Plan — Design Spec

**Datum:** 2026-03-21
**Branch:** feature/frontend-redesign
**Ziel:** Alle Settings-Seiten auf Mockup-Standard bringen, Config-Key-Bugs fixen, fehlende Felder ergänzen, neue Seiten und Features hinzufügen — ohne bereits funktionierende Bereiche zu beschädigen.

**Quellen:** Alle Feldnamen stammen direkt aus `backend/config.py` via `docs/SETTINGS_GAP_ANALYSIS.md`. Kein Feld darf ohne Verifikation gegen diese Quelle implementiert werden.

---

## Grundregeln

1. **Jede Datei nur einmal anfassen** — Abhängigkeitsbasierte Reihenfolge: tiefere Schichten zuerst.
2. **PROTECTED.md ist bindend** — Vor jeder Änderung muss `docs/PROTECTED.md` geprüft werden. Bestätigte Bereiche dürfen nur mit expliziter User-Freigabe angefasst werden.
3. **Eine Einheit = ein Commit** — Jede Settings-Seite, jedes Feature = separater, atomarer Commit.
4. **Design-Referenz** — `mockups/concept-final.html` und `mockups/concept-drilldown.html` sind verbindlich für alle visuellen Entscheidungen.
5. **Funktion vor Design** — Config-Key-Bugs zuerst fixen (Phase 1), dann Design angleichen (Phase 2).
6. **Keys aus Gap-Analyse** — Jeder neue UI-Key muss mit `SETTINGS_GAP_ANALYSIS.md` abgeglichen werden, bevor er implementiert wird.

---

## Design-System (nicht veränderbar)

Quelle der Wahrheit: `frontend/src/index.css`. Tokens nicht im Code hardcoden, immer CSS-Variable verwenden.

```css
--accent: #0f9bb5          /* light mode (index.css) */
/* .dark { --accent: #1DB8D4 } — dark mode wird von index.css gehandelt */
--bg-deep: #131519
--bg-primary: #1a1d23
--bg-surface: #1f2228
--bg-elevated: #282c35
--text-primary: #e0e4ec
--text-secondary: #848b9e
--text-muted: #4a5168
--border: #2a2e38
--success: #2ed573
--error: #f43f5e
--warning: #f59e0b
```

### Kanonische Komponenten (geschützt — nur verwenden, nicht verändern)

- **SettingsSection** — Karte mit 32px Icon-Box (accent-bg), Titel, Beschreibung, optionaler Advanced-Bereich
- **FormGroup** — Label+Hint links (max-width 320px) + Control rechts (min-width 260px), responsive
- **Input-Standard** — `bg-elevated`, `border`, `6px radius`, `7px/12px padding`, `13px font`, `220px width`, focus → accent border
- **Toggle** — 40×22px, accent wenn aktiv
- **Button primary** — accent background, schwarz text, font-weight 600
- **Button ghost** — transparent, border, hover → border-hover

---

## Phase 0 — Bereits erledigt (nicht anfassen)

| Bereich | Dateien | Status |
|---------|---------|--------|
| CSS Design-Tokens | `frontend/src/index.css` | ✅ Geschützt |
| Basis-Komponenten | `SettingsSection`, `FormGroup`, `SettingsDetailLayout`, `SettingsCard` | ✅ Geschützt |
| SeriesDetailPage | `SeriesDetail.tsx` + alle Series-Komponenten | ✅ Geschützt |
| ConnectionsSettings (Basis) | `ConnectionsSettings.tsx` | ✅ Geschützt (Basis) |

---

## Phase 1 — Config-Key-Bugs fixen

**Reihenfolge zwingend:** Funktion vor Design. Erst wenn Keys stimmen, wird Design in Phase 2 angeglichen.

### Schritt 1 — GeneralSettings: 3 falsche Keys

**Datei:** `frontend/src/pages/Settings/GeneralSettings.tsx`

| Frontend (falsch) | Backend (korrekt) | Aktion |
|-------------------|-------------------|--------|
| `workers` | `translation_max_workers` + `scan_metadata_max_workers` | Aufteilen in zwei separate Number-Inputs |
| `log_to_file` (Boolean) | `log_file` (Pfad-String, z.B. `/config/sublarr.log`) | Key + Control-Typ ändern |
| `translation_enabled` | *(existiert nicht)* | Entfernen |

**Commit:** `fix: correct config keys in GeneralSettings`

### Schritt 2 — AutomationSettings: 8 falsche Keys (Komplett-Rewrite)

**Datei:** `frontend/src/pages/Settings/AutomationSettings.tsx`

Aktuell werden **alle Werte verworfen** — kein einziger Key landet im Backend.

| Frontend (falsch) | Backend (korrekt) |
|-------------------|-------------------|
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

**Vorgehen:** Datei komplett neu schreiben mit korrekten Keys und SettingsSection/FormGroup-Pattern.

**Commit:** `fix: rewrite AutomationSettings with correct backend config keys`

---

## Phase 2 — Settings: Design + fehlende Felder

Jede Seite = ein Commit. Reihenfolge einhalten.

### Schritt 3 — GeneralSettings: Design + fehlende Felder

**Datei:** `frontend/src/pages/Settings/GeneralSettings.tsx`

Fehlende Felder ergänzen (alle in `config.py` bestätigt):
- `log_format` — Select: `text` | `json`
- `scan_metadata_engine` — Select: `ffprobe` | `mediainfo` | `auto`
- `translation_max_workers` — Number Input (bereits in Schritt 1 angelegt)
- `scan_metadata_max_workers` — Number Input (bereits in Schritt 1 angelegt)

Design: bereits nah am Ziel, minimale Anpassungen auf SettingsSection-Standard.

**Commit:** `feat: complete GeneralSettings — design + missing fields`

### Schritt 4 — AutomationSettings: Design + fehlende Felder

**Datei:** `frontend/src/pages/Settings/AutomationSettings.tsx`

Nach Phase-1-Fix jetzt vollständig machen. Fehlende Felder (alle in `config.py` bestätigt):

**Wanted-Suche:**
- `wanted_search_max_items_per_run` — Number
- `wanted_max_search_attempts` — Number
- `wanted_adaptive_backoff_enabled` — Toggle
- `wanted_backoff_base_hours` — Number (nur sichtbar wenn Backoff aktiv)
- `wanted_backoff_cap_hours` — Number (nur sichtbar wenn Backoff aktiv)
- `wanted_auto_extract` — Toggle
- `wanted_anime_only` — Toggle
- `wanted_anime_movies_only` — Toggle

**Upgrade:**
- `upgrade_window_days` — Number
- `upgrade_prefer_ass` — Toggle (SRT→ASS immer upgraden)

**Webhook:**
- `webhook_delay_minutes` — Number
- `webhook_auto_scan` — Toggle
- `webhook_auto_translate` — Toggle

**Auto-Processing:**
- `auto_process_common_fixes` — Toggle
- `auto_process_hi_removal` — Toggle
- `auto_process_credit_removal` — Toggle
- `auto_process_sync_threshold` — Number
- `auto_nfo_export` — Toggle
- `auto_cleanup_keep_languages` — Text-Input (kommagetrennte Sprach-Codes)
- `auto_cleanup_keep_formats` — Text-Input (kommagetrennte Formate)
- `subtitle_trash_retention_days` — Number

Design: SettingsSection-Standard, Gruppierung nach Funktion (Wanted / Upgrade / Webhook / Post-Processing).

**Commit:** `feat: complete AutomationSettings — design + all missing fields`

### Schritt 5 — SubtitlesSettings: Design + fehlende Felder

**Datei:** `frontend/src/pages/Settings/SubtitlesSettings.tsx`

Fehlende Felder (alle in `config.py` bestätigt):
- `hi_removal_enabled` — Toggle (globales HI-Removal)
- `credit_threshold_sec` — Number (Sekunden vom Ende)
- `op_window_sec` — Number (OP/ED-Erkennungsfenster)
- `use_embedded_subs` — Toggle
- `wanted_skip_srt_on_no_ass` — Toggle

**Commit:** `feat: complete SubtitlesSettings — design + missing fields`

### Schritt 6 — ProvidersSettings: Design + fehlende Felder

**Datei:** `frontend/src/pages/Settings/ProvidersSettings.tsx`

Fehlende Felder (alle in `config.py` bestätigt):
- `dedup_on_download` — Toggle
- `provider_reranking_enabled` — Toggle
- `provider_reranking_min_downloads` — Number (nur sichtbar wenn Reranking aktiv)
- `provider_reranking_max_modifier` — Number
- `provider_auto_prioritize` — Toggle
- `provider_rate_limit_enabled` — Toggle
- `provider_search_timeout` — Number (Sekunden, globaler Fallback)
- `provider_cache_ttl_minutes` — Number
- `provider_auto_disable_cooldown_minutes` — Number
- `github_token` — Password-Input (für Plugin Marketplace Rate-Limits)

**Advanced-Sektion (ausgeklappt):**
- `provider_dynamic_timeout_enabled` — Toggle
- `provider_dynamic_timeout_min_samples` — Number
- `provider_dynamic_timeout_multiplier` — Number
- `provider_dynamic_timeout_buffer_secs` — Number
- `provider_dynamic_timeout_min_secs` — Number
- `provider_dynamic_timeout_max_secs` — Number
- `circuit_breaker_failure_threshold` — Number
- `circuit_breaker_cooldown_seconds` — Number

**Commit:** `feat: complete ProvidersSettings — design + missing fields`

### Schritt 7 — TranslationSettings: Design + fehlende Felder

**Datei:** `frontend/src/pages/Settings/TranslationSettings.tsx`

Fehlende Felder (alle in `config.py` bestätigt — Keys ohne `translation_`-Präfix):
- `temperature` — Number (0.0–1.0, Slider oder Number-Input)
- `batch_size` — Number
- `request_timeout` — Number (Sekunden)
- `backoff_base` — Number (Backoff-Zeit zwischen Retries)
- `glossary_max_terms` — Number

**Commit:** `feat: complete TranslationSettings — design + missing fields`

### Schritt 8 — NotificationsSettings: Design + fehlende Felder

**Datei:** `frontend/src/pages/Settings/NotificationsSettings.tsx`

Fehlende Felder:
- `notify_manual_actions` — Toggle (normales Config-Feld, `PATCH /api/v1/config`)

**Quiet Hours — eigene API, nicht über Config-Endpoint:**

Die Quiet Hours werden in einer separaten DB-Tabelle gespeichert mit eigenen Endpoints:
- Laden: `GET /api/v1/notifications/quiet-hours`
- Anlegen: `POST /api/v1/notifications/quiet-hours`
- Bearbeiten: `PUT /api/v1/notifications/quiet-hours/<id>`
- Löschen: `DELETE /api/v1/notifications/quiet-hours/<id>`

UI-Controls:
- Toggle "Quiet Hours aktivieren" → POST bei Aktivierung, DELETE bei Deaktivierung
- Time-Input "Von" (HH:MM) + Time-Input "Bis" (HH:MM) → PUT bei Änderung

**Commit:** `feat: complete NotificationsSettings — design + missing fields`

### Schritt 9 — ConnectionsSettings: Multi-Instanz + API-Keys

**Datei:** `frontend/src/pages/Settings/ConnectionsSettings.tsx`

**Wichtig:** Bestehendes Design und bestehende Keys nicht verändern — nur erweitern.

#### Multi-Instanz UI (User-approved Design)

Ersetzt Einzel-Felder für Sonarr/Radarr durch Instanz-Listen:

**Instanz-Karte:**
- Status-Dot (grün/rot/grau) — Verbindungsstatus
- Name-Feld — editierbarer Input, sieht wie Text aus, bei Hover → Rahmen + ✎
- Status-Badges — "Standard" (erste Instanz), "Verbunden"/"Fehler"
- "Entfernen"-Button — ghost style, hover → rot
- URL-Feld — Standard-Input
- API-Key-Feld — Password-Input + "Testen"-Button

**"+ Instanz hinzufügen"** — gestrichelter Rahmen-Button, hover → Teal

**Backend-Keys:**
- `sonarr_instances_json` — JSON-Array (serialisiert vor Speichern)
- `radarr_instances_json` — JSON-Array

**Neue Einzel-Felder (FormGroup, alle in `config.py` bestätigt):**
- `tmdb_api_key` — Password-Input
- `tvdb_api_key` — Password-Input
- `tvdb_pin` — Password-Input
- `metadata_cache_ttl_days` — Number
- `ffmpeg_timeout` — Number (Sekunden, Advanced-Sektion)

**Commit:** `feat: add multi-instance UI and API key fields to ConnectionsSettings`

### Schritt 10 — SystemSettings: Backup + AniDB + Remux + Standalone

**Datei:** `frontend/src/pages/Settings/SystemSettings.tsx`

Fehlende Felder (alle in `config.py` bestätigt):

**Backup:**
- `backup_dir` — Pfad-Input
- `backup_retention_daily` — Number (Täglich aufbewahren: Anzahl Backups)
- `backup_retention_weekly` — Number
- `backup_retention_monthly` — Number

**AniDB (für Anime-User):**
- `anidb_enabled` — Toggle
- `anidb_cache_ttl_days` — Number
- `anidb_custom_field_name` — Text-Input
- `anidb_fallback_to_mapping` — Toggle

**Remux:**
- `remux_trash_dir` — Pfad-Input
- `remux_backup_retention_days` — Number
- `remux_use_reflink` — Toggle
- `remux_arr_pause_enabled` — Toggle

**Standalone:**
- `standalone_scan_interval_hours` — Number
- `standalone_debounce_seconds` — Number
- `standalone_skip_extras` — Toggle

**Commit:** `feat: complete SystemSettings — backup, AniDB, remux, standalone fields`

---

## Phase 3 — Neue Seiten & Features

**Regel:** Nur neue Dateien erstellen oder bestehende Dateien erweitern, ohne deren bestehende Funktionalität zu verändern.

### Schritt 11 — Re-scan Series

**Dateien:**
- `frontend/src/components/series/SeriesHero.tsx` — Button verdrahten (existiert bereits)
- `backend/routes/library.py` — neue Route `POST /api/v1/series/<id>/scan`

**Verhalten:**
- Klick → Loading-Spinner im Button
- Erfolg → Toast "Scan gestartet"
- Fehler → Toast mit Fehlermeldung

**Commit:** `feat: wire re-scan series button to new backend route`

### Schritt 12 — Glossar-Verwaltung

**Datei:** `frontend/src/components/translation/GlossaryPanel.tsx`

Aktuell: Nur Anzeige. Ergänzen:
- "Eintrag hinzufügen" — Modal mit Term (DE) + Translation (EN) → `POST /api/v1/glossary`
- Bearbeiten-Button → gleicher Modal → `PUT /api/v1/glossary/<id>`
- Löschen-Button → Bestätigungs-Dialog → `DELETE /api/v1/glossary/<id>`
- Export-Button → `GET /api/v1/glossary/export`

**Commit:** `feat: add CRUD and export to GlossaryPanel`

### Schritt 13 — Sprachprofil-Verwaltungsseite

**Neue Datei:** `frontend/src/pages/LanguageProfiles.tsx`

CRUD-Seite für Language Profiles:
- Liste aller Profile (Karten-Layout)
- "Neues Profil" Button → Modal → `POST /api/v1/language-profiles`
- Bearbeiten → gleicher Modal → `PUT /api/v1/language-profiles/<id>`
- Löschen → Bestätigungs-Dialog → `DELETE /api/v1/language-profiles/<id>`
- Felder: Name, Sprachen (Multi-Select), Cutoff-Score, Upgrade-Score

**Route:** neue Route in `frontend/src/App.tsx` → `/settings/language-profiles`

**Commit:** `feat: add Language Profiles management page`

### Schritt 14 — Backup-Management UI

**Datei:** `frontend/src/pages/Settings/SystemSettings.tsx` — neue Sektion

- Backup auslösen → `POST /api/v1/backup/full`
- Backup-Liste → `GET /api/v1/backup/full/list`
- Download pro Backup → `GET /api/v1/backup/full/download/<filename>`
- Restore pro Backup → `POST /api/v1/backup/full/restore` + Bestätigungs-Dialog

**Commit:** `feat: add Backup Management UI to SystemSettings`

### Schritt 15 — MovieDetailPage

**Neue Datei:** `frontend/src/pages/MovieDetail.tsx`

Analog zu SeriesDetailPage, angepasst für Filme:
- Hero mit Poster, Metadaten, Action-Buttons (Suchen, Übersetzen, Re-scan)
- Keine Season-Tabs (Filme haben keine Staffeln)
- Subtitle-Liste statt Episode-Grid
- Settings-Panel analog zu SeriesSettingsPanel

**Route:** neue Route → `/movies/<id>`

**Commit:** `feat: add MovieDetailPage analogous to SeriesDetailPage`

---

## Qualitätssicherung nach jeder Einheit

Nach jeder abgeschlossenen und vom User bestätigten Einheit:
1. Eintrag in `docs/PROTECTED.md` ergänzen
2. `cd frontend && npm run lint && npx tsc --noEmit`
3. Backend (wenn verändert): `cd backend && ruff check . && ruff format --check .`

---

## Nicht in diesem Plan (eigene Planung erforderlich)

- Hook-Manager UI
- Benachrichtigungsverlauf
- Whisper-Transkriptions-UI
- Remux-UI (Trigger, nicht Einstellungen)
- Bazarr-Import-Wizard
- Translation-Memory UI
- Subtitle-Editor-Erweiterungen (Split/Merge, Timing-Normalisierung)
- Infrastructure-Settings (Database/Redis) — sinnvoller via ENV-Variable
- Konzeptionell fehlende Felder (B1–B10 in SETTINGS_GAP_ANALYSIS) — separate Backlog-Items

---

*Spec-Status: Zur User-Freigabe bereit*
*Referenz-Mockups: `mockups/concept-final.html`, `mockups/concept-drilldown.html`*
*Gap-Analysen: `docs/UI_GAP_ANALYSIS.md`, `docs/SETTINGS_GAP_ANALYSIS.md`*
