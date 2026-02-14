# Sublarr Roadmap — Open Subtitle Platform mit LLM-Uebersetzung

> **Vision:** Sublarr wird zur offenen, erweiterbaren Subtitle-Plattform die Bazarr nicht nur ersetzt,
> sondern mit Plugin-System, Multi-Backend-Translation, Whisper-Integration und Standalone-Modus
> weit uebertrifft. Anime und ASS-Qualitaet bleiben im Vordergrund, aber das System ist offen
> genug fuer jeden Use-Case.

## Status-Uebersicht

### Phase 1: Foundation (v1.0-beta) — ABGESCHLOSSEN

| Milestone | Status | Beschreibung |
|---|---|---|
| 1 | ✅ Erledigt | Provider-System (OpenSubtitles, Jimaku, AnimeTosho) |
| 2 | ✅ Erledigt | Eigenstaendiges Wanted-System |
| 3 | ✅ Erledigt | Such- und Download-Workflow |
| 4 | ✅ Erledigt | Provider-UI + Management |
| 5 | ✅ Erledigt | Upgrade-System + Automatisierung |
| 6 | ✅ Erledigt | Erweiterte Provider, Language Profiles, Bazarr entfernt |
| 7 | ✅ Erledigt | Blacklist, History, HI-Removal |
| 8 | ✅ Erledigt | Embedded Subtitle Detection + Robustheit |
| 9 | ✅ Erledigt | Uebersetzungsqualitaet + Glossar |
| 10 | ✅ Erledigt | Radarr-Vollintegration + Multi-Library |
| 11 | ✅ Erledigt | Notification-System (Apprise) |
| 12 | ✅ Erledigt | Public Beta (Docker Hub, Docs, Onboarding) |

### Phase 2: Open Platform (v0.2.0-beta → v0.9.0-beta → v1.0.0) — IN PLANUNG

| Milestone | Status | Beschreibung | Geplante Version |
|---|---|---|---|
| 13 | 🔲 Geplant | Provider Plugin-Architektur + Expansion | v0.2.0-beta |
| 14 | 🔲 Geplant | Translation Multi-Backend (Ollama, DeepL, LibreTranslate, OpenAI, Google) | v0.2.0-beta |
| 15 | 🔲 Geplant | Whisper Speech-to-Text Integration | v0.2.0-beta |
| 16 | 🔲 Geplant | Media-Server Abstraction (Plex, Kodi, Jellyfin, Emby) | v0.3.0-beta |
| 17 | 🔲 Geplant | Standalone-Modus (Folder-Watch, TMDB/AniList Metadata) | v0.3.0-beta |
| 18 | 🔲 Geplant | Forced/Signs Subtitle Management | v0.3.0-beta |
| 19 | 🔲 Geplant | Event-System, Script-Hooks + Custom Scoring | v0.4.0-beta |
| 20 | 🔲 Geplant | UI i18n (EN/DE) + Backup/Restore + Admin-Polish | v0.4.0-beta |
| 21 | 🔲 Geplant | Provider Health, OpenAPI, Performance | v0.4.0-beta |
| 22 | 🔲 Geplant | v0.9.0-beta Release + Community-Launch | v0.9.0-beta |
| 23 | 🔲 Geplant | Performance & Scalability Optimierungen | v0.5.0-beta |

### Phase 3: Advanced Features & UX (v1.1+) — IN PLANUNG

| Milestone | Status | Beschreibung |
|---|---|---|
| 24 | 🔲 Geplant | Subtitle-Vorschau & Editor |
| 25 | 🔲 Geplant | Batch-Operations & Smart-Filter |
| 26 | 🔲 Geplant | Subtitle-Vergleichstool & Quality-Metrics |
| 27 | 🔲 Geplant | Subtitle-Sync & Health-Check Tools |
| 28 | 🔲 Geplant | Erweiterte Dashboard-Widgets & Quick-Actions |
| 29 | 🔲 Geplant | API-Key-Management & Export/Import-Erweiterungen |
| 30 | 🔲 Geplant | Notification-Templates & Advanced-Filter |
| 31 | 🔲 Geplant | Subtitle-Deduplizierung & Cleanup-Tools |
| 32 | 🔲 Geplant | Externe Tool-Integrationen & Migration-Tools |

---

## Phase 1: Foundation (v1.0-beta) — Details

<details>
<summary>Milestone 1-12 (alle abgeschlossen — aufklappen fuer Details)</summary>

### Milestone 1: Provider-Fundament ✅

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

### Milestone 2: Wanted-System (eigenstaendig) ✅

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

### Milestone 3: Such- und Download-Workflow ✅

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

---

### Milestone 4: Provider-UI + Management ✅

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

### Milestone 5: Upgrade-System + Automatisierung ✅

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

### Milestone 6: Erweiterte Provider, Language Profiles, Bazarr entfernt ✅

**Ziel:** Neuer Provider, Multi-Language Support, Bazarr komplett entfernen.

**Erledigt:**
- [x] SubDL Provider hinzugefuegt (Subscene-Nachfolger, REST API, ZIP-Download)
- [x] `bazarr_client.py` endgueltig entfernt, Deprecation-Warning fuer alte Config
- [x] Language-Profile System (DB, API, Frontend, Multi-Target)
- [x] `.env.example` aktualisiert

**Neue Dateien:** 1 (`providers/subdl.py`) | **Geloeschte Dateien:** 1 (`bazarr_client.py`)

---

### Milestone 7: Blacklist, History, HI-Removal ✅

**Ziel:** Bazarr Feature-Paritaet: Subtitle-Blacklisting, Download-History, Hearing-Impaired Tag Removal.

**Erledigt:**
- [x] Blacklist-System (DB, API, Frontend, Provider-Filterung)
- [x] History-Page (Download-History, Statistiken, Filter)
- [x] HI-Tag Removal (Regex-basiert, konfigurierbar)
- [x] Navigation: History + Blacklist in Sidebar

**Neue Dateien:** 3 (`hi_remover.py`, `History.tsx`, `Blacklist.tsx`)

---

### Milestone 8: Embedded Subtitle Detection + Robustheit ✅

**Ziel:** Embedded Subs im MKV erkennen, Wanted-Liste praeziser machen.

**Erledigt:**
- [x] ffprobe-Integration (Embedded-Stream-Erkennung, Sprache, Format)
- [x] ffprobe-Cache-System (mtime-basierte Invalidierung)
- [x] Embedded Sub Extraction (ffmpeg-basiert, auf Benutzer-Anforderung)
- [x] Credential-Sanitization (Whitespace-Trimming)
- [x] Path-Mapping UI + Test-Button

---

### Milestone 9: Uebersetzungsqualitaet + Glossar ✅

**Ziel:** Bessere LLM-Uebersetzungen, konsistente Terminologie.

**Erledigt:**
- [x] Glossar-System (DB, API, Frontend-Editor in SeriesDetail)
- [x] Glossar-Integration in Translation-Pipeline
- [x] Uebersetzungs-Validierung (Zeilenanzahl, Halluzination, Length-Ratio)
- [x] Prompt-Presets (DB, Default-Preset, Settings-UI)

---

### Milestone 10: Radarr-Vollintegration + Multi-Library ✅

**Ziel:** Radarr gleichwertig zu Sonarr, mehrere Media-Libraries unterstuetzen.

**Erledigt:**
- [x] Radarr Anime-Movie-Filter (Tag-basiert)
- [x] Radarr Metadata-Enrichment (IMDB, TMDB, Year)
- [x] Radarr Webhook-Integration (Download, MovieFileDelete)
- [x] Multi-Library Config (JSON-Array, Migration, Fallback)
- [x] Multi-Library Backend + Frontend (Instanz-Editor, Filter, Badges)
- [x] Jellyfin/Emby Library-Refresh (Item-Level + Fallback)

---

### Milestone 11: Notification-System (Apprise) ✅

**Ziel:** Benachrichtigungen fuer alle wichtigen Events via Apprise (90+ Services).

**Erledigt:**
- [x] Apprise-Backend-Modul (`notifier.py`)
- [x] Notification-Config (URLs, Event-Toggles, Manual-Suppress)
- [x] Trigger-Integration (Download, Upgrade, Batch, Error)
- [x] Notification-API + Settings-UI

---

### Milestone 12: Public Beta (Docker Hub, Docs, Onboarding) ✅

**Ziel:** Sublarr als oeffentliches Projekt veroeffentlichen.

**Erledigt:**
- [x] GitHub Actions CI/CD (Multi-Arch: amd64, arm64)
- [x] Dockerfile-Optimierungen (Multi-Stage, Health-Check)
- [x] Onboarding-Wizard (5-Step Setup)
- [x] Dokumentation (README, ARCHITECTURE, API, PROVIDERS, CONTRIBUTING)
- [x] Unraid Community App Template
- [x] Release v1.0.0-beta

</details>

---

## Phase 2: Open Platform (v0.2.0-beta → v0.9.0-beta → v1.0.0)

> **Leitmotiv:** Von "Bazarr-Ersatz" zu "offene Subtitle-Plattform".
> Jeder Milestone macht Sublarr flexibler und erweiterbarer, ohne den Anime/ASS-Fokus zu verlieren.

---

## Milestone 13: Provider Plugin-Architektur + Expansion

**Ziel:** Offenes Plugin-System fuer Provider (Drop-in Python-Dateien) + 8-10 neue Built-in Provider.
Sublarr wird so offen wie Bazarr bei Providern, aber mit sauberer Architektur.

**Motivation (Community):**
- Bazarr hat ~20+ Provider, Sublarr nur 4 — groesste Luecke fuer Non-Anime-User
- Community will eigene Provider schreiben koennen ohne Sublarr-Fork
- Provider-Qualitaet bei Bazarr schwankt stark (subliminal_patch Metaclass-Magic)

### Plugin-System

- [ ] **Plugin-Verzeichnis + Auto-Discovery:**
  - Neues Verzeichnis `backend/providers/plugins/` (Volume-Mount in Docker: `/config/providers/`)
  - Beim Start: Alle `.py` Dateien im Plugin-Verzeichnis scannen
  - Jede Datei die eine `SubtitleProvider`-Subclass exportiert wird registriert
  - `ProviderManager._init_providers()` refactoren: Built-in + Plugin-Provider laden
  - Reihenfolge: Built-in zuerst, dann Plugins (alphabetisch)

- [ ] **Plugin-Manifest + Validation:**
  - Provider-Klasse erhaelt optionale Class-Attribute: `version`, `author`, `description`, `homepage`
  - Validation beim Laden: Name-Collision-Check, required methods vorhanden, safe import
  - Error-Handling: Fehlerhafter Plugin crashed nicht den ganzen ProviderManager
  - Logging: Geladene Plugins mit Version anzeigen beim Start

- [ ] **Hot-Reload Support:**
  - API-Endpoint `POST /api/v1/providers/reload` — Plugins neu laden ohne Restart
  - File-Watcher (optional, `watchdog`): Automatisch neu laden bei Datei-Aenderung
  - Frontend: "Reload Providers" Button in Settings

- [ ] **Plugin-Config-System:**
  - Provider-spezifische Config-Felder werden aus dem Provider selbst gelesen
  - Neues Class-Attribute `config_fields`: Liste von `{name, type, label, required, default}`
  - Settings-UI rendert dynamisch Formulare basierend auf `config_fields`
  - Config-Werte in `config_entries` DB-Tabelle (Prefix: `provider_{name}_`)
  - Kein Hardcoding von Provider-Config in `config.py` mehr noetig

- [ ] **Plugin-Template + Dokumentation:**
  - `docs/PLUGIN_DEVELOPMENT.md` — Schritt-fuer-Schritt Guide
  - `backend/providers/plugins/_template.py` — Kommentiertes Beispiel-Plugin
  - Beispiel-Plugin: `backend/providers/plugins/example_provider.py` (funktionsfaehig, deaktiviert)

### Built-in Provider Expansion

- [ ] **Addic7ed Provider** (`providers/addic7ed.py`):
  - Web-Scraping-basiert, bekannt fuer TV-Serien
  - Session-basiert (Login optional), SRT-Format
  - Rate-Limit: 24 Downloads pro Tag (ohne VIP)

- [ ] **Podnapisi Provider** (`providers/podnapisi.py`):
  - REST API, starke europaeische Sprach-Abdeckung
  - XML-basierte Suche, gute Movie-Unterstuetzung
  - Kein Auth noetig

- [ ] **Gestdown Provider** (`providers/gestdown.py`):
  - Subscene-Nachfolger (neben SubDL), REST API
  - Gute Anime-Abdeckung, ZIP-Download

- [ ] **Kitsunekko Provider** (`providers/kitsunekko.py`):
  - Japanische Anime-Subs (ASS/SRT), Fansub-Qualitaet
  - Scraping-basiert, kein Auth
  - Besonders wertvoll fuer JP→DE Uebersetzungs-Pipeline

- [ ] **Whisper-Subgen Provider** (`providers/whisper_subgen.py`):
  - Anbindung an externe Subgen/Whisper-Instanz als Provider
  - Generiert SRT aus Audio wenn kein Provider Subs findet
  - Niedrigste Prioritaet (Fallback), hohe Latenz markiert
  - Vorbereitung fuer Milestone 15 (integriertes Whisper)

- [ ] **Napisy24 Provider** (`providers/napisy24.py`):
  - Polnische Subtitle-Community, REST API
  - Starke polnische Sprachabdeckung

- [ ] **Titrari Provider** (`providers/titrari.py`):
  - Rumaenische Subtitle-Community
  - Europaeische Sprachvielfalt

- [ ] **LegendasDivx Provider** (`providers/legendasdivx.py`):
  - Brasilianisch/Portugiesisch fokussiert
  - Gute Film + Serien Abdeckung

### Provider Health Monitoring (Basis)

- [ ] **Fehler-Tracking pro Provider:**
  - Neue DB-Tabelle `provider_health` (provider_name, consecutive_errors, last_error, last_success, disabled_until)
  - Auto-Disable nach 5 aufeinanderfolgenden Fehlern (konfigurierbar)
  - Auto-Re-Enable nach Cooldown-Periode (Default: 30 Minuten)
  - Provider-Status-Badge im Frontend (Healthy/Degraded/Disabled)

- [ ] **Provider-Statistiken Dashboard:**
  - Neue API: `GET /api/v1/providers/stats` — Erfolgsrate, Avg Response Time, Downloads pro Provider
  - Dashboard-Widget: Provider-Health-Uebersicht
  - Settings: Pro-Provider Error-Threshold + Cooldown konfigurierbar

**Neue Dateien:** ~12 (Plugin-System + 8 Provider + Template) | **Geschaetzte Zeilen:** +2500

**Abhaengigkeiten:** Keine (baut auf bestehendem Provider-ABC auf)

---

## Milestone 14: Translation Multi-Backend

**Ziel:** Translation-Backend-Abstraction — Ollama bleibt Default, aber DeepL, LibreTranslate,
Google Cloud Translation und OpenAI API werden als Alternativen unterstuetzt.
Aehnliches Konzept wie Apprise fuer Notifications: Ein Interface, viele Backends.

**Motivation (Community):**
- Bazarr hat KEINE Uebersetzung — Sublarrs USP weiter ausbauen
- Nicht jeder hat GPU fuer Ollama, Cloud-APIs als Alternative
- LibreTranslate fuer Self-Hosted-Puristen
- Qualitaetsvergleich zwischen Backends erleichtern

### Backend-Abstraction

- [ ] **TranslationBackend ABC** (`backend/translation/__init__.py`):
  - Neues Package `backend/translation/`
  - Abstract Base Class: `translate_batch(lines, source_lang, target_lang, glossary, prompt) → list[str]`
  - Methoden: `health_check()`, `get_name()`, `get_config_fields()`, `supports_glossary()`
  - Bestehender `ollama_client.py` wird zu `backend/translation/ollama.py` refactored
  - Alle Backends registrieren sich aehnlich wie Provider

- [ ] **Ollama Backend** (`backend/translation/ollama.py`):
  - Migration des bestehenden `ollama_client.py` Code
  - Gleiche Funktionalitaet: Batch, Retry, Validation, Glossar, Halluzination-Detection
  - Bleibt Default-Backend
  - Config: `SUBLARR_TRANSLATION_BACKEND=ollama` (Default)

- [ ] **DeepL Backend** (`backend/translation/deepl.py`):
  - DeepL API (Free + Pro)
  - Glossar-Support via DeepL Glossary API
  - Rate-Limit-Handling (500k chars/Monat Free, unlimitiert Pro)
  - Config: API-Key, Pro/Free Toggle
  - Besonderheit: Kein Custom-Prompt moeglich — nur Source→Target

- [ ] **LibreTranslate Backend** (`backend/translation/libretranslate.py`):
  - Self-Hosted LibreTranslate API
  - Kein Auth noetig (self-hosted), optional API-Key
  - Batch-Support via API
  - Config: URL, API-Key (optional)

- [ ] **OpenAI-Compatible Backend** (`backend/translation/openai_compat.py`):
  - OpenAI API, Azure OpenAI, oder jeder OpenAI-kompatible Endpoint
  - Chat Completions API (`/v1/chat/completions`)
  - Custom Prompt + Glossar-Support (wie Ollama)
  - Config: API-Key, Base-URL, Model-Name
  - Funktioniert auch mit lokalen Alternativen (LM Studio, vLLM, text-generation-webui)

- [ ] **Google Cloud Translation Backend** (`backend/translation/google_translate.py`):
  - Google Cloud Translation API v3
  - Glossar-Support via Cloud Glossaries
  - Config: Service-Account-JSON oder API-Key

### Integration

- [ ] **Backend-Auswahl pro Language-Profile:**
  - `language_profiles` Tabelle: Neues Feld `translation_backend` (Default: global Setting)
  - Globales Setting: `SUBLARR_TRANSLATION_BACKEND` (Default: `ollama`)
  - Pro Serie/Film ueberschreibbar via Language-Profile
  - Use-Case: Anime-Serien mit Ollama (bessere Prompt-Kontrolle), Filme mit DeepL (schneller)

- [ ] **Fallback-Chain:**
  - Konfigurierbare Reihenfolge: z.B. `ollama → deepl → libretranslate`
  - Wenn Backend 1 fehlschlaegt → naechstes Backend probieren
  - Config: `SUBLARR_TRANSLATION_FALLBACK=deepl,libretranslate`

- [ ] **Backend-Config UI:**
  - Settings → neuer Tab "Translation" (ersetzt bisherigen Ollama-Bereich)
  - Backend-Auswahl-Dropdown (Global Default)
  - Pro-Backend Konfigurationsformulare (dynamisch basierend auf `get_config_fields()`)
  - Test-Button pro Backend
  - Fallback-Chain Editor (Drag-and-Drop Reihenfolge)

- [ ] **Quality-Metrics pro Backend:**
  - DB-Tracking: Welches Backend hat welche Datei uebersetzt
  - Dashboard-Widget: Uebersetzungen pro Backend, Fehlerrate
  - History-Page: Backend-Badge pro Download

**Neue Dateien:** 7 (Package + 5 Backends + Tests) | **Geschaetzte Zeilen:** +1800

**Abhaengigkeiten:** Keine (Refactoring des bestehenden ollama_client.py)

---

## Milestone 15: Whisper Speech-to-Text Integration

**Ziel:** Wenn kein Provider Untertitel findet, kann Sublarr selbst aus dem Audio-Track
Untertitel generieren. Lokal via faster-whisper oder extern via Subgen-API.

**Motivation (Community):**
- Bazarr + Subgen ist der gaengige Workaround — Sublarr integriert das nativ
- Fuer Nischen-Anime oder neue Releases gibt es oft keine Provider-Subs
- Whisper-generierte SRT → LLM-Uebersetzung → Ziel-SRT/ASS ist ein starker Workflow

### Whisper-Engine

- [ ] **Whisper Backend ABC** (`backend/whisper/__init__.py`):
  - Neues Package `backend/whisper/`
  - Abstract Base Class: `transcribe(audio_path, language) → list[SubtitleLine]`
  - `SubtitleLine`: Dataclass mit `start_time`, `end_time`, `text`
  - Methoden: `health_check()`, `get_available_models()`, `get_supported_languages()`

- [ ] **faster-whisper Backend** (`backend/whisper/faster_whisper.py`):
  - `faster-whisper` Library (CTranslate2-basiert, 4x schneller als original Whisper)
  - Model-Auswahl: tiny, base, small, medium, large-v3 (konfigurierbar)
  - GPU-Support (CUDA) mit CPU-Fallback
  - VAD-Filter (Voice Activity Detection) fuer bessere Segmentierung
  - Batch-Processing: Queue-basiert, ein File nach dem anderen
  - Config: Model-Name, Device (auto/cpu/cuda), Compute-Type (float16/int8)
  - `requirements.txt`: `faster-whisper` (optional, nur wenn aktiviert)

- [ ] **Subgen-API Backend** (`backend/whisper/subgen_api.py`):
  - Externe Subgen-Instanz als API-Endpoint
  - HTTP-basiert: POST Audio-Datei → SRT zurueck
  - Config: Subgen-URL, Timeout
  - Fuer User die Subgen bereits laufen haben

- [ ] **Audio-Extraktion** (`backend/whisper/audio.py`):
  - ffmpeg-basiert: Audio-Track aus MKV/MP4 extrahieren
  - Sprach-Auswahl: Japanischen Audio-Track bevorzugen (fuer Anime)
  - Temporaere WAV/FLAC-Datei erstellen → nach Transkription loeschen
  - Nutzung des bestehenden ffprobe-Cache fuer Stream-Info

### Pipeline-Integration

- [ ] **Translation-Pipeline erweitern:**
  - Neuer Case in `translator.py`: Case D (Whisper-Fallback)
  - Nach Case C (Provider-Suche fehlgeschlagen) → Whisper-Transkription starten
  - Whisper erzeugt Source-Language SRT → Translation-Backend uebersetzt → Ziel-SRT/ASS
  - Konfigurierbar: Whisper als Fallback aktivieren/deaktivieren
  - Setting: `whisper_enabled` (Default: false), `whisper_backend` (faster-whisper/subgen)
  - Setting: `whisper_auto_fallback` — automatisch bei Provider-Failure oder nur manuell

- [ ] **Whisper-Queue-System:**
  - Separate Queue fuer Whisper-Jobs (CPU/GPU-intensiv)
  - Max-Concurrent-Jobs Setting (Default: 1)
  - Progress-Tracking: Whisper-Fortschritt in Prozent (faster-whisper reportet das)
  - WebSocket-Events: `whisper_job_started`, `whisper_job_progress`, `whisper_job_completed`
  - Abbruch-Moeglichkeit fuer laufende Jobs

- [ ] **Whisper-UI:**
  - Settings → Whisper-Tab: Backend-Auswahl, Model-Auswahl, Device-Config
  - Wanted-Page: "Transcribe" Button pro Item (manueller Whisper-Trigger)
  - Activity-Page: Whisper-Jobs mit Progress-Bar
  - Dashboard: Whisper-Statistiken (Transkriptionen heute, Avg-Dauer)

- [ ] **Sprach-Erkennung:**
  - faster-whisper kann Sprache automatisch erkennen
  - Validation: Erkannte Sprache == erwartete Source-Language?
  - Warnung wenn Sprache nicht uebereinstimmt (z.B. Dub statt Original)

**Neue Dateien:** 5 (Package + 2 Backends + Audio + Tests) | **Geschaetzte Zeilen:** +1500

**Abhaengigkeiten:** Milestone 14 (Translation-Backend ABC fuer Whisper→Translate Chain)

---

## Milestone 16: Media-Server Abstraction (Plex, Kodi, Jellyfin, Emby)

**Ziel:** Einheitliches Interface fuer alle grossen Media-Server. Plex und Kodi neu,
Jellyfin/Emby in das neue Interface migrieren. Sublarr ist Media-Server-agnostisch.

**Motivation (Community):**
- Bazarr unterstuetzt Sonarr/Radarr + alle Media-Server — Sublarr nur Jellyfin/Emby
- Plex ist der meistgenutzte Media-Server im Homelab-Bereich
- Kodi-User wollen auch Subtitle-Automation

### Media-Server ABC

- [ ] **MediaServer ABC** (`backend/media_servers/__init__.py`):
  - Neues Package `backend/media_servers/`
  - Abstract Base Class: `refresh_item(file_path)`, `get_item_by_path(path)`, `health_check()`
  - Optional: `get_libraries()`, `scan_library(library_id)`
  - Bestehender `jellyfin_client.py` wird zu `backend/media_servers/jellyfin.py` migriert

- [ ] **Jellyfin/Emby Backend** (`backend/media_servers/jellyfin.py`):
  - Migration des bestehenden `jellyfin_client.py` Code
  - Gleiche Funktionalitaet, aber neues Interface
  - Emby-Kompatibilitaet beibehalten (identische API)

- [ ] **Plex Backend** (`backend/media_servers/plex.py`):
  - PlexAPI Library (`python-plexapi`)
  - Auth: Plex Token oder Account-Login
  - Library-Refresh nach Subtitle-Download
  - Item-Lookup via Datei-Pfad
  - Webhook-Empfang: `/api/v1/webhook/plex` (optional)
  - Config: Plex URL, Token

- [ ] **Kodi Backend** (`backend/media_servers/kodi.py`):
  - JSON-RPC API (HTTP-basiert)
  - Library-Update nach Subtitle-Download (`VideoLibrary.Scan`)
  - Item-Lookup via Datei-Pfad (`Files.GetFileDetails`)
  - Config: Kodi URL, Username, Password
  - Mehrere Kodi-Instanzen (JSON-Array wie Sonarr/Radarr)

### Integration

- [ ] **Multi-Server Config:**
  - Config: `SUBLARR_MEDIA_SERVERS_JSON` — JSON-Array mit Server-Definitionen
  - Format: `[{"type": "jellyfin", "name": "Main", "url": "...", "api_key": "..."}, ...]`
  - Mehrere Server gleichzeitig (z.B. Jellyfin + Plex)
  - Alle konfigurierten Server werden bei Subtitle-Download benachrichtigt

- [ ] **Settings-UI Erweiterung:**
  - Settings → neuer Tab "Media Servers" (ersetzt bisherigen Jellyfin-Bereich)
  - Server-Typ Dropdown (Jellyfin/Emby, Plex, Kodi)
  - Multi-Server Editor (Add/Edit/Delete)
  - Test-Connection Button pro Server
  - Server-Status-Badge (Connected/Disconnected)

- [ ] **Onboarding-Update:**
  - Onboarding-Wizard: Schritt "Media Server" anpassen (Multi-Server, Multi-Type)
  - Optional-Skip beibehalten (Media-Server ist nicht Pflicht)

**Neue Dateien:** 4 (Package + 3 Backends) | **Geschaetzte Zeilen:** +1000

**Abhaengigkeiten:** Keine (Refactoring des bestehenden jellyfin_client.py)

---

## Milestone 17: Standalone-Modus (Folder-Watch, TMDB/AniList Metadata)

**Ziel:** Sublarr funktioniert OHNE Sonarr/Radarr — ueberwacht Verzeichnisse direkt,
erkennt Medien-Dateien und holt Metadaten von TMDB/AniList/TVDB.

**Motivation (Community):**
- Bazarr erfordert zwingend Sonarr oder Radarr — oft genannter Kritikpunkt
- Manche User haben Medien manuell organisiert oder nutzen andere Tools
- Standalone-Modus macht Sublarr unabhaengig vom *arr-Stack

### Folder-Watcher

- [ ] **Filesystem-Watcher** (`backend/folder_watcher.py`):
  - `watchdog` Library fuer Filesystem-Events (cross-platform)
  - Ueberwacht konfigurierte Verzeichnisse auf neue/geaenderte Video-Dateien
  - Unterstuetzte Formate: `.mkv`, `.mp4`, `.avi`, `.m4v` (konfigurierbar)
  - Event-Types: Created, Modified, Moved (nicht Deleted)
  - Debounce: 30 Sekunden nach letztem Event bevor Processing (Datei noch am Kopieren?)
  - Config: `SUBLARR_WATCH_DIRS_JSON` — JSON-Array von Verzeichnispfaden
  - Config: `SUBLARR_WATCH_ENABLED` (Default: false)

- [ ] **Media-File-Parser** (`backend/media_parser.py`):
  - Dateinamen-Analyse: Titel, Jahr, Season, Episode, Release-Group, Aufloesung
  - Library: `guessit` (etablierter Parser, kennt Anime-Patterns)
  - Ordnerstruktur-Analyse: `/Anime/Series Name/Season 01/Episode.mkv`
  - Fallback: Regex-Patterns fuer gaengige Benennungen
  - Ergebnis: `ParsedMedia` Dataclass kompatibel mit `VideoQuery`

### Metadata-Fetching

- [ ] **TMDB Client** (`backend/metadata/tmdb.py`):
  - Neues Package `backend/metadata/`
  - TMDB API v3 (kostenloser API-Key)
  - Suche: Titel + Jahr → TMDB ID, IMDB ID, Poster, Beschreibung
  - Serien: Season/Episode-Info, Air-Dates
  - Config: API-Key

- [ ] **AniList Client** (`backend/metadata/anilist.py`):
  - GraphQL API (kein Auth noetig)
  - Anime-Erkennung: Ist diese Serie ein Anime?
  - Episode-Mapping: AniList → AniDB (fuer Provider-Suche)
  - Ergaenzt bestehenden `anidb_mapper.py`

- [ ] **TVDB Client** (`backend/metadata/tvdb.py`):
  - TVDB API v4 (kostenloser API-Key)
  - Alternative zu TMDB fuer Serien-Identifikation
  - TVDB ID ist Standard in Sonarr — kompatible IDs

### Standalone-Library

- [ ] **Standalone-Library-Manager:**
  - Neue DB-Tabellen: `standalone_series`, `standalone_movies`, `standalone_episodes`
  - Auto-Grouping: Dateien mit gleichem Titel → Serie
  - Metadata-Enrichment: Parser-Ergebnis → TMDB/AniList Suche → DB speichern
  - Manuelles Override: User kann Metadaten korrigieren
  - Library-Page: Funktioniert identisch ob Sonarr/Radarr oder Standalone

- [ ] **Wanted-Scanner Integration:**
  - `wanted_scanner.py` erweitern: Neben Sonarr/Radarr-Scan auch Standalone-Scan
  - Standalone-Items in gleicher `wanted_items` Tabelle (neues Feld: `source` = sonarr/radarr/standalone)
  - Gleiche Pipeline: Wanted → Search → Download → Translate

- [ ] **Settings-UI:**
  - Settings → "Library Sources" Tab
  - Toggle: Sonarr, Radarr, Folder-Watch (mehrere gleichzeitig moeglich)
  - Folder-Watch: Verzeichnisse hinzufuegen/entfernen + Browse-Button
  - TMDB/TVDB API-Key Felder
  - Scan-Button: Manueller Full-Scan der Watch-Directories

- [ ] **Onboarding-Update:**
  - Onboarding-Wizard: Neuer Pfad "Standalone" (ohne Sonarr/Radarr)
  - Schritt 1: Watch-Verzeichnisse auswaehlen
  - Schritt 2: TMDB API-Key eingeben
  - Schritt 3: Erster Scan starten

**Neue Dateien:** 6 (Watcher + Parser + 3 Metadata-Clients + Tests) | **Geschaetzte Zeilen:** +2000

**Abhaengigkeiten:** Keine (neue unabhaengige Komponente)

---

## Milestone 18: Forced/Signs Subtitle Management

**Ziel:** Forced Subtitles (nur Signs/Foreign-Parts) als eigene Kategorie verwalten —
getrennt von Full-Subs, ohne Wanted-Spam wie bei Bazarr.

**Motivation (Community):**
- Bazarr markiert ALLE Medien ohne Forced-Subs als "Wanted" → Tausende Eintraege
- Signs/Songs-Erkennung existiert bereits in `ass_utils.py` — darauf aufbauen
- Anime hat oft Signs (Schilder, Texte) die separat uebersetzt werden muessen

### Forced-Subtitle-System

- [ ] **Forced-Sub Kategorie in DB:**
  - `wanted_items` Tabelle: Neues Feld `subtitle_type` (full/forced/signs, Default: full)
  - `subtitle_downloads` Tabelle: Gleiches Feld
  - Separate Zaehlung: Full-Subs und Forced-Subs unabhaengig tracken
  - Wanted-Summary: Getrennte Statistiken fuer Full vs Forced

- [ ] **Forced-Sub Provider-Suche:**
  - Provider-Search erweitern: `forced_only` Parameter in `VideoQuery`
  - OpenSubtitles: Forced-Flag in API-Suche nutzen
  - SubDL: Forced/Foreign-Parts Filter
  - AnimeTosho/Jimaku: Signs-Track-Erkennung in Fansub-ASS (nutzt bestehende Style-Klassifizierung)
  - Scoring: Forced-Subs separat scoren (eigene Gewichtung)

- [ ] **Smart-Detection:**
  - ffprobe: Forced-Flag in embedded Subtitle-Streams erkennen
  - ASS-Analyse: Dateien mit >80% Sign-Styles als "Signs-Only" klassifizieren
  - Benennungs-Patterns: `.forced.srt`, `.signs.ass`, `.sdh.srt` erkennen
  - Heuristik: Wenn Full-Sub vorhanden aber kein Forced → KEIN Wanted-Eintrag (anders als Bazarr!)

- [ ] **Per-Serie Forced-Preference:**
  - Language-Profile: Neues Feld `forced_subtitle_mode` (disabled/separate/auto)
  - `disabled`: Forced-Subs ignorieren
  - `separate`: Forced-Subs als eigene Dateien suchen/erstellen
  - `auto`: Nur suchen wenn Medien-Datei Foreign-Audio-Parts hat
  - Default: `disabled` (kein Wanted-Spam)

- [ ] **Frontend-Updates:**
  - Wanted-Page: Filter-Dropdown "All / Full Subs / Forced/Signs"
  - Library-Page: Forced-Sub-Status-Badge pro Episode/Film
  - Settings: Globaler Default fuer Forced-Mode
  - SeriesDetail: Per-Serie Forced-Mode Override

**Neue Dateien:** 0 (Integration in bestehende Module) | **Geschaetzte Zeilen:** +800

**Abhaengigkeiten:** Keine (baut auf bestehender ASS Style-Klassifizierung auf)

---

## Milestone 19: Event-System, Script-Hooks + Custom Scoring

**Ziel:** Erweiterbares Event-System mit konfigurierbaren Shell-Script-Hooks und
anpassbaren Scoring-Regeln. Sublarr wird zur anpassbaren Plattform.

**Motivation (Community):**
- Bazarr hat Post-Processing Scripts — wichtig fuer Automatisierung
- Scoring-Gewichtung ist aktuell fest — User wollen das anpassen
- Event-System ermoeglicht Drittanbieter-Integrationen ohne Code-Aenderung

### Event-Bus

- [ ] **Internes Event-System** (`backend/events.py`):
  - Neues Modul: Publish/Subscribe Event-Bus
  - Event-Types: `subtitle_downloaded`, `subtitle_translated`, `subtitle_upgraded`,
    `whisper_completed`, `provider_error`, `wanted_scan_completed`, `batch_completed`
  - Event-Payload: Strukturierte Daten (file_path, language, provider, format, etc.)
  - Bestehende Notification-Trigger migrieren auf Event-Bus
  - WebSocket-Events automatisch aus Event-Bus generieren

### Script-Hooks

- [ ] **Hook-Engine** (`backend/hooks.py`):
  - Neues Modul: Shell-Script Ausfuehrung bei Events
  - Config: `SUBLARR_HOOKS_DIR` (Default: `/config/hooks/`)
  - Hook-Dateien: `on_download.sh`, `on_translate.sh`, `on_upgrade.sh`, etc.
  - Umgebungsvariablen pro Event:
    - `SUBLARR_EVENT` — Event-Name
    - `SUBLARR_FILE_PATH` — Pfad zur Subtitle-Datei
    - `SUBLARR_LANGUAGE` — Sprache
    - `SUBLARR_FORMAT` — Format (ass/srt)
    - `SUBLARR_PROVIDER` — Provider-Name
    - `SUBLARR_SERIES_TITLE` — Serien/Film-Name
    - `SUBLARR_EPISODE` — Episode-Info (SxxExx)
  - Timeout: Konfigurierbar (Default: 60 Sekunden)
  - Error-Handling: Hook-Fehler loggen aber Pipeline nicht blockieren
  - Sicherheit: Hooks laufen als gleicher User wie Sublarr, kein Sandboxing

- [ ] **Hook-UI:**
  - Settings → neuer Tab "Hooks & Automation"
  - Event-Liste mit Toggle (aktiviert/deaktiviert)
  - Hook-Script-Editor (einfacher Texteditor im Browser)
  - Hook-Test-Button (manueller Trigger mit Beispiel-Daten)
  - Hook-Log: Letzte Ausfuehrungen mit Exit-Code + Output

### Outgoing Webhooks

- [ ] **Custom Outgoing Webhooks:**
  - Zusaetzlich zu Script-Hooks: HTTP-Webhooks an beliebige URLs
  - Config: JSON-Array von Webhook-Definitionen `{url, events[], method, headers}`
  - Payload: JSON mit Event-Daten (gleiche Felder wie Script-Umgebungsvariablen)
  - Retry-Logik: 3 Versuche mit Exponential-Backoff
  - UI: Webhook-Editor in "Hooks & Automation" Tab

### Custom Scoring

- [ ] **Scoring-Konfiguration:**
  - Bestehende Scoring-Weights konfigurierbar machen:
    - `score_hash_match` (Default: 359)
    - `score_series_match` (Default: 180)
    - `score_year_match` (Default: 90)
    - `score_season_match` (Default: 30)
    - `score_episode_match` (Default: 30)
    - `score_release_group` (Default: 14)
    - `score_ass_bonus` (Default: 50)
  - Settings-UI: Scoring-Slider/Inputs
  - Preset-Buttons: "Sublarr Default", "Bazarr-Compatible", "ASS-Prioritaet"
  - Scoring-Erklaerung: Tooltip pro Gewichtung mit Beispiel

- [ ] **Provider-spezifische Scoring-Modifier:**
  - Pro Provider: Bonus/Malus-Offset (z.B. AnimeTosho +20, OpenSubtitles -10)
  - Konfigurierbar in Provider-Settings
  - Use-Case: Fansub-Provider generell hoeher bewerten

**Neue Dateien:** 3 (events.py, hooks.py, Tests) | **Geschaetzte Zeilen:** +1200

**Abhaengigkeiten:** Keine

---

## Milestone 20: UI i18n (EN/DE) + Backup/Restore + Admin-Polish

**Ziel:** Frontend in Englisch und Deutsch, Backup/Restore-System, UI-Verbesserungen.

**Motivation:**
- Sublarr ist ein deutsch-initiiertes Projekt — DE-UI ist Ehrensache
- Backup/Restore fehlt fuer Production-Deployments
- Admin-Verbesserungen fuer den taeglichen Betrieb

### Frontend i18n

- [ ] **i18n-Setup:**
  - `react-i18next` + `i18next` Integration
  - Namespace-Struktur: `common`, `dashboard`, `settings`, `wanted`, `library`, etc.
  - Language-Dateien: `frontend/src/locales/en/`, `frontend/src/locales/de/`
  - Sprach-Umschaltung: Dropdown im Header/Sidebar
  - Sprach-Persistenz: LocalStorage + Config-API
  - Fallback: Englisch wenn Key nicht uebersetzt

- [ ] **Englische Basis-Uebersetzung:**
  - Alle 12 Pages + Shared Components
  - Error-Messages, Tooltips, Placeholder-Texte
  - Datum/Uhrzeit-Formatierung (Intl API)

- [ ] **Deutsche Uebersetzung:**
  - Vollstaendige Uebersetzung aller Keys
  - Korrekte Fachbegriffe (Untertitel, Anbieter, Bibliothek, etc.)
  - Date/Time: Deutsches Format (DD.MM.YYYY, 24h)

### Backup/Restore

- [ ] **Backup-System** (`backend/backup.py`):
  - Neues Modul: Config + DB-Snapshot als ZIP exportieren
  - API: `POST /api/v1/backup` → ZIP-Download
  - Inhalt: SQLite DB-Dump, `config_entries` Export, Provider-Plugin-Liste
  - Optionen: Mit/ohne History-Daten, mit/ohne Provider-Cache
  - Automatische Backups: Konfigurierbar (taeglich/woechentlich)
  - Backup-Rotation: Max N Backups behalten (Default: 5)
  - Backup-Verzeichnis: `/config/backups/`

- [ ] **Restore-System:**
  - API: `POST /api/v1/restore` — ZIP-Upload → Validierung → Restore
  - Validierung: Schema-Version pruefen, Integrity-Checks
  - Merge-Strategie: Bestehende Daten behalten oder ueberschreiben (User-Wahl)
  - Warnung: "Dieser Vorgang ueberschreibt die aktuelle Konfiguration"

- [ ] **Backup-UI:**
  - Settings → neuer Tab "System" oder "Maintenance"
  - Backup-Button: Manuelles Backup erstellen + Download
  - Restore-Button: ZIP-Upload + Vorschau + Bestaetigung
  - Auto-Backup-Toggle + Frequenz
  - Backup-Liste: Vorhandene Backups mit Groesse + Datum

### Admin-Polish

- [ ] **System-Status Dashboard:**
  - System-Info-Widget: Version, Uptime, DB-Groesse, Provider-Count
  - Disk-Usage: Subtitle-Dateien Gesamt-Groesse, DB-Groesse
  - Queue-Status: Aktive Jobs, Pending Items

- [ ] **Umfangreiche Statistik-Seite:**
  - Neue Frontend-Seite "Statistics" im System-Bereich
  - Moderne, interaktive Visualisierungen mit Charts (Chart.js oder Recharts)
  - Zeitraum-Filter: Letzte 7/30/90 Tage, Gesamt, Custom Range
  - Export-Funktionen: CSV, JSON, PNG (für Charts)
  
  **Übersichts-Karten (Top-Level Metrics):**
  - Gesamt übersetzte Untertitel (mit Trend-Indikator)
  - Erfolgsrate (Success vs Failed)
  - Heute übersetzt (mit Vergleich zu gestern)
  - Durchschnittliche Übersetzungsdauer
  - Aktive Provider-Anzahl
  - Wanted-Items gesamt
  
  **Translation-Statistiken:**
  - Tägliche Übersetzungen (Liniendiagramm über Zeit)
  - Format-Verteilung (ASS vs SRT) - Donut/Pie Chart
  - Source-Sprache-Verteilung - Bar Chart
  - Erfolgsrate über Zeit - Liniendiagramm
  - Durchschnittliche Score-Verbesserung bei Upgrades
  - Quality-Warnings Trend
  
  **Provider-Statistiken:**
  - Provider-Performance-Vergleich (Bar Chart)
  - Erfolgsrate pro Provider (mit Trend)
  - Durchschnittliche Response-Zeit pro Provider
  - Downloads pro Provider (Stacked Bar Chart)
  - Cache-Hit-Rate pro Provider
  - Top Provider nach Score (Ranking-Tabelle)
  
  **Wanted-Statistiken:**
  - Wanted-Items über Zeit (Liniendiagramm)
  - Status-Verteilung (wanted/searching/found/failed) - Pie Chart
  - Erfolgsrate bei Suchen (Found vs Failed)
  - Durchschnittliche Suchdauer pro Item
  - Top gesuchte Serien/Filme (Tabelle)
  
  **Upgrade-Statistiken:**
  - Upgrade-History über Zeit
  - SRT→ASS Upgrades vs Score-Upgrades
  - Durchschnittliche Score-Verbesserung
  - Upgrade-Reasons-Verteilung
  
  **System-Statistiken:**
  - Uptime-Visualisierung
  - Job-Queue-Status (Pending/Running/Completed/Failed)
  - Batch-Operationen-Statistiken
  - Datenbank-Größe über Zeit
  - Cache-Größe pro Provider
  
  **Interaktive Features:**
  - Hover-Tooltips mit detaillierten Informationen
  - Klickbare Chart-Elemente für Drill-Down
  - Real-time Updates via WebSocket
  - Responsive Design (Mobile-optimiert)
  - Dark/Light Theme Support
  
  **Backend-API:**
  - `GET /api/v1/statistics/overview` - Übersichts-Metriken
  - `GET /api/v1/statistics/translation?days=30` - Translation-Stats mit Zeitraum
  - `GET /api/v1/statistics/providers?days=30` - Provider-Stats mit Zeitraum
  - `GET /api/v1/statistics/wanted?days=30` - Wanted-Stats mit Zeitraum
  - `GET /api/v1/statistics/upgrades?days=30` - Upgrade-Stats
  - `GET /api/v1/statistics/system` - System-Stats
  - `GET /api/v1/statistics/export?format=csv&days=30` - Export-Funktion

- [ ] **Log-Verbesserungen:**
  - Log-Level-Filter in UI (DEBUG/INFO/WARNING/ERROR)
  - Log-Download als Textdatei
  - Log-Rotation-Config (Max-Groesse, Max-Dateien)

- [ ] **Dark/Light Theme:**
  - Theme-Toggle im Header
  - Tailwind: `dark:` Prefix-Klassen fuer alle Komponenten
  - Theme-Persistenz: LocalStorage

- [ ] **Subtitle Processing Tools (niedrige Prioritaet):**
  - Neue "Tools" Dropdown-Menue in Series/Episode-Detail-Ansicht (aehnlich Bazarr)
  - Manuelle Subtitle-Verarbeitungs-Tools pro Episode/Film:
    - **Adjust Times** - Timing-Anpassungen (Offset in ms, Speed-Multiplikator)
    - **Remove Style Tags** - ASS-Style-Tags entfernen (z.B. `{\an8}`, `{\pos}`)
    - **Common Fixes** - Haeufige Probleme beheben (doppelte Leerzeichen, falsche Zeilenumbrueche, etc.)
    - **Fix Uppercase** - Falsche Grossschreibung korrigieren
    - **Add Color** - ASS-Color-Tags hinzufuegen (optional)
    - **Remove Emoji** - Emoji aus Subtitles entfernen (optional)
    - **Change Frame Rate** - Frame-Rate-Konvertierung (optional)
  - Backend-API: `POST /api/v1/subtitles/<file_path>/process` mit `tool` Parameter
  - Processing-Module: `backend/subtitle_tools.py` (TimeAdjuster, StyleRemover, CommonFixes, etc.)
  - Frontend: Tools-Dropdown mit Icons pro Tool
  - Batch-Processing: Mehrere Episoden gleichzeitig verarbeiten
  - Preview-Funktion: Aenderungen vor Anwendung anzeigen
  - Undo-Funktion: Original wiederherstellen
  - Hinweis: Niedrige Prioritaet, nur wenn Zeit vorhanden

**Neue Dateien:** 6 (backup.py, statistics.py, Statistics.tsx, subtitle_tools.py, Locale-Dateien, Tests) | **Geschaetzte Zeilen:** +3800

**Abhaengigkeiten:** Keine

---

## Milestone 21: Provider Health, OpenAPI, Performance

**Ziel:** Produktionsreife-Verbesserungen: API-Dokumentation, Performance-Optimierung,
erweiterte Diagnostik.

### OpenAPI/Swagger

- [ ] **OpenAPI-Spec Generierung:**
  - `flask-smorest` oder manuelle OpenAPI 3.0 YAML
  - Alle 50+ Endpoints dokumentiert
  - Request/Response-Schemas aus Pydantic-Models
  - Swagger-UI unter `/api/docs` (optional, deaktivierbar)
  - Spec-Download: `/api/v1/openapi.json`

### Performance

- [ ] **Wanted-Scan Optimierung:**
  - Inkrementeller Scan: Nur geaenderte/neue Dateien scannen
  - Parallel-Scan: asyncio oder Thread-Pool fuer ffprobe-Aufrufe
  - Scan-Dauer Ziel: <30 Sekunden fuer 500+ Serien

- [ ] **Provider-Suche Optimierung:**
  - Parallele Provider-Suche: Alle Provider gleichzeitig abfragen (statt sequenziell)
  - Result-Streaming: Erste Ergebnisse sofort anzeigen, nicht auf alle Provider warten
  - Connection-Pooling: Persistente HTTP-Sessions pro Provider

- [ ] **Frontend Performance:**
  - Code-Splitting: Lazy-Loading fuer Pages (React.lazy)
  - Virtual-Scrolling fuer grosse Listen (Library, Wanted, History)
  - Service-Worker: Offline-Faehigkeit fuer Dashboard

### Erweiterte Diagnostik

- [ ] **Health-Endpoint Erweiterung:**
  - `/api/v1/health/detailed` — Detaillierter System-Status
  - Checks: DB-Connectivity, Provider-Health, Ollama-Status, Disk-Space
  - Format: Kompatibel mit Uptime-Monitoring-Tools

- [ ] **Task-Scheduler Dashboard / Tasks-Seite:**
  - Neue Frontend-Seite "Tasks" im System-Bereich (aehnlich wie Bazarr)
  - Tabelle mit Spalten: Name, Interval, Next Execution, Run-Button
  - Uebersicht aller Scheduled Tasks mit naechster Ausfuehrung
  - Manueller Trigger pro Task (Run-Button)
  - Task-History (letzte 10 Ausfuehrungen mit Ergebnis)
  - Formatierung der Intervalle (z.B. "alle 6 Stunden", "täglich um 4:00", "jeden Sonntag um 3:00")
  - Relative Zeitangaben für nächste Ausführung (z.B. "in 28 Minuten", "in 6 Stunden")
  - Backend-API: `GET /api/v1/tasks` (Liste aller Tasks), `POST /api/v1/tasks/<name>/run` (manueller Run)
  - Task-Manager-System im Backend zur zentralen Registrierung und Verwaltung aller Tasks
  - Geplante Tasks:
    - Wanted Scan (konfigurierbares Intervall, Default: 6 Stunden)
    - Wanted Search (konfigurierbares Intervall, Default: 24 Stunden)
    - Provider Cache Maintenance (täglich um 3:00 Uhr)
    - Health Check (alle 6 Stunden)
    - Database Backup (wöchentlich am Sonntag um 3:00 Uhr, Platzhalter für Milestone 20)

**Neue Dateien:** 2 (OpenAPI, Diagnostik) | **Geschaetzte Zeilen:** +1000

**Abhaengigkeiten:** Alle vorherigen Milestones (dokumentiert die finale API)

---

## Milestone 22: v0.9.0-beta Release + Community-Launch

**Ziel:** Sublarr v0.9.0-beta als stabilisierte Beta-Version veroeffentlichen.
Alle Phase 2 Features sind implementiert, Stabilisierung und Bugfixes abgeschlossen.

### Dokumentation

- [ ] **Migration Guide v1.0.0-beta→v0.9.0-beta:**
  - Breaking Changes dokumentieren (Translation-Backend, Media-Server-Config)
  - Automatische Migration: Alte Config-Keys → neue Struktur
  - docker-compose.yml Update-Anleitung

- [ ] **Plugin-Entwickler Guide:**
  - `docs/PLUGIN_DEVELOPMENT.md` erweitern
  - Provider-Plugin Beispiele (einfach, mittel, komplex)
  - Translation-Backend-Plugin Guide
  - Best Practices, Testing, Publishing

- [ ] **User-Guide:**
  - `docs/USER_GUIDE.md` — Umfassende Benutzer-Dokumentation
  - Setup-Szenarien: Anime-focused, General-Purpose, Standalone
  - Troubleshooting erweitern
  - FAQ basierend auf Community-Feedback

### Community

- [ ] **Community-Provider-Repository:**
  - GitHub-Repository: `sublarr-providers` (Community-beigetragene Provider-Plugins)
  - Template-Repository fuer schnellen Einstieg
  - CI/CD: Automatische Tests fuer Community-Provider
  - Provider-Katalog in README

- [ ] **Release-Vorbereitung:**
  - CHANGELOG.md: Alle Aenderungen v1.0.0-beta→v0.9.0-beta
  - Version-Tag: `v0.9.0-beta`
  - Docker-Image: `sublarr:0.9.0-beta`, `sublarr:beta`
  - GitHub Release mit binaries/assets
  - Unraid Template Update
  - Reddit/r/selfhosted Announcement Post vorbereiten

- [ ] **Telemetrie (Opt-in):**
  - Anonyme Usage-Statistiken (Provider-Nutzung, Uebersetzungs-Volumen)
  - Opt-in bei Onboarding oder in Settings
  - Transparenz: Genau anzeigen welche Daten gesendet werden
  - Zweck: Priorisierung zukuenftiger Features

**Neue Dateien:** 3 (Docs, Migration-Script) | **Geschaetzte Zeilen:** +800

**Abhaengigkeiten:** Alle vorherigen Milestones

---

## Milestone 23: Performance & Scalability Optimierungen

**Ziel:** System-Optimierungen fuer bessere Performance, Skalierbarkeit und Production-Ready-Deployments.
Von SQLite zu PostgreSQL, Redis-Integration, persistente Job-Queues und weitere Performance-Verbesserungen.

**Motivation:**
- SQLite-Limitationen bei hoher Concurrency und Multi-Instance-Deployments
- In-Process Job-Queue geht bei Restart verloren
- Provider-Cache in SQLite ist langsamer als In-Memory-Cache
- Skalierbarkeit fuer groessere Libraries und hoehere Last

### Database-Optimierungen

- [ ] **SQLite → PostgreSQL Migration:**
  - SQLAlchemy als ORM/Abstraction Layer (Database-Agnostic)
  - Migrationstool fuer bestehende SQLite-Daten (`backend/migrations/`)
  - Connection Pooling via SQLAlchemy (konfigurierbare Pool-Groesse)
  - Read Replicas Support fuer Read-Heavy Operations (optional)
  - Config: `SUBLARR_DATABASE_URL` (SQLite oder PostgreSQL Connection String)
  - Fallback: SQLite bleibt Default fuer einfache Deployments
  - Migration-Strategie: Automatische Schema-Migration bei Start
  - Daten-Migration: Optionales CLI-Tool `python -m backend.migrate_db`

- [ ] **Database Connection Pooling (auch fuer SQLite):**
  - SQLAlchemy Connection Pool fuer SQLite (bessere Thread-Safety)
  - Konfigurierbare Pool-Parameter (size, max_overflow, timeout)
  - Thread-Local Connections fuer bessere Parallelitaet
  - Connection-Health-Checks und Auto-Reconnect

- [ ] **Database Indexing-Optimierungen:**
  - Composite Indices fuer haeufige Query-Patterns
  - Partial Indices fuer gefilterte Queries (z.B. `WHERE status='wanted'`)
  - Index-Analyse-Tool: `EXPLAIN QUERY PLAN` fuer alle wichtigen Queries
  - Automatische Index-Optimierung basierend auf Query-Logs

### Caching-Optimierungen mit Redis

- [ ] **Redis fuer Provider-Cache:**
  - Redis als primaeres Cache-Backend fuer Provider-Search-Results
  - TTL-basierte Expiration (konfigurierbar, Default: 1 Stunde)
  - Fallback zu SQLite wenn Redis nicht verfuegbar
  - Cache-Warming-Strategien (haeufige Queries vorladen)
  - Cache-Invalidierung bei Provider-Updates
  - Config: `SUBLARR_REDIS_URL` (optional, Default: deaktiviert)
  - Migration: Bestehende SQLite-Cache-Daten nach Redis migrieren

- [ ] **Redis fuer Session-Management:**
  - WebSocket-Session-Tracking in Redis
  - User-Session-Cache (fuer zukuenftige Multi-User-Support)
  - Session-Persistenz ueber Restarts

- [ ] **Redis fuer Rate-Limiting:**
  - Provider Rate-Limit-Tracking in Redis
  - API Rate-Limiting (konfigurierbar pro Endpoint)
  - Distributed Rate-Limiting ueber mehrere Instanzen
  - Sliding-Window-Algorithmus fuer praezise Limits

- [ ] **Multi-Layer Caching:**
  - L1: In-Memory (Python dict) fuer sehr haeufige Daten (z.B. Config)
  - L2: Redis fuer mittelfristige Daten (Provider-Cache, Sessions)
  - L3: Database fuer persistente Daten
  - Cache-Hit-Rate-Metriken pro Layer

### Job Queue-Optimierungen

- [ ] **Redis + RQ fuer Job Queue:**
  - RQ als Task Queue (einfacher als Celery, ausreichend fuer Sublarr)
  - Redis als Message Broker
  - Persistente Queue (ueberlebt Restarts)
  - Distributed Processing (mehrere Worker-Instanzen)
  - Job-Priorisierung (High/Normal/Low Priority)
  - Retry-Mechanismen mit Exponential-Backoff
  - Job-Scheduling (periodische Tasks)
  - Job-Monitoring: Status, Progress, Errors
  - Migration: Bestehende In-Process-Jobs zu Queue migrieren
  - Config: `SUBLARR_REDIS_URL`, `SUBLARR_WORKER_COUNT`

### Weitere Performance-Optimierungen

- [ ] **API Rate Limiting (Redis-basiert):**
  - Per-User/IP Limits
  - Quota-Management
  - Rate-Limit-Headers in Responses
  - Config: `SUBLARR_RATE_LIMIT_ENABLED`

- [ ] **Message Queue fuer Events (Redis Streams):**
  - Redis Streams fuer Event-Bus (einfacher als RabbitMQ)
  - Asynchrone Event-Verarbeitung
  - Event-Subscription fuer externe Services
  - Webhook-Delivery ueber Queue (retry, prioritization)
  - Decoupling von Komponenten

- [ ] **Object Storage fuer Subtitle-Dateien (sehr optional):**
  - S3/MinIO-Integration fuer Subtitle-Storage
  - Deduplizierung von Subtitle-Dateien (Content-Hash-basiert)
  - Migration: Bestehende lokale Dateien zu Object Storage
  - Config: `SUBLARR_STORAGE_TYPE` (local/s3/minio)
  - Fallback: Lokale Dateien bleiben Default
  - Vorteile: Nur fuer Multi-Instance-Deployments oder sehr grosse Libraries relevant
  - Hinweis: Fuer typische Self-Hosted-Deployments nicht noetig

- [ ] **Full-Text-Search (sehr optional):**
  - Elasticsearch oder Meilisearch-Integration
  - Indexierung von: Subtitle-History, Serien/Film-Titel, Glossar-Eintraegen, Blacklist
  - Fuzzy-Search fuer Tippfehler-Toleranz
  - Faceted Search fuer erweiterte Filter
  - Config: `SUBLARR_SEARCH_ENGINE_URL` (optional)
  - API: `GET /api/v1/search?q=...&type=history|series|glossary`
  - Hinweis: SQLite-Suche reicht fuer die meisten Use-Cases aus

### Monitoring & Observability

- [ ] **Prometheus Metrics Export:**
  - System-Metriken (CPU, Memory, Disk, Network)
  - Business-Metriken (Uebersetzungen/Tag, Downloads, Erfolgsrate)
  - Provider-Performance-Metriken (Response-Time, Success-Rate)
  - Queue-Metriken (Pending, Processing, Completed)
  - Endpoint: `/metrics` (Prometheus-Format)
  - Config: `SUBLARR_METRICS_ENABLED` (Default: true)

- [ ] **Grafana-Dashboards:**
  - Vordefinierte Dashboards fuer Sublarr
  - System-Health-Dashboard
  - Business-Metrics-Dashboard
  - Provider-Performance-Dashboard
  - Dashboard-JSON-Dateien in `docs/grafana/`


### Migration & Kompatibilitaet

- [ ] **Backward-Compatibility:**
  - SQLite bleibt Default (kein Breaking Change)
  - Redis optional (System funktioniert ohne)
  - Graceful Degradation: Features deaktivieren wenn Dependencies fehlen
  - Migration-Guide: SQLite → PostgreSQL, In-Process → Queue

- [ ] **Configuration:**
  - Neue Config-Keys fuer alle neuen Features
  - Environment-Variable-Support
  - Settings-UI erweitern (Database-Type, Redis-Config, etc.)
  - Health-Checks fuer alle neuen Dependencies

**Neue Dateien:** ~10 (Migrations, Redis-Client, Queue-Worker, Metrics, etc.) | **Geschaetzte Zeilen:** +3000

**Abhaengigkeiten:** 
- Optional: PostgreSQL (fuer Multi-Instance-Deployments)
- Optional: Redis (fuer Cache/Queue/Events - empfohlen)
- Optional: RQ (fuer Job-Queue, benoetigt Redis)
- Sehr optional: S3/MinIO (fuer Object Storage, nur Multi-Instance)
- Sehr optional: Elasticsearch/Meilisearch (fuer Full-Text-Search)
- Optional: Prometheus (fuer Metrics - empfohlen)

**Hinweis:** Alle neuen Dependencies sind optional. Das System funktioniert weiterhin mit SQLite und In-Process-Queue, aber bietet erweiterte Features fuer groessere Deployments.

---

## Geschaetzter Aufwand

### Phase 1: Foundation (v1.0-beta) — ABGESCHLOSSEN

| Milestone | Status | Schwerpunkt | Zeilen |
|---|---|---|---|
| 1 Provider-Fundament | ✅ | Backend | +1977 |
| 2 Wanted-System | ✅ | Backend | +700 |
| 3 Such-/Download-Flow | ✅ | Backend + Frontend | +560 |
| 4 Provider-UI | ✅ | Frontend | ~300 |
| 5 Upgrade + Automation | ✅ | Backend + Frontend | +800 |
| 6 Provider + Profiles | ✅ | Full-Stack | ~1500 |
| 7 Blacklist + History + HI | ✅ | Full-Stack | ~1200 |
| 8 Embedded Subs + Robustheit | ✅ | Backend + ffprobe | +400 |
| 9 Uebersetzungsqualitaet | ✅ | Backend (LLM) + Frontend | +800 |
| 10 Radarr + Multi-Library | ✅ | Backend + Config + Frontend | +600 |
| 11 Notification-System | ✅ | Backend + Frontend | +500 |
| 12 Public Beta | ✅ | DevOps + Docs | +1000 |
| **Gesamt Phase 1** | **✅** | | **~10337** |

### Phase 2: Open Platform (v0.2.0-beta → v0.9.0-beta → v1.0.0) — GEPLANT

| Milestone | Status | Schwerpunkt | Geschaetzte Zeilen |
|---|---|---|---|
| 13 Provider Plugin + Expansion | 🔲 | Backend Architektur + 8 Provider | +2500 |
| 14 Translation Multi-Backend | 🔲 | Backend Refactoring | +1800 |
| 15 Whisper Integration | 🔲 | Backend (Audio/ML) | +1500 |
| 16 Media-Server Abstraction | 🔲 | Backend Refactoring | +1000 |
| 17 Standalone-Modus | 🔲 | Backend + Metadata | +2000 |
| 18 Forced/Signs Subs | 🔲 | Backend + Frontend | +800 |
| 19 Event-System + Hooks + Scoring | 🔲 | Backend + Frontend | +1200 |
| 20 i18n + Backup + Admin | 🔲 | Frontend + Backend | +3800 |
| 21 Health + OpenAPI + Performance | 🔲 | Full-Stack | +1000 |
| 22 v0.9.0-beta Release | 🔲 | Docs + Community | +800 |
| 23 Performance + Scalability | 🔲 | Backend Architecture | +3000 |
| **Gesamt Phase 2** | **🔲** | | **~17900** |

### Phase 3: Advanced Features & UX (v2.1+) — GEPLANT

| Milestone | Status | Schwerpunkt | Geschaetzte Zeilen |
|---|---|---|---|
| 24 Subtitle-Vorschau & Editor | 🔲 | Frontend (Editor) | +2000 |
| 25 Batch-Operations & Smart-Filter | 🔲 | Frontend + Backend | +1500 |
| 26 Vergleichstool & Quality-Metrics | 🔲 | Full-Stack | +1800 |
| 27 Sync & Health-Check | 🔲 | Backend + Frontend | +1600 |
| 28 Dashboard-Widgets & Quick-Actions | 🔲 | Frontend | +2200 |
| 29 API-Key-Management & Export/Import | 🔲 | Full-Stack | +1800 |
| 30 Notification-Templates & Filter | 🔲 | Backend + Frontend | +1200 |
| 31 Deduplizierung & Cleanup | 🔲 | Backend + Frontend | +1400 |
| 32 Externe Tool-Integrationen | 🔲 | Backend + Migration | +2000 |
| **Gesamt Phase 3** | **🔲** | | **~15500** |

---

## Implementierungsreihenfolge (Phase 2)

Empfohlene Reihenfolge basierend auf Abhaengigkeiten:

```
Milestone 13 (Provider Plugin) ──┐
                                 ├──> Milestone 15 (Whisper — nutzt Plugin-System)
Milestone 14 (Translation) ─────┘

Milestone 16 (Media-Server) ─── unabhaengig, parallel zu 13/14 moeglich
Milestone 17 (Standalone) ───── unabhaengig, parallel zu 16 moeglich

Milestone 18 (Forced Subs) ─── nach 13 (Provider-Erweiterungen benoetigt)
Milestone 19 (Events/Hooks) ── nach 14+15 (Events fuer alle Backends)
Milestone 20 (i18n/Backup) ─── unabhaengig, jederzeit
Milestone 21 (Health/Perf) ─── nach 13-19 (dokumentiert finale Features)
Milestone 22 (v0.9.0-beta Release) ── nach allem
Milestone 23 (Performance/Scalability) ── optional, nach 22 oder parallel (alle Features optional)
```

### Empfohlene Waves:

**Wave 1 (Architektur-Refactoring):** Milestone 13 + 14 + 16 (parallel moeglich)
- Provider-Plugin-System, Translation-Abstraction, Media-Server-Abstraction
- Bereitet die Basis fuer alles Weitere

**Wave 2 (Neue Capabilities):** Milestone 15 + 17 + 18
- Whisper, Standalone-Modus, Forced-Subs
- Groesste neue Features, hoechster User-Impact

**Wave 3 (Customization + Polish):** Milestone 19 + 20
- Event-System, Hooks, Scoring, i18n, Backup
- Macht Sublarr zur anpassbaren Plattform

**Wave 4 (Release):** Milestone 21 + 22
- Performance, Dokumentation, Community-Launch

**Wave 5 (Scalability - Optional):** Milestone 23
- Database-Migration, Redis-Integration, Queue-System
- Fuer groessere Deployments und Production-Use-Cases
- Alle Features optional, System funktioniert weiterhin mit SQLite

---

## Phase 3: Advanced Features & UX (v2.1+)

### Empfohlene Waves (Phase 3):

**Wave 1 (Core UX):** Milestone 24 + 25 + 28
- Subtitle-Vorschau/Editor, Batch-Operations, Dashboard-Widgets
- Hoechster User-Impact, verbessert taegliche Nutzung

**Wave 2 (Quality Tools):** Milestone 26 + 27
- Vergleichstool, Sync, Health-Check
- Professionelle Tools fuer Qualitaetskontrolle

**Wave 3 (Management):** Milestone 29 + 30 + 31
- API-Key-Management, Notifications, Cleanup
- Bessere Verwaltung und Wartung

**Wave 4 (Integration):** Milestone 32
- Externe Tool-Integrationen
- Migration und Kompatibilitaet

---

## Vergleich mit Bazarr nach v1.1+

| Feature | Bazarr | Sublarr v1.0 | Sublarr v0.9.0-beta | Sublarr v1.1+ |
|---|---|---|---|---|
| Provider-Anzahl | ~20+ | 4 | 12+ Built-in + Plugin-System | 12+ Built-in + Plugin-System |
| Plugin-System | Nein (subliminal Fork) | Nein | Ja (Drop-in Python) | Ja (Drop-in Python) |
| Uebersetzung | Nein (explizit abgelehnt) | Ollama | 5+ Backends | 5+ Backends |
| Whisper/STT | Via Subgen-Provider | Nein | Integriert | Integriert |
| ASS-Handling | Buggy (zerstoert Styles) | First-Class | First-Class + Forced/Signs | First-Class + Forced/Signs |
| Media-Server | Jellyfin + Emby + Plex | Jellyfin + Emby | Jellyfin + Emby + Plex + Kodi | Jellyfin + Emby + Plex + Kodi |
| Standalone-Modus | Nein (Sonarr/Radarr Pflicht) | Nein | Ja | Ja |
| Forced Subs | Ja (mit Wanted-Spam) | Nein | Ja (ohne Spam) | Ja (ohne Spam) |
| Script-Hooks | Ja | Nein | Ja | Ja |
| Custom Scoring | Begrenzt | Nein | Voll konfigurierbar | Voll konfigurierbar |
| i18n | Nein (nur EN) | Nein | EN + DE | EN + DE |
| Backup/Restore | Nein | Nein | Ja | Ja |
| API-Docs | Nein | Nein | OpenAPI/Swagger | OpenAPI/Swagger |
| **Subtitle-Editor** | Nein | Nein | Nein | **Ja (Inline-Editor)** |
| **Subtitle-Vorschau** | Nein | Nein | Nein | **Ja (Browser-basiert)** |
| **Batch-Operations** | Begrenzt | Nein | Nein | **Ja (Vollstaendig)** |
| **Smart-Filter** | Basis | Nein | Nein | **Ja (Presets, Quick-Filter)** |
| **Vergleichstool** | Nein | Nein | Nein | **Ja (Side-by-Side)** |
| **Quality-Metrics** | Nein | Nein | Nein | **Ja (Detailliert)** |
| **Sync-Tool** | Nein | Nein | Nein | **Ja (Auto + Manual)** |
| **Health-Check** | Nein | Nein | Nein | **Ja (Auto-Detection)** |
| **Dashboard-Widgets** | Statisch | Statisch | Statisch | **Konfigurierbar** |
| **Quick-Actions** | Nein | Nein | Nein | **Ja (Keyboard-Shortcuts)** |
| **API-Key-Management** | Nein | Nein | Nein | **Ja (Zentral)** |
| **Deduplizierung** | Nein | Nein | Nein | **Ja (Auto-Detection)** |
| **Cleanup-Tools** | Nein | Nein | Nein | **Ja (Scheduled)** |
| **Bazarr-Migration** | - | Nein | Nein | **Ja (Vollstaendig)** |
| Anime-Fokus | Nachtraeglich | Kernfeature | Kernfeature + erweitert | Kernfeature + erweitert |

---

## Technische Grundlagen

### Provider-Plugin-Architektur (Milestone 13)

```python
# backend/providers/plugins/my_provider.py (Beispiel)
from providers.base import SubtitleProvider, VideoQuery, SubtitleResult

class MyProvider(SubtitleProvider):
    name = "my_provider"
    version = "1.0.0"
    author = "Community"
    description = "Mein Custom Provider"

    config_fields = [
        {"name": "api_key", "type": "password", "label": "API Key", "required": True},
        {"name": "timeout", "type": "number", "label": "Timeout (s)", "default": 30},
    ]

    def search(self, query: VideoQuery) -> list[SubtitleResult]:
        # Provider-Logik
        ...

    def download(self, result: SubtitleResult) -> bytes:
        # Download-Logik
        ...
```

### Translation-Backend-Architektur (Milestone 14)

```python
# backend/translation/deepl.py (Beispiel)
from translation import TranslationBackend

class DeepLBackend(TranslationBackend):
    name = "deepl"
    supports_glossary = True
    supports_custom_prompt = False

    config_fields = [
        {"name": "api_key", "type": "password", "label": "API Key", "required": True},
        {"name": "pro_account", "type": "boolean", "label": "Pro Account", "default": False},
    ]

    def translate_batch(self, lines, source_lang, target_lang, **kwargs):
        # DeepL API Call
        ...

    def health_check(self):
        # API erreichbar?
        ...
```

### Warum kein subliminal als Dependency?

Sublarr nutzt ein eigenes leichtgewichtiges Provider-System statt subliminal:
- subliminal bringt ~15 transitive Dependencies (stevedore, dogpile.cache, enzyme, etc.)
- Bazarrs subliminal_patch ist eine schwer wartbare Fork mit Metaclass-Magic
- Sublarrs Provider-System: Saubere Architektur, Plugin-faehig ab v2.0
- Das Plugin-System in Milestone 13 macht Community-Provider trivial hinzufuegbar

---

## Phase 3: Advanced Features & UX (v2.1+)

> **Leitmotiv:** Erweiterte UX-Features, professionelle Tools und Integrationen.
> Fokus auf Benutzerfreundlichkeit, Qualitaetskontrolle und erweiterte Automatisierung.

---

## Milestone 24: Subtitle-Vorschau & Editor

**Ziel:** Interaktive Subtitle-Vorschau und Inline-Editor direkt in der UI.
Ermoeglicht schnelle Korrekturen, Qualitaetskontrolle und manuelle Anpassungen ohne externe Tools.

**Motivation (Community):**
- Aktuell muessen User externe Tools (Aegisub, SubtitleEdit) nutzen fuer manuelle Korrekturen
- Schnelle Fixes erfordern Download → Edit → Upload — umstaendlich
- Qualitaetskontrolle vor Download waere wertvoll
- Glossar-Tests direkt in der UI

### Subtitle-Vorschau

- [ ] **Vorschau-Komponente** (`frontend/src/components/subtitle/SubtitlePreview.tsx`):
  - ASS/SRT Parser fuer Browser (WebAssembly oder JavaScript)
  - Zeilenweise Anzeige mit Timestamps
  - Syntax-Highlighting fuer ASS-Tags (`{\an8}`, `{\pos()}`, etc.)
  - Scrollbare Timeline-Ansicht
  - Zeilen-Nummerierung
  - Format-Umschaltung: ASS ↔ SRT (nur Anzeige, keine Konvertierung)

- [ ] **Vorschau-Integration:**
  - Wanted-Page: "Preview" Button bei Search-Results → Modal mit Vorschau
  - History-Page: Vorschau-Link pro Download
  - SeriesDetail: Vorschau pro Episode/Film
  - Library-Page: Quick-Preview auf Hover (optional)
  - Backend-API: `GET /api/v1/subtitles/preview?file_path=...` — Subtitle-Inhalt als JSON

- [ ] **Vorschau-Features:**
  - Zeilen-Filter: Nur Dialog, Nur Signs, Alle
  - Suche innerhalb der Subtitles (Text-Suche)
  - Highlighting von Glossar-Eintraegen
  - Encoding-Detection (UTF-8, Latin-1, etc.)
  - Zeilen-Anzahl, Gesamt-Dauer, Format-Info

### Subtitle-Editor

- [ ] **Editor-Komponente** (`frontend/src/components/subtitle/SubtitleEditor.tsx`):
  - Code-Editor basierend auf Monaco Editor oder CodeMirror
  - ASS/SRT Syntax-Highlighting
  - Zeilen-Nummerierung
  - Auto-Formatierung (optional)
  - Undo/Redo Funktionalitaet
  - Validierung: Syntax-Checks, Timestamp-Format, Encoding

- [ ] **Editor-Integration:**
  - SeriesDetail: "Edit Subtitle" Button pro Episode/Film
  - History-Page: "Edit" Link pro Download
  - Wanted-Page: Edit nach Download moeglich
  - Backend-API: `PUT /api/v1/subtitles/edit` — Aenderungen speichern
  - Backup: Original wird als `.backup` gespeichert vor Edit

- [ ] **Editor-Features:**
  - Live-Preview: Aenderungen sofort in Vorschau sichtbar
  - Diff-View: Original vs. Editiert (Side-by-Side)
  - Batch-Edit: Mehrere Zeilen gleichzeitig bearbeiten
  - Find & Replace mit Regex-Support
  - Timestamp-Adjustment: Alle Timestamps um X ms verschieben
  - Style-Tag-Helper: GUI fuer haeufige ASS-Tags

- [ ] **Editor-Validierung:**
  - Syntax-Errors werden rot markiert
  - Timestamp-Format-Validierung
  - Warnung bei ueberlappenden Timestamps
  - Encoding-Warnung bei nicht-UTF-8 Zeichen
  - Zeilen-Laenge-Warnung (ueber 42 Zeichen)

**Neue Dateien:** 3 (SubtitlePreview.tsx, SubtitleEditor.tsx, subtitle_parser.js) | **Geschaetzte Zeilen:** +2000

**Abhaengigkeiten:** Keine

---

## Milestone 25: Batch-Operations & Smart-Filter

**Ziel:** Effiziente Bulk-Operationen und erweiterte Filter-Optionen fuer alle Listen.
Zeitersparnis bei der Verwaltung grosser Libraries.

**Motivation (Community):**
- Groesse Libraries erfordern Bulk-Operationen
- Aktuelle Filter sind begrenzt
- Gespeicherte Filter-Presets fehlen
- Quick-Filter-Buttons waeren hilfreich

### Batch-Operations

- [ ] **Library Batch-Operations:**
  - Multi-Select: Checkboxen in Library-Liste
  - Select All / Deselect All
  - Bulk-Actions Toolbar (erscheint bei Selection):
    - Bulk Language-Profile-Zuweisung
    - Bulk Glossar-Import
    - Bulk Retranslation (mit Filter: nur bestimmte Sprachen)
    - Bulk Wanted-Scan
    - Bulk Provider-Suche
  - Progress-Indicator fuer Batch-Operations
  - Undo-Option (wenn moeglich)

- [ ] **Wanted Batch-Operations:**
  - Multi-Select in Wanted-Liste
  - Bulk-Search: Alle selektierten Items durchsuchen
  - Bulk-Process: Alle selektierten Items downloaden + uebersetzen
  - Bulk-Status-Update: Status auf "ignored" setzen
  - Bulk-Delete: Items aus Wanted-Liste entfernen

- [ ] **History Batch-Operations:**
  - Multi-Select in History-Liste
  - Bulk-Blacklist: Mehrere Downloads gleichzeitig blacklisten
  - Bulk-Delete: History-Eintraege loeschen
  - Bulk-Export: Mehrere Subtitles als ZIP exportieren

### Smart-Filter

- [ ] **Erweiterte Filter-Optionen:**
  - Library: Filter nach Release-Group, Qualitaet, Format, Datum
  - Wanted: Filter nach Release-Group, Provider, Score-Range, Datum
  - History: Filter nach Provider, Format, Sprache, Erfolgs-Status
  - Multi-Filter: Mehrere Filter gleichzeitig kombinieren (AND/OR Logik)

- [ ] **Gespeicherte Filter-Presets:**
  - Filter-Speicherung: User kann Filter-Kombinationen speichern
  - Preset-Management: Presets benennen, loeschen, bearbeiten
  - Quick-Access: Presets in Dropdown-Menue
  - Default-Presets: "Nur heute hinzugefuegt", "Nur fehlgeschlagen", "Nur ASS", etc.

- [ ] **Quick-Filter-Buttons:**
  - Library: "Nur fehlende Subs", "Nur Upgradeable", "Nur heute gedownloadet"
  - Wanted: "Nur heute hinzugefuegt", "Nur fehlgeschlagen", "Nur ASS gesucht"
  - History: "Nur heute", "Nur diese Woche", "Nur ASS", "Nur erfolgreich"
  - Buttons sind konfigurierbar in Settings

- [ ] **Global-Search:**
  - Suchleiste im Header (ueber alle Seiten)
  - Suche in: Serien/Film-Titel, Episode-Namen, Provider-Namen, Glossar-Eintraegen
  - Fuzzy-Search: Tippfehler-Toleranz
  - Suchergebnisse: Gruppiert nach Typ (Series, Movie, History, etc.)
  - Keyboard-Shortcut: `Ctrl+K` oder `Cmd+K` fuer Quick-Search

**Neue Dateien:** 2 (BatchOperations.tsx, SmartFilter.tsx) | **Geschaetzte Zeilen:** +1500

**Abhaengigkeiten:** Keine

---

## Milestone 26: Subtitle-Vergleichstool & Quality-Metrics

**Ziel:** Side-by-Side-Vergleich mehrerer Subtitle-Versionen und detaillierte Qualitaets-Metriken.
Hilft bei Upgrade-Entscheidungen und Qualitaetskontrolle.

**Motivation (Community):**
- Upgrade-Entscheidungen sind schwer ohne Vergleich
- Qualitaets-Metriken fehlen aktuell
- Score allein reicht nicht fuer Entscheidung
- Vergleich mehrerer Provider-Results waere wertvoll

### Subtitle-Vergleichstool

- [ ] **Vergleichs-Komponente** (`frontend/src/components/subtitle/SubtitleCompare.tsx`):
  - Side-by-Side oder Overlay-Ansicht
  - Zeilenweise Synchronisation (scrollt beide Ansichten zusammen)
  - Diff-Highlighting: Unterschiede farblich markieren
  - Timestamp-Vergleich: Unterschiede in Timing anzeigen
  - Format-Vergleich: ASS vs SRT, Encoding, etc.

- [ ] **Vergleichs-Integration:**
  - Wanted-Page: "Compare" Button bei mehreren Search-Results
  - History-Page: "Compare with Previous" Link
  - SeriesDetail: Vergleich zwischen Versionen
  - Backend-API: `POST /api/v1/subtitles/compare` — Zwei Dateien vergleichen

- [ ] **Vergleichs-Features:**
  - Multi-Compare: Bis zu 4 Versionen gleichzeitig vergleichen
  - Score-Anzeige: Score pro Version prominent anzeigen
  - Provider-Info: Welcher Provider, wann gedownloadet
  - Download-Button: Beste Version direkt downloaden
  - Export: Vergleich als HTML/PDF exportieren

### Quality-Metrics Dashboard

- [ ] **Per-Serie Quality-Metrics:**
  - SeriesDetail: Neuer Tab "Quality Metrics"
  - Metriken pro Serie:
    - Durchschnittliche Score-Entwicklung ueber Zeit (Chart)
    - Provider-Erfolgsrate pro Serie (welcher Provider funktioniert am besten)
    - Format-Verteilung (ASS vs SRT Anteil)
    - Upgrade-History (wie oft wurde upgraded, durchschnittliche Verbesserung)
    - Uebersetzungsqualitaet (Halluzination-Rate, Length-Ratio-Trends)

- [ ] **Global Quality-Metrics:**
  - Dashboard: Neues Widget "Quality Overview"
  - Top-Serien nach Score sortiert
  - Serien mit haeufigen Upgrades (moegliche Qualitaetsprobleme)
  - Provider-Performance-Ranking (welcher Provider liefert beste Scores)

- [ ] **Quality-Warnings:**
  - Automatische Erkennung von Qualitaetsproblemen:
    - Niedrige Scores (< 200) bei mehreren Episoden
    - Hauefige Upgrades (moeglicher Provider-Problem)
    - Uebersetzungsfehler (hohe Halluzination-Rate)
  - Warnungen in Dashboard und SeriesDetail
  - Action-Buttons: "Retranslate", "Search Better Provider"

**Neue Dateien:** 3 (SubtitleCompare.tsx, QualityMetrics.tsx, compare_utils.py) | **Geschaetzte Zeilen:** +1800

**Abhaengigkeiten:** Milestone 24 (nutzt Subtitle-Parser)

---

## Milestone 27: Subtitle-Sync & Health-Check Tools

**Ziel:** Automatische Timing-Korrekturen und Health-Check-System fuer Subtitles.
Behebt haeufige Probleme automatisch.

**Motivation (Community):**
- Leicht desynchte Subtitles sind haeufig
- Manuelle Timing-Korrektur ist zeitaufwaendig
- Qualitaetsprobleme werden oft zu spaet erkannt
- Automatische Fixes waeren wertvoll

### Subtitle-Sync-Tool

- [ ] **Sync-Engine** (`backend/subtitle_sync.py`):
  - Automatische Timing-Korrektur bei leichten Verschiebungen
  - Algorithmus: Audio-Waveform-Analyse oder Reference-Subtitle-Vergleich
  - Offset-Anpassung: Alle Timestamps um X ms verschieben
  - Speed-Multiplikator: Timestamps um Faktor anpassen (z.B. 1.05x)
  - Frame-Rate-Konvertierung: 23.976 → 25 fps, etc.

- [ ] **Sync-UI:**
  - SeriesDetail: "Sync Subtitle" Button pro Episode/Film
  - Manuelle Offset-Eingabe: User kann Offset in ms eingeben
  - Live-Preview: Aenderungen sofort in Vorschau sichtbar
  - Auto-Detect: Button "Auto-Detect Offset" (nutzt Reference-Subtitle)
  - Batch-Sync: Mehrere Episoden gleichzeitig syncen

- [ ] **Sync-Features:**
  - Reference-Subtitle: Andere Sprache als Referenz nutzen
  - Partial-Sync: Nur bestimmte Zeilen syncen (z.B. nur erste 10 Minuten)
  - Undo: Original wiederherstellen
  - Validation: Warnung bei unplausiblen Timestamps

### Subtitle-Health-Check

- [ ] **Health-Check-Engine** (`backend/subtitle_health.py`):
  - Automatische Erkennung haeufiger Probleme:
    - Doppelte Zeilen
    - Falsche Encoding (z.B. Latin-1 statt UTF-8)
    - Timing-Probleme (ueberlappende Timestamps, negative Dauer)
    - Leere Zeilen
    - Zu lange Zeilen (> 42 Zeichen)
    - Fehlende Style-Tags (bei ASS)
    - Falsche Frame-Rate

- [ ] **Health-Check-UI:**
  - SeriesDetail: "Health Check" Button → Modal mit Problemen
  - Library-Page: Health-Status-Badge pro Episode/Film
  - Dashboard: Widget "Subtitle Health Overview"
  - Backend-API: `GET /api/v1/subtitles/health?file_path=...` — Probleme als JSON

- [ ] **Auto-Fix-Optionen:**
  - Pro Problem: Auto-Fix Button
  - Fix-Optionen:
    - Doppelte Zeilen entfernen
    - Encoding korrigieren
    - Leere Zeilen entfernen
    - Zu lange Zeilen umbrechen
    - Timing-Probleme korrigieren
  - Preview vor Fix: User sieht Aenderungen vor Anwendung
  - Batch-Fix: Alle Probleme einer Serie gleichzeitig beheben

- [ ] **Health-Metrics:**
  - DB-Tracking: Health-Score pro Subtitle (0-100)
  - Trend-Analyse: Verbesserung/Verschlechterung ueber Zeit
  - Provider-Qualitaet: Welcher Provider liefert gesuendere Subtitles
  - Dashboard: Top-Probleme (welche Probleme treten am haeufigsten auf)

**Neue Dateien:** 2 (subtitle_sync.py, subtitle_health.py) | **Geschaetzte Zeilen:** +1600

**Abhaengigkeiten:** Milestone 24 (nutzt Subtitle-Parser)

---

## Milestone 28: Erweiterte Dashboard-Widgets & Quick-Actions

**Ziel:** Konfigurierbare Dashboard-Widgets und Quick-Actions Toolbar.
Personalisierbare UX fuer verschiedene Use-Cases.

**Motivation (Community):**
- Aktuelles Dashboard ist statisch
- User haben verschiedene Prioritaeten
- Quick-Actions fehlen
- Keyboard-Shortcuts waeren hilfreich

### Erweiterte Dashboard-Widgets

- [ ] **Widget-System:**
  - Widget-Library: Vordefinierte Widgets
  - Widget-Types:
    - Stat-Card (Zahl + Trend)
    - Chart (Line, Bar, Pie, Donut)
    - Table (z.B. Top-Serien, Recent Downloads)
    - Progress-Bar (z.B. Batch-Progress)
    - Custom-HTML (fuer erweiterte Visualisierungen)

- [ ] **Widget-Konfiguration:**
  - Drag-and-Drop Layout: Widgets per Drag-and-Drop anordnen
  - Widget-Size: Small, Medium, Large, Full-Width
  - Widget-Settings: Pro Widget konfigurierbare Optionen
  - Widget-Visibility: Widgets ein/ausblenden
  - Preset-Layouts: "Default", "Minimal", "Detailed", "Anime-Focused"

- [ ] **Vordefinierte Widgets:**
  - Translation-Today (mit Vergleich zu gestern)
  - Provider-Performance (Bar Chart)
  - Wanted-Items-Trend (Line Chart)
  - Top-Serien (nach Downloads)
  - Recent-Activity (Timeline)
  - System-Health (CPU, Memory, Disk)
  - Queue-Status (Pending, Running, Completed)
  - Quality-Score-Distribution (Histogram)

- [ ] **Widget-Export:**
  - Dashboard als Bild exportieren (PNG)
  - Dashboard-Layout als JSON exportieren/importieren
  - Sharing: Dashboard-Layout mit anderen Usern teilen

### Quick-Actions Toolbar

- [ ] **Quick-Actions-Komponente:**
  - Floating Action Button (FAB) oder Toolbar im Header
  - Kontextuelle Actions: Actions aendern sich je nach aktueller Seite
  - Icon-basierte Buttons mit Tooltips
  - Keyboard-Shortcuts: Jede Action hat Shortcut

- [ ] **Global Quick-Actions:**
  - "Search All Wanted" (Shortcut: `Ctrl+S`)
  - "Refresh Library" (Shortcut: `Ctrl+R`)
  - "New Language Profile" (Shortcut: `Ctrl+N`)
  - "Open Settings" (Shortcut: `Ctrl+,`)
  - "Quick Search" (Shortcut: `Ctrl+K`)

- [ ] **Context-Specific Actions:**
  - Library-Page: "Bulk Assign Profile", "Bulk Retranslate"
  - Wanted-Page: "Search All", "Process All", "Clear Failed"
  - History-Page: "Export Selected", "Bulk Blacklist"
  - SeriesDetail: "Retranslate Series", "Sync All Episodes"

- [ ] **Quick-Actions-Konfiguration:**
  - Settings: Quick-Actions anpassen (hinzufuegen/entfernen)
  - Shortcut-Konfiguration: User kann Shortcuts aendern
  - Action-Gruppen: Actions in Gruppen organisieren
  - Visibility: Actions ein/ausblenden

**Neue Dateien:** 3 (DashboardWidgets.tsx, QuickActions.tsx, widget_system.ts) | **Geschaetzte Zeilen:** +2200

**Abhaengigkeiten:** Keine

---

## Milestone 29: API-Key-Management & Export/Import-Erweiterungen

**Ziel:** Zentrale API-Key-Verwaltung und erweiterte Export/Import-Funktionen.
Bessere Verwaltung von Credentials und Daten-Migration.

**Motivation (Community):**
- API-Keys sind ueber verschiedene Settings verteilt
- Rotation-Reminder fehlen
- Export/Import ist aktuell begrenzt
- Migration von anderen Tools (Bazarr) waere hilfreich

### API-Key-Management

- [ ] **Zentrale Key-Verwaltung:**
  - Neue Settings-Seite "API Keys" oder Tab
  - Liste aller API-Keys: Provider, Translation-Backends, Media-Server, etc.
  - Key-Info: Name, Typ, Status (valid/invalid), letzte Nutzung
  - Key-Maskierung: Keys werden maskiert angezeigt (`****-****-****-abcd`)
  - Show/Hide Toggle: Original-Key anzeigen (mit Bestaetigung)

- [ ] **Key-Features:**
  - Key-Test: "Test" Button pro Key → Validierung
  - Key-Rotation: "Rotate" Button → Neuen Key eingeben, alten loeschen
  - Rotation-Reminder: Warnung wenn Key bald ablaeuft (wenn bekannt)
  - Key-Export: Alle Keys als verschluesseltes JSON exportieren
  - Key-Import: Keys aus Export importieren

- [ ] **Key-Statistiken:**
  - Nutzungs-Statistiken pro Key (wie oft verwendet, letzte Nutzung)
  - Fehler-Rate pro Key (wenn Key invalid ist)
  - Rate-Limit-Status (wenn Provider das anzeigt)

### Export/Import-Erweiterungen

- [ ] **Erweiterte Export-Funktionen:**
  - Settings → "Export" Tab
  - Export-Optionen:
    - Language-Profiles (JSON)
    - Glossare (CSV/JSON)
    - Prompt-Presets (JSON)
    - Blacklist (CSV/JSON)
    - History (CSV/JSON, mit/ohne Dateien)
    - Config (JSON)
    - Alles zusammen (ZIP)
  - Export-Filter: Nur bestimmte Serien, Zeitraum, etc.

- [ ] **Import-Funktionen:**
  - Settings → "Import" Tab
  - Import-Quellen:
    - Sublarr-Export (ZIP/JSON)
    - Bazarr-Config (Migration)
    - CSV-Files (fuer Glossare, Blacklist)
  - Import-Preview: Was wird importiert, Konflikte anzeigen
  - Merge-Strategie: Ueberschreiben, Merge, Skip

- [ ] **Bazarr-Migration-Tool:**
  - Spezieller Import-Wizard fuer Bazarr-Migration
  - Liest Bazarr-Config-Dateien
  - Migriert: Language-Profiles, Provider-Settings, Blacklist
  - Mapping: Bazarr-Provider → Sublarr-Provider
  - Validierung: Was konnte migriert werden, was nicht

- [ ] **Scheduled Exports:**
  - Automatische Exports: Taeglich/Woechentlich
  - Export-Ziel: Lokaler Ordner oder Cloud-Storage (S3, etc.)
  - Export-Rotation: Alte Exports automatisch loeschen
  - Notification: Benachrichtigung bei erfolgreichem Export

**Neue Dateien:** 3 (ApiKeyManagement.tsx, ExportImport.tsx, bazarr_migrator.py) | **Geschaetzte Zeilen:** +1800

**Abhaengigkeiten:** Keine

---

## Milestone 30: Notification-Templates & Advanced-Filter

**Ziel:** Anpassbare Notification-Templates und erweiterte Filter-Optionen.
Flexiblere Benachrichtigungen fuer verschiedene Use-Cases.

**Motivation (Community):**
- Aktuelle Notifications sind statisch
- User wollen verschiedene Notification-Formate
- Quiet-Hours fehlen
- Filter fuer welche Events benachrichtigen

### Notification-Templates

- [ ] **Template-System:**
  - Settings → "Notifications" Tab erweitern
  - Template-Editor: Custom-Templates erstellen/bearbeiten
  - Template-Variablen: `{event}`, `{series}`, `{episode}`, `{provider}`, `{language}`, etc.
  - Template-Types: Text, Markdown, HTML
  - Preview: Template-Vorschau mit Beispiel-Daten

- [ ] **Vordefinierte Templates:**
  - "Simple" (nur Event + Serie)
  - "Detailed" (alle Informationen)
  - "Anime-Focused" (mit AniDB-Links)
  - "Minimal" (nur Icon + Text)
  - User kann eigene Templates erstellen

- [ ] **Template-Zuweisung:**
  - Pro Notification-Service: Eigenes Template
  - Pro Event-Type: Eigenes Template (optional)
  - Fallback: Default-Template wenn kein spezifisches Template

### Advanced Notification-Filter

- [ ] **Event-Filter:**
  - Pro Notification-Service: Welche Events benachrichtigen
  - Filter-Optionen:
    - Nur Fehler
    - Nur Upgrades
    - Nur Downloads
    - Nur Batch-Completions
    - Custom: User waehlt Events aus Liste
  - Filter-Logik: Include/Exclude bestimmte Events

- [ ] **Content-Filter:**
  - Filter nach Serie/Film (nur bestimmte Serien benachrichtigen)
  - Filter nach Sprache (nur bestimmte Sprachen)
  - Filter nach Provider (nur bestimmte Provider)
  - Filter nach Format (nur ASS, nur SRT)

- [ ] **Quiet-Hours:**
  - Zeitfenster definieren: Keine Notifications zwischen X und Y Uhr
  - Zeitzone-Konfiguration
  - Ausnahme: Kritische Fehler auch in Quiet-Hours
  - Quiet-Hours pro Notification-Service konfigurierbar

- [ ] **Notification-History:**
  - Neue Seite "Notifications" im System-Bereich
  - Historie aller gesendeten Notifications
  - Filter: Nach Service, Event, Datum
  - Re-Send: Notification erneut senden
  - Export: Notification-History als CSV

**Neue Dateien:** 2 (NotificationTemplates.tsx, NotificationHistory.tsx) | **Geschaetzte Zeilen:** +1200

**Abhaengigkeiten:** Milestone 11 (baut auf Notification-System auf)

---

## Milestone 31: Subtitle-Deduplizierung & Cleanup-Tools

**Ziel:** Automatische Erkennung und Bereinigung von Duplikaten.
Optimiert Speicherplatz und reduziert Verwirrung.

**Motivation (Community):**
- Doppelte Downloads kommen vor
- Speicherplatz-Verschwendung
- Verwirrung bei mehreren Versionen
- Cleanup-Tools fehlen

### Subtitle-Deduplizierung

- [ ] **Deduplizierungs-Engine** (`backend/deduplicator.py`):
  - Content-Hash-basierte Erkennung: Gleicher Inhalt = Duplikat
  - Dateiname-Vergleich: Aehnliche Dateinamen als potenzielle Duplikate
  - Metadata-Vergleich: Gleiche Serie, Episode, Sprache, Format
  - Scoring: Wahrscheinlichkeit dass es Duplikat ist (0-100%)

- [ ] **Deduplizierungs-UI:**
  - Settings → "Maintenance" Tab
  - "Find Duplicates" Button → Scan starten
  - Duplikat-Liste: Gruppiert nach Content-Hash
  - Pro Gruppe: Welche Datei behalten? (User waehlt)
  - Batch-Delete: Alle Duplikate auf einmal loeschen
  - Preview: Unterschiede zwischen Dateien anzeigen (wenn vorhanden)

- [ ] **Auto-Deduplizierung:**
  - Option: Automatisch Duplikate beim Download erkennen
  - Wenn Duplikat erkannt: Warnung anzeigen, Download abbrechen
  - Oder: Automatisch beste Version behalten (nach Score)

### Cleanup-Tools

- [ ] **Cleanup-Dashboard:**
  - Settings → "Maintenance" Tab erweitern
  - Cleanup-Optionen:
    - Loesche Subtitles ohne zugehoerige Medien-Datei
    - Loesche Subtitles aelter als X Tage (ohne Medien-Datei)
    - Loesche Backup-Dateien (`.backup`) aelter als X Tage
    - Loesche temporaere Dateien
    - Bereinige Provider-Cache (alte Eintraege)
    - Bereinige History (alte Eintraege)

- [ ] **Cleanup-Preview:**
  - Vor Cleanup: Preview was geloescht wird
  - Statistiken: Wie viele Dateien, Gesamt-Groesse
  - Filter: User kann bestimmte Dateien ausschliessen
  - Undo: Cleanup kann rueckgaengig gemacht werden (wenn moeglich)

- [ ] **Scheduled Cleanup:**
  - Automatische Cleanups: Taeglich/Woechentlich
  - Cleanup-Regeln konfigurierbar
  - Notification: Benachrichtigung nach Cleanup mit Statistiken

- [ ] **Disk-Space-Analyse:**
  - Dashboard-Widget: Disk-Usage pro Kategorie
  - Kategorien: Subtitles, Backups, Cache, DB, Logs
  - Trends: Disk-Usage ueber Zeit
  - Warnung: Wenn Disk-Space knapp wird

**Neue Dateien:** 2 (deduplicator.py, CleanupTools.tsx) | **Geschaetzte Zeilen:** +1400

**Abhaengigkeiten:** Keine

---

## Milestone 32: Externe Tool-Integrationen & Migration-Tools

**Ziel:** Integration mit externen Tools und Migration von anderen Subtitle-Managern.
Ermoeglicht nahtlose Migration und erweiterte Funktionalitaet.

**Motivation (Community):**
- Migration von Bazarr ist aktuell manuell
- Integration mit anderen Tools fehlt
- Health-Checks fuer externe Services waeren hilfreich
- Export-Formate fuer andere Tools

### Bazarr-Integration & Migration

- [ ] **Bazarr-Migration-Tool** (erweitert Milestone 29):
  - Vollstaendige Migration: Config, Language-Profiles, Blacklist, History
  - Bazarr-DB-Reader: Liest Bazarr SQLite-Datenbank direkt
  - Mapping-Tabelle: Bazarr-Provider → Sublarr-Provider
  - Validierung: Was konnte migriert werden, was nicht
  - Migration-Report: Detaillierter Report nach Migration

- [ ] **Bazarr-Health-Check:**
  - Integration-Check: Ist Bazarr noch aktiv?
  - Vergleich: Bazarr vs. Sublarr Statistiken
  - Dual-Run-Modus: Sublarr und Bazarr parallel laufen lassen (Migration-Phase)

### Externe Tool-Integrationen

- [ ] **Plex-Kompatibilitaets-Check:**
  - Plex-Integration-Test: Funktioniert Subtitle-Refresh?
  - Plex-Subtitle-Format-Check: Unterstuetzt Plex ASS-Format?
  - Plex-Path-Mapping-Validation: Sind Pfade korrekt gemappt?

- [ ] **Sonarr/Radarr Health-Check:**
  - Erweiterte Health-Checks: Sind Sonarr/Radarr erreichbar?
  - API-Version-Check: Unterstuetzte API-Version?
  - Path-Mapping-Validation: Funktioniert Path-Mapping?
  - Webhook-Test: Funktioniert Webhook-Empfang?

- [ ] **Jellyfin/Emby Health-Check:**
  - Library-Refresh-Test: Funktioniert Refresh?
  - Item-Lookup-Test: Kann Sublarr Items finden?
  - API-Version-Check: Unterstuetzte API-Version?

### Export-Formate fuer andere Tools

- [ ] **Export-Formate:**
  - Bazarr-Format: Export als Bazarr-kompatible Config
  - Plex-Format: Subtitles im Plex-Format exportieren
  - Kodi-Format: Subtitles im Kodi-Format exportieren
  - Generic: Generische Formate (SRT, ASS, VTT)

- [ ] **Import-Formate:**
  - Bazarr-Config-Import (siehe Milestone 29)
  - Subtitle-Edit-Format: Import von Subtitle-Edit-Projekten
  - Aegisub-Format: Import von Aegisub-Projekten (wenn moeglich)

**Neue Dateien:** 3 (bazarr_migrator.py, ExternalToolIntegration.tsx, health_checker.py) | **Geschaetzte Zeilen:** +2000

**Abhaengigkeiten:** Milestone 16 (Media-Server Integration), Milestone 29 (Export/Import)

---

## Geschaetzter Aufwand (Phase 3)

| Milestone | Status | Schwerpunkt | Geschaetzte Zeilen |
|---|---|---|---|
| 24 Subtitle-Vorschau & Editor | 🔲 | Frontend (Editor) | +2000 |
| 25 Batch-Operations & Smart-Filter | 🔲 | Frontend + Backend | +1500 |
| 26 Vergleichstool & Quality-Metrics | 🔲 | Full-Stack | +1800 |
| 27 Sync & Health-Check | 🔲 | Backend + Frontend | +1600 |
| 28 Dashboard-Widgets & Quick-Actions | 🔲 | Frontend | +2200 |
| 29 API-Key-Management & Export/Import | 🔲 | Full-Stack | +1800 |
| 30 Notification-Templates & Filter | 🔲 | Backend + Frontend | +1200 |
| 31 Deduplizierung & Cleanup | 🔲 | Backend + Frontend | +1400 |
| 32 Externe Tool-Integrationen | 🔲 | Backend + Migration | +2000 |
| **Gesamt Phase 3** | **🔲** | | **~15500** |

---

## Implementierungsreihenfolge (Phase 3)

Empfohlene Reihenfolge basierend auf Abhaengigkeiten:

```
Milestone 24 (Vorschau/Editor) ──┐
                                 ├──> Milestone 26 (Vergleichstool nutzt Parser)
Milestone 25 (Batch/Filter) ────┼──> Milestone 28 (Widgets unabhaengig)
                                 │
Milestone 27 (Sync/Health) ──────┘
Milestone 29 (API-Keys/Export) ── unabhaengig
Milestone 30 (Notifications) ──── nach Milestone 11
Milestone 31 (Deduplizierung) ─── unabhaengig
Milestone 32 (Integrationen) ──── nach Milestone 16, 29
```

### Empfohlene Waves (Phase 3):

**Wave 1 (Core UX):** Milestone 24 + 25 + 28
- Vorschau/Editor, Batch-Operations, Dashboard-Widgets
- Hoechster User-Impact, verbessert taegliche Nutzung

**Wave 2 (Quality Tools):** Milestone 26 + 27
- Vergleichstool, Sync, Health-Check
- Professionelle Tools fuer Qualitaetskontrolle

**Wave 3 (Management):** Milestone 29 + 30 + 31
- API-Key-Management, Notifications, Cleanup
- Bessere Verwaltung und Wartung

**Wave 4 (Integration):** Milestone 32
- Externe Tool-Integrationen
- Migration und Kompatibilitaet

---

## Versions-Überblick

### Phase 1: Foundation
- **v1.0.0-beta** ✅ (2026-02-14) — Foundation abgeschlossen

### Phase 2: Open Platform
- **v0.2.0-beta** 🔲 — Plugin-System, Translation-Backend, Whisper (Milestone 13-15)
- **v0.3.0-beta** 🔲 — Media-Server, Standalone, Forced-Subs (Milestone 16-18)
- **v0.4.0-beta** 🔲 — Events/Hooks, i18n, OpenAPI (Milestone 19-21)
- **v0.5.0-beta** 🔲 — Performance-Optimierungen (Milestone 23)
- **v0.9.0-beta** 🔲 — Stabilisierung, alle Phase 2 Features (Milestone 22)
- **v0.9.1, v0.9.2, ...** 🔲 — Bugfixes und weitere Stabilisierung
- **v1.0.0** 🔲 — Final Release (nach ausreichendem Testing)

### Phase 3: Advanced Features & UX
- **v1.1.0-beta** 🔲 — Advanced Features (Milestone 24-32)
- **v1.2.0, v1.3.0, ...** 🔲 — Weitere Feature-Releases
- **v2.0.0** 🔲 — Nur bei Breaking Changes
