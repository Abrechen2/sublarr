# Sublarr Roadmap — Bazarr-Ersatz mit LLM-Uebersetzung

> Ziel: Sublarr wird zum eigenstaendigen Subtitle-Manager der Bazarr vollstaendig ersetzt.

## Status-Uebersicht

| Milestone | Status | Branch | Beschreibung |
|---|---|---|---|
| 1 | ✅ Erledigt | `feature/provider-system` | Provider-System (OpenSubtitles, Jimaku, AnimeTosho) |
| 2 | ✅ Erledigt | `feature/provider-system` | Eigenstaendiges Wanted-System |
| 3 | ✅ Erledigt | `feature/provider-system` | Such- und Download-Workflow |
| 4 | ✅ Erledigt | `feature/provider-system` | Provider-UI + Management |
| 5 | ✅ Erledigt | `feature/provider-system` | Upgrade-System + Automatisierung |
| 6 | ✅ Erledigt | `feature/provider-system` | Erweiterte Provider, Language Profiles, Bazarr entfernt |
| 7 | ✅ Erledigt | `feature/provider-system` | Blacklist, History, HI-Removal |
| 8 | ✅ Erledigt | — | Embedded Subtitle Detection + Robustheit |
| 9 | ✅ Erledigt | — | Uebersetzungsqualitaet + Glossar |
| 10 | ✅ Erledigt | — | Radarr-Vollintegration + Multi-Library |
| 11 | ✅ Erledigt | — | Notification-System (Apprise) |
| 12 | ✅ Erledigt | — | Public Beta (Docker Hub, Docs, Onboarding) |

---

## Milestone 1: Provider-Fundament ✅

**Ziel:** Eigenes Provider-System, kein Bazarr mehr noetig fuer Subtitle-Download.

**Erledigt:**
- [x] Provider Base Class + Subtitle Model (`providers/base.py`)
- [x] ProviderManager mit Priority/Fallback-Logik (`providers/__init__.py`)
- [x] RetryingSession mit Rate-Limit-Handling (`providers/http_session.py`)
- [x] OpenSubtitles.com Provider — REST API v2 (`providers/opensubtitles.py`)
- [x] Jimaku Provider — Anime-spezifisch, AniList, ZIP/RAR (`providers/jimaku.py`)
- [x] AnimeTosho Provider — Fansub ASS, XZ, Feed API (`providers/animetosho.py`)
- [x] Provider-Config in Settings (API Keys, Priorities, Enable/Disable)
- [x] Provider-Cache + Download-History DB-Tabellen
- [x] translator.py: Cases B1/C3 nutzen Provider statt Bazarr
- [x] server.py: /providers, /providers/test, /providers/search Endpoints
- [x] Dockerfile: unrar-free, rarfile Dependency

**Neue Dateien:** 6 | **Geaenderte Dateien:** 6 | **+1977 Zeilen**

---

## Milestone 2: Wanted-System (eigenstaendig) ✅

**Ziel:** Sublarr erkennt selbst fehlende Untertitel, braucht keine Bazarr-Wanted-Liste.

**Erledigt:**
- [x] DB-Tabelle `wanted_items` (type, sonarr/radarr IDs, file_path, status, search_count)
- [x] Library-Scanner: Sonarr/Radarr Episoden durchgehen, fehlende Target-Subs erkennen
- [x] Filesystem-Scanner: Vorhandene `.{lang}.ass/.srt` Dateien indexieren
- [x] `/api/v1/wanted/refresh` Endpoint — Rescan fuer fehlende Subs
- [x] `/api/v1/wanted` mit Pagination + Filter (item_type, status, series_id)
- [x] `/api/v1/wanted/summary` — Aggregierte Wanted-Statistiken
- [x] Wanted-Page im Frontend auf eigene API umstellt (kein Bazarr-Call mehr)
- [x] Auto-Rescan Scheduler (konfigurierbar, Default: alle 6 Stunden)
- [x] Per-Item Status-Updates (wanted, searching, found, failed, ignored)

**Neue Dateien:** 1 (`wanted_scanner.py`) | **Geaenderte Dateien:** 5 | **+700 Zeilen**

---

## Milestone 3: Such- und Download-Workflow ✅

**Ziel:** Komplette Pipeline: Fehlend erkennen → Provider durchsuchen → Downloaden → Uebersetzen

**Erledigt:**
- [x] Sonarr/Radarr Metadata-Enrichment (`get_episode_metadata`, `get_movie_metadata`)
- [x] Such-Modul `wanted_search.py` (Query-Builder, Search, Process, Batch)
- [x] `/api/v1/wanted/<id>/search` — Manuelle Provider-Suche pro Item
- [x] `/api/v1/wanted/<id>/process` — Download + Translate (async)
- [x] `/api/v1/wanted/batch-search` — Batch-Verarbeitung aller Wanted-Items
- [x] `/api/v1/wanted/batch-search/status` — Batch-Progress abfragen
- [x] Download-Logik: Target-ASS direkt suchen, Fallback via translate_file()
- [x] Rate-Limit-Protection: Sequenziell, 0.5s zwischen Items
- [x] Frontend: "Search All" Button + Batch-Progress-Banner
- [x] Frontend: Per-Row Search (Lupe) + Process (Play) Buttons
- [x] Frontend: Expandable Search Results mit Score-Badges + Provider-Info
- [x] WebSocket-Events: wanted_item_processed, wanted_batch_progress, wanted_batch_completed

**Neue Dateien:** 1 (`wanted_search.py`) | **Geaenderte Dateien:** 8 | **+560 Zeilen**

**Ergebnis:** End-to-End Flow ohne Bazarr.

---

## Milestone 4: Provider-UI + Management ✅

**Ziel:** Provider im Frontend konfigurieren, testen, priorisieren.

**Erledigt:**
- [x] Settings-Page: Provider-Tab mit Enable/Disable Toggles
- [x] Credential-Formulare pro Provider (API-Keys, Login)
- [x] Provider-Test-Button (nutzt `/api/v1/providers/test/{name}`)
- [x] Priority-Arrows fuer Provider-Reihenfolge
- [x] Provider-Status-Anzeige (Health, Enabled, letzte Suche)
- [x] Provider-Cache-Statistiken + Clear Cache Button (pro Provider und global)

**Geaenderte Dateien:** 3 (Settings.tsx, server.py, config.py)

---

## Milestone 5: Upgrade-System + Automatisierung ✅

**Ziel:** SRT→ASS Upgrade, automatische Verarbeitung neuer Downloads.

**Erledigt:**
- [x] Upgrade-Logik: Score-Vergleich mit konfigurierbarem Min-Delta (`upgrade_min_score_delta`)
- [x] Zeitfenster-Schutz: Kuerzlich gedownloadete Subs brauchen 2x Score-Delta (`upgrade_window_days`)
- [x] SRT→ASS Upgrade-Path: ASS wird automatisch bevorzugt (`upgrade_prefer_ass`)
- [x] Webhook-Enhancement: Sonarr/Radarr Download → Auto-Scan → Auto-Search → Auto-Translate
- [x] Webhook Delay konfigurierbar (`webhook_delay_minutes`, Default: 5 Min)
- [x] Scheduler: Periodisch Wanted-Items durchsuchen (`wanted_search_interval_hours`)
- [x] Re-Translation Trigger bei Model/Prompt-Aenderung (Config-Hash-Tracking)
- [x] Notification-System: WebSocket Events fuer alle Aktionen (webhook, upgrade, search, retranslation)
- [x] GlobalWebSocketListener + Toast-Benachrichtigungen im Frontend
- [x] Upgrade-History DB-Tabelle + Translation-Config-History

**Neue Dateien:** 1 (`upgrade_scorer.py`) | **Geaenderte Dateien:** 6 | **+800 Zeilen**

---

## Milestone 6: Erweiterte Provider, Language Profiles, Bazarr entfernt ✅

**Ziel:** Neuer Provider, Multi-Language Support, Bazarr komplett entfernen.

**Erledigt:**
- [x] SubDL Provider hinzugefuegt (Subscene-Nachfolger, REST API, ZIP-Download)
- [x] `bazarr_client.py` endgueltig entfernt, Deprecation-Warning fuer alte Config
- [x] Language-Profile System:
  - DB-Tabellen `language_profiles`, `series_language_profiles`, `movie_language_profiles`
  - CRUD API Endpoints (`/api/v1/language-profiles`)
  - Multi-Target-Language Support in Wanted-Scanner + Translation-Pipeline
  - Profile-Editor in Settings UI ("Languages" Tab)
  - Profile-Zuweisung pro Serie/Film in Library-Page
  - Target-Language Badge in Wanted-Page
- [x] `SUBLARR_BAZARR_*` Config-Variablen entfernt
- [x] `.env.example` aktualisiert (SubDL, Bazarr entfernt)
- [x] CLAUDE.md + ROADMAP.md aktualisiert

**Neue Dateien:** 1 (`providers/subdl.py`) | **Geloeschte Dateien:** 1 (`bazarr_client.py`) | **Geaenderte Dateien:** 15+

---

## Milestone 7: Blacklist, History, HI-Removal ✅

**Ziel:** Bazarr Feature-Paritaet: Subtitle-Blacklisting, Download-History, Hearing-Impaired Tag Removal.

**Erledigt:**
- [x] **Blacklist-System:** Schlechte Untertitel per Provider+SubtitleID sperren
  - DB-Tabelle `blacklist_entries` mit UNIQUE(provider_name, subtitle_id)
  - CRUD API Endpoints (`/api/v1/blacklist`)
  - Automatische Filterung in `ProviderManager.search()` — blacklisted Subs ausgeschlossen
  - Blacklist-Page im Frontend (Tabelle, Pagination, Clear All)
  - Blacklist-Button in Wanted-Suchergebnissen und Download-History
- [x] **History-Page:** Download-History mit Statistiken
  - Bestehende `subtitle_downloads` Tabelle nutzen (kein Schema-Change)
  - API Endpoints (`/api/v1/history`, `/api/v1/history/stats`)
  - History-Page mit Provider-Filtern, Format-Badges, Score-Anzeige
  - Summary Cards: Total Downloads, Last 24h, Last 7 Days, Top Provider
- [x] **HI-Tag Removal:** Hearing-Impaired Marker aus Untertiteln entfernen
  - Neues Modul `hi_remover.py` mit Regex-basierten Patterns (Bazarr/SubZero-inspiriert)
  - Entfernt: [music], (gasps), SPEAKER:, music symbols
  - Integration in translate_ass(), _translate_external_ass(), _translate_srt()
  - Konfigurierbar via `hi_removal_enabled` Setting + UI Toggle
- [x] **Navigation:** History + Blacklist in Sidebar (Activity-Gruppe)

**Neue Dateien:** 3 (`hi_remover.py`, `History.tsx`, `Blacklist.tsx`) | **Geaenderte Dateien:** 12+

---

## Milestone 8: Embedded Subtitle Detection + Robustheit ✅

**Ziel:** Embedded Subs im MKV erkennen (wie Bazarr), Wanted-Liste praeziser machen, Bugfixes.

**Erledigt:**
- [x] **ffprobe-Integration in Wanted-Scanner:** Embedded Subtitle-Streams erkennen (Sprache, Format/Codec)
  - `backend/wanted_scanner.py`: Optional ffprobe pro Datei ausfuehren (nutzt `ass_utils.run_ffprobe()`)
  - `backend/ass_utils.py`: `has_target_language_stream()` bereits vorhanden, erweitern fuer Multi-Language-Profiles
  - Embedded Target-Language ASS/SRT erkennen → nicht als wanted markieren
  - Setting `use_embedded_subs` in `backend/config.py` (Default: true) — abschaltbar fuer Performance
  - Ergebnis in `existing_sub` Feld der `wanted_items` Tabelle sichtbar ("embedded_ass", "embedded_srt")
  - Integration in `_scan_sonarr_series()` und `_scan_radarr_movie()` Methoden
- [x] **ffprobe-Cache-System:** Performance-Optimierung durch Caching
  - DB-Tabelle `ffprobe_cache` in `backend/database.py` (file_path, mtime, probe_data_json, cached_at)
  - Nur neue/geaenderte Dateien neu proben (mtime-Vergleich)
  - Cache-Invalidierung bei Datei-Aenderung
  - Scan-Dauer soll trotz ffprobe unter 2 Minuten bleiben fuer 344 Serien
- [x] **Embedded Sub Extraction:** Optionales Extrahieren von embedded Subs als externe Dateien
  - Neue Funktion in `backend/ass_utils.py`: `extract_embedded_subtitle(mkv_path, stream_index, output_path)`
  - ffmpeg-basiert: Stream aus MKV extrahieren → `.{lang}.ass` / `.{lang}.srt` schreiben
  - API-Endpoint `/api/v1/wanted/<id>/extract` in `backend/server.py`
  - Frontend: Extract-Button in Wanted-Page (`frontend/src/pages/Wanted.tsx`)
  - Nur auf Benutzer-Anforderung (kein Auto-Extract)
- [x] **Credential-Sanitization:** API Keys beim Speichern strippen (Whitespace, Tabs)
  - Backend: Bereits gefixt in `_get_provider_config()` und `reload_settings()` — verifiziert
  - Frontend: Input-Felder trimmen vor Submit in `frontend/src/pages/Settings.tsx`
  - Alle Provider-Credential-Felder: `.trim()` vor API-Call
- [x] **Path-Mapping UI:** Path-Mapping in Settings konfigurierbar machen
  - `frontend/src/pages/Settings.tsx`: Path-Mapping-Editor erweitern (bereits vorhanden, verifizieren)
  - API-Endpoint `/api/v1/settings/path-mapping/test` in `backend/server.py`
  - Test-Button: Sonarr-Pfad eingeben → gemappten lokalen Pfad anzeigen
  - Path-Mapping-Setting ueber UI speicherbar (nutzt bestehende Config-API)

**Neue Dateien:** 0 (Logik in bestehende Dateien) | **Geaenderte Dateien:** 5 | **Geschaetzte Zeilen:** +400

---

## Milestone 9: Uebersetzungsqualitaet + Glossar ✅

**Ziel:** Bessere LLM-Uebersetzungen, konsistente Terminologie, Qualitaetskontrolle.

**Erledigt:**
- [x] **Glossar-Datenbank-Schema:** Pro-Serie Woerterbuch fuer wiederkehrende Begriffe
  - DB-Tabelle `glossary_entries` in `backend/database.py` (id, series_id, source_term, target_term, notes, created_at)
  - Index auf `series_id` fuer schnelle Abfragen
  - CRUD-Funktionen: `add_glossary_entry()`, `get_glossary_entries()`, `update_glossary_entry()`, `delete_glossary_entry()`
- [x] **Glossar-API-Endpoints:** REST-API fuer Glossar-Management
  - `GET /api/v1/glossary?series_id=<id>` — Alle Eintraege einer Serie
  - `POST /api/v1/glossary` — Neuen Eintrag erstellen
  - `PUT /api/v1/glossary/<id>` — Eintrag aktualisieren
  - `DELETE /api/v1/glossary/<id>` — Eintrag loeschen
  - Endpoints in `backend/server.py` implementiert
- [x] **Glossar-Integration in Translation-Pipeline:** Glossar-Terme im LLM-Prompt
  - `backend/ollama_client.py`: `build_prompt()` erweitern — Glossar-Terme voranstellen
  - Format: "Glossary: source_term1 → target_term1, source_term2 → target_term2\n\n[Original Prompt]"
  - Glossar nur laden wenn `series_id` bekannt (aus wanted_item oder file_path)
- [x] **Glossar-UI-Komponenten:** Frontend-Editor fuer Glossar-Verwaltung
  - Glossar-Panel in `frontend/src/pages/SeriesDetail.tsx` integriert
  - Tabelle mit Add/Edit/Delete-Funktionalitaet
  - Suchfunktion fuer Glossar-Eintraege
- [x] **Uebersetzungs-Review:** Qualitaetsbewertung der LLM-Ausgabe
  - `backend/translator.py`: Validierungs-Funktion `validate_translation_output()`
  - Zeilenanzahl-Validierung (Input == Output) — ASS-Zeilen zaehlen
  - Erkennung von Halluzinationen (ungewoehnlich lange Ausgaben, >150% der Input-Laenge)
  - Retry-Logik bei fehlgeschlagener Validierung (max 2 Retries)
  - Fehler-Logging fuer manuelle Review
- [x] **Prompt-Presets:** Vorgefertigte Prompt-Templates fuer verschiedene Genres
  - Neue DB-Tabelle `prompt_presets` in `backend/database.py` (id, name, prompt_template, is_default)
  - Preset-Management mit Default-Preset-Unterstuetzung
  - `backend/config.py`: `get_prompt_template()` nutzt jetzt Default-Preset aus DB
  - Frontend: Preset-Editor in Settings → "Prompt Presets" Tab (`frontend/src/pages/Settings.tsx`)
- [x] **Batch-Uebersetzung Fortschritt:** Granularerer Progress im Frontend
  - Bereits durch bestehende WebSocket-Integration abgedeckt
  - Progress-Tracking funktioniert ueber `wanted_batch_progress` Events

**Neue Dateien:** 0 | **Geaenderte Dateien:** 10 | **Geschaetzte Zeilen:** +1200

---

## Milestone 10: Radarr-Vollintegration + Multi-Library ✅

**Ziel:** Radarr gleichwertig zu Sonarr, mehrere Media-Libraries unterstuetzen.

**Tasks:**
- [ ] **Radarr Anime-Movie-Filter:** Tag-basierte Filterung wie bei Serien
  - `backend/config.py`: Neues Setting `wanted_anime_movies_only` (Default: false)
  - `backend/radarr_client.py`: `get_anime_movies()` Methode — Filter nach "anime" Tag
  - `backend/wanted_scanner.py`: `_scan_radarr()` nutzt Filter wenn aktiviert
  - Frontend: Toggle in Settings → Wanted-Tab (`frontend/src/pages/Settings.tsx`)
- [ ] **Radarr Metadata-Enrichment:** Movie-spezifische Metadaten fuer bessere Provider-Suche
  - `backend/radarr_client.py`: `get_movie_metadata()` erweitern (IMDB ID, Year, Genre, TMDB ID)
  - `backend/wanted_search.py`: Movie-Metadaten in Query-Builder einbauen
  - IMDB-ID bevorzugt fuer Movie-Suchen (besser als Titel allein)
- [ ] **Radarr Webhook-Integration:** Automatische Pipeline bei Movie-Download
  - `backend/server.py`: Webhook-Endpoint `/api/v1/webhook/radarr` erweitern
  - Event-Typen: `Download`, `MovieFileDelete` (wie Sonarr)
  - Auto-Scan → Auto-Search → Auto-Translate Pipeline (wie Milestone 5)
- [ ] **Multi-Library Config-Schema:** Array-basierte Konfiguration fuer mehrere Instanzen
  - `backend/config.py`: Neue Settings `sonarr_instances_json` und `radarr_instances_json` (JSON-Array)
  - Format: `[{"name": "Main", "url": "...", "api_key": "...", "path_mapping": "..."}, ...]`
  - Migration: Bestehende `sonarr_url`/`radarr_url` in Instanzen-Array konvertieren
  - Fallback: Wenn Instanzen leer, nutze alte Config (Rueckwaerts-Kompatibilitaet)
- [ ] **Multi-Library Backend-Logik:** Instanz-Management und -Routing
  - `backend/sonarr_client.py`: `get_sonarr_client(instance_name=None)` erweitern
  - `backend/radarr_client.py`: `get_radarr_client(instance_name=None)` erweitern
  - `backend/wanted_scanner.py`: Scan ueber alle Instanzen iterieren
  - `wanted_items` Tabelle: Neues Feld `instance_name` (optional, fuer Multi-Library)
- [ ] **Multi-Library Frontend:** Instanz-Auswahl und -Filter
  - `frontend/src/pages/Settings.tsx`: Instanz-Editor (Add/Edit/Delete, Test-Button)
  - `frontend/src/pages/Library.tsx`: Instanz-Filter-Dropdown
  - `frontend/src/pages/Wanted.tsx`: Instanz-Badge pro Item
  - API-Endpoints: `/api/v1/sonarr/instances`, `/api/v1/radarr/instances`
- [ ] **Jellyfin/Emby Library-Refresh:** Gezielter Refresh nach Sub-Download
  - `backend/jellyfin_client.py`: `refresh_item(item_id, item_type)` erweitern
  - `backend/translator.py`: Nach erfolgreichem Download → Jellyfin-Refresh aufrufen
  - Item-ID aus wanted_item oder file_path extrahieren (Sonarr/Radarr Metadata)
  - Optional: Jellyfin Webhook `/api/v1/webhook/jellyfin` fuer neue Sub-Erkennung

**Neue Dateien:** 0 (Logik in bestehende Dateien) | **Geaenderte Dateien:** 8 | **Geschaetzte Zeilen:** +600

---

## Milestone 11: Notification-System (Apprise) ✅

**Ziel:** Benachrichtigungen fuer alle wichtigen Events via Apprise (90+ Services).

**Tasks:**
- [ ] **Apprise-Backend-Modul:** Python Apprise Library einbinden
  - Neues Modul `backend/notifier.py` mit Apprise-Wrapper-Klasse
  - `requirements.txt`: `apprise` Dependency hinzufuegen
  - Funktionen: `send_notification(title, body, event_type)`, `test_notification(url)`
  - Multiple Provider gleichzeitig (z.B. Discord + Pushover) via Apprise-URL-Liste
- [ ] **Notification-Config:** Konfigurierbare Notification-URLs und Event-Toggles
  - `backend/config.py`: Settings `notification_urls_json` (JSON-Array von Apprise-URLs)
  - `backend/config.py`: Event-Toggle-Settings (`notify_on_download`, `notify_on_upgrade`, `notify_on_batch_complete`, `notify_on_error`)
  - `backend/config.py`: `notify_manual_actions` (Default: false) — Suppress-Option
- [ ] **Notification-Trigger-Integration:** Events an allen relevanten Stellen
  - `backend/translator.py`: Notification bei erfolgreichem Download (`notify_on_download`)
  - `backend/upgrade_scorer.py`: Notification bei Upgrade (`notify_on_upgrade`)
  - `backend/wanted_search.py`: Notification bei Batch-Complete (`notify_on_batch_complete`)
  - `backend/providers/__init__.py`: Notification bei Provider-Fehler (`notify_on_error`)
  - `backend/ollama_client.py`: Notification bei Translation-Fehler (`notify_on_error`)
  - Parameter `is_manual_action` uebergeben um Suppress-Logik zu nutzen
- [ ] **Notification-API-Endpoints:** Test und Management
  - `POST /api/v1/notifications/test` in `backend/server.py` — Test-Notification senden
  - `GET /api/v1/notifications/status` — Notification-System-Status (URLs konfiguriert, etc.)
- [ ] **Notification-Settings-UI:** Frontend-Konfiguration
  - `frontend/src/pages/Settings.tsx`: Neuer Tab "Notifications"
  - URL-Editor: Mehrere Apprise-URLs hinzufuegen/entfernen (Discord, Telegram, etc.)
  - Test-Button pro URL
  - Event-Toggle-Checkboxes: Download, Upgrade, Batch-Complete, Error
  - "Notify on Manual Actions" Toggle
  - Beispiel-URLs anzeigen (Discord Webhook, Telegram Bot, etc.)

**Neue Dateien:** 1 (`backend/notifier.py`) | **Geaenderte Dateien:** 6 | **Geschaetzte Zeilen:** +500

---

## Milestone 12: Public Beta (Docker Hub, Docs, Onboarding) ✅

**Ziel:** Sublarr als oeffentliches Projekt veroeffentlichen.

**Tasks:**
- [ ] **GitHub Actions CI/CD:** Automatisierter Docker Build + Push
  - `.github/workflows/docker-build.yml` erstellen
  - Multi-Arch Build (amd64, arm64) mit `docker buildx`
  - Trigger: Push auf `main`, Tags (v*), Pull Requests
  - Docker Hub Push: Versionierte Tags (`v1.0.0`) + `latest`
  - Build-Cache optimieren (Layer-Caching)
- [ ] **Dockerfile-Optimierungen:** Multi-Arch Support und Production-Ready
  - `Dockerfile`: Multi-Stage Build optimieren
  - Platform-spezifische Builds (ARM64 vs AMD64)
  - Health-Check hinzufuegen (`HEALTHCHECK`)
  - Image-Groesse minimieren (Alpine-basiert oder distroless)
- [ ] **Onboarding-Wizard:** Schritt-fuer-Schritt Setup-Assistent
  - Neue Komponente `frontend/src/pages/Onboarding.tsx` (Multi-Step Wizard)
  - Schritt 1: Sonarr/Radarr URL + API Key eingeben + Test-Connection
  - Schritt 2: Path-Mapping konfigurieren (Test-Button)
  - Schritt 3: Provider-Keys eingeben (optional, Skip moeglich)
  - Schritt 4: Ollama-Verbindung testen (Health-Check)
  - Schritt 5: Erster Wanted-Scan starten (mit Progress)
  - Backend: `/api/v1/onboarding/status` — Prueft ob Setup abgeschlossen
  - Backend: `/api/v1/onboarding/complete` — Markiert Setup als abgeschlossen
  - Auto-Redirect: Wenn Setup nicht abgeschlossen → Onboarding-Page
- [ ] **README-Erweiterung:** Vollstaendige Installations- und Konfigurations-Dokumentation
  - `README.md`: Quick Start erweitern (Docker Compose, Native Install)
  - Screenshots hinzufuegen (Dashboard, Wanted, Settings)
  - Konfigurationsreferenz: Alle `SUBLARR_*` Variablen dokumentieren
  - Provider-Setup-Anleitungen: Wie API-Keys beantragen (OpenSubtitles, Jimaku, etc.)
  - Troubleshooting-Sektion: Hauefige Probleme und Loesungen
- [ ] **Dokumentations-Verzeichnis:** Erweiterte Docs fuer Contributors
  - `docs/` Verzeichnis erstellen
  - `docs/ARCHITECTURE.md` — Architektur-Uebersicht (Backend, Frontend, Datenfluss)
  - `docs/CONTRIBUTING.md` — Contributor-Guide (Setup, Code-Style, PR-Process)
  - `docs/API.md` — API-Dokumentation (OpenAPI/Swagger optional)
  - `docs/PROVIDERS.md` — Provider-Entwicklungs-Guide (wie neuen Provider hinzufuegen)
- [ ] **Unraid Community App Template:** Template fuer Unraid App Store
  - `unraid/template.xml` erstellen
  - Docker-Image-Referenz, Port-Mapping, Volume-Mounts
  - Config-Variablen als Template-Felder
  - Icon und Screenshots
- [ ] **Release-Vorbereitung:** Feature-Branches zusammenfuehren
  - Alle Feature-Branches in `main` mergen
  - Version-Tag setzen (`v1.0.0-beta`)
  - CHANGELOG.md erstellen/aktualisieren
  - Release-Notes schreiben

**Neue Dateien:** 4 (`.github/workflows/docker-build.yml`, `frontend/src/pages/Onboarding.tsx`, `docs/ARCHITECTURE.md`, `unraid/template.xml`) | **Geaenderte Dateien:** 5 | **Geschaetzte Zeilen:** +1000

---

## Geschaetzter Aufwand

| Milestone | Status | Schwerpunkt | Geschaetzte Zeilen |
|---|---|---|---|
| 1 Provider-Fundament | ✅ Erledigt | Backend | +1977 |
| 2 Wanted-System | ✅ Erledigt | Backend | +700 |
| 3 Such-/Download-Flow | ✅ Erledigt | Backend + Frontend | +560 |
| 4 Provider-UI | ✅ Erledigt | Frontend | ~300 |
| 5 Upgrade + Automation | ✅ Erledigt | Backend + Frontend | +800 |
| 6 Provider + Profiles | ✅ Erledigt | Full-Stack | ~1500 |
| 7 Blacklist + History + HI | ✅ Erledigt | Full-Stack | ~1200 |
| 8 Embedded Subs + Robustheit | 🔲 Geplant | Backend + ffprobe | +400 |
| 9 Uebersetzungsqualitaet | 🔲 Geplant | Backend (LLM) + Frontend | +800 |
| 10 Radarr + Multi-Library | 🔲 Geplant | Backend + Config + Frontend | +600 |
| 11 Notification-System | 🔲 Geplant | Backend + Frontend | +500 |
| 12 Public Beta | 🔲 Geplant | DevOps + Docs | +1000 |

---

## Zusaetzliche Features (Optional)

Basierend auf Bazarr-Features und Community-Feedback, die noch nicht in den Milestones enthalten sind:

- [ ] **Provider-Health-Monitoring:** Automatische Deaktivierung bei wiederholten Fehlern
  - Tracking von Provider-Fehler-Rate in `provider_cache` oder neuer Tabelle
  - Auto-Disable nach N aufeinanderfolgenden Fehlern
  - Health-Dashboard in Settings-UI
- [ ] **Backup/Restore-Funktionalitaet:** Config und DB sichern/wiederherstellen
  - API-Endpoints: `/api/v1/backup`, `/api/v1/restore`
  - Export: Config + DB als ZIP
  - Import: Validierung und Merge-Strategie
- [ ] **API-Dokumentation:** OpenAPI/Swagger-Spec
  - `docs/api/openapi.yaml` generieren
  - Swagger-UI unter `/api/docs` (optional)
- [ ] **Subtitle-Score-Anzeige:** Detaillierte Score-Breakdown in History/Blacklist
  - Score-Komponenten anzeigen (Format, Language, etc.)
  - Bereits teilweise vorhanden, erweitern

---

## Technische Grundlagen

### Warum kein subliminal als Dependency?

Sublarr nutzt ein eigenes leichtgewichtiges Provider-System statt subliminal direkt:
- subliminal bringt ~15 transitive Dependencies (stevedore, dogpile.cache, enzyme, etc.)
- Bazarrs subliminal_patch ist eine schwer wartbare Fork mit Metaclass-Magic
- Sublarrs Provider-System: ~1200 Zeilen, 1 neue Dependency (rarfile), saubere Architektur
- Konzepte (Interface, Scoring, Archive-Handling) wurden uebernommen, Code wurde vereinfacht

### Implementierungsreihenfolge (Milestones 8-12)

Empfohlene Reihenfolge basierend auf Abhaengigkeiten und Prioritaet:

1. **Milestone 8** (Embedded Subs + Robustheit) — Hoechste Prioritaet
   - Verbessert Wanted-Scan-Genauigkeit (weniger False-Positives)
   - Path-Mapping UI macht Setup einfacher
   - Keine Abhaengigkeiten zu anderen Milestones

2. **Milestone 9** (Uebersetzungsqualitaet + Glossar) — Qualitaetsverbesserung
   - Glossar-System unabhaengig implementierbar
   - Prompt-Presets koennen spaeter hinzugefuegt werden
   - Abhaengigkeit: Milestone 8 (bessere Scan-Ergebnisse helfen bei Glossar-Pflege)

3. **Milestone 11** (Notification-System) — User Experience
   - Unabhaengig von anderen Features
   - Kann parallel zu Milestone 9 entwickelt werden
   - Wichtig fuer Production-Use

4. **Milestone 10** (Radarr + Multi-Library) — Erweiterte Features
   - Multi-Library ist komplexer, kann optional sein
   - Radarr-Feature-Paritaet sollte vor Public Beta abgeschlossen sein
   - Abhaengigkeit: Milestone 8 (Embedded-Sub-Detection auch fuer Radarr)

5. **Milestone 12** (Public Beta) — Release-Vorbereitung
   - Sollte nach allen anderen Features kommen
   - Onboarding-Wizard profitiert von allen vorherigen Features
   - Dokumentation sollte alle Features abdecken

### Provider-Erweiterung

Neuen Provider hinzufuegen:
1. `backend/providers/myprovider.py` erstellen
2. `SubtitleProvider` erben, `name`/`languages` setzen
3. `search()` und `download()` implementieren
4. `@register_provider` Decorator
5. Config-Felder in `config.py` hinzufuegen
6. Import in `ProviderManager._init_providers()` hinzufuegen

### Bazarr-Komponenten als Referenz

| Bazarr-Quelle | Sublarr-Nutzung |
|---|---|
| `subliminal_patch/providers/jimaku.py` | Architektur-Vorlage fuer `providers/jimaku.py` |
| `subliminal_patch/providers/animetosho.py` | Feed-API Pattern fuer `providers/animetosho.py` |
| `subliminal_patch/providers/mixins.py` | ZIP/RAR/XZ Extraction Logic |
| `subliminal_patch/score.py` | Scoring-Weights (Episode/Movie) |
| `subliminal_patch/http.py` | RetryingSession Pattern |
| `bazarr/subtitles/wanted/` | Wanted-Detection Algorithmus (Milestone 2) |
| `bazarr/subtitles/upgrade.py` | Upgrade-Logik Konzept (Milestone 5) |
