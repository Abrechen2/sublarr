# Sublarr — Standalone Subtitle Manager & Translator (*arr-Style)

> **Teil des DIYHaus Hub** — Open-Source Anime/Media Untertitel-Manager mit LLM-Uebersetzung

## Zweck

Eigenstaendiger Subtitle-Manager fuer Anime/Media — ein verbesserter Bazarr-Klon mit
integrierter LLM-Uebersetzung via Ollama. Durchsucht Subtitle-Provider direkt (ohne Bazarr),
downloadt die besten Untertitel (ASS bevorzugt) und uebersetzt sie automatisch.

Multi-Language-Support (konfigurierbare Quell- und Zielsprache), ASS und SRT Formate.
Arbeitet mit dem *arr-Oekosystem zusammen: Sonarr, Radarr, Jellyfin/Emby.

**Primaerziel:** Zielsprache ASS-Untertitel fuer jede Anime-Episode — ohne Bazarr.

## Projektziel: Bazarr ersetzen

Sublarr entwickelt sich vom reinen Uebersetzer zum vollstaendigen Bazarr-Ersatz:

- **Phase 1 (erledigt):** Eigenes Provider-System (OpenSubtitles, Jimaku, AnimeTosho)
- **Phase 2 (erledigt):** Eigenstaendiges Wanted-System (fehlende Subs selbst erkennen)
- **Phase 3 (erledigt):** Such- und Download-Workflow (End-to-End ohne Bazarr)
- **Phase 4 (erledigt):** Provider-UI (Credentials, Prioritaeten, Test im Frontend)
- **Phase 5 (erledigt):** Upgrade-System + Automatisierung (SRT→ASS, Scheduler)
- **Phase 6 (erledigt):** Erweiterte Provider (SubDL), Language-Profiles, Bazarr entfernt

### Vorteile gegenueber Bazarr

- **ASS-first:** ASS-Format bekommt +50 Scoring-Bonus, Bazarr behandelt ASS als Nebenformat
- **Download + Uebersetzung in einer Pipeline:** Sub runterladen → direkt uebersetzen
- **Ein Container weniger** im Stack (kein separates Bazarr noetig)
- **LLM-Uebersetzung integriert** — das hat Bazarr gar nicht

### Lizenz-Kompatibilitaet

| Projekt | Lizenz | Kompatibel |
|---|---|---|
| Bazarr | GPL-3.0 | Ja — identisch mit Sublarr |
| subliminal | MIT | Ja — permissiver |
| Sublarr | GPL-3.0 | Basis |

Code aus Bazarr darf direkt kopiert/adaptiert werden (gleiche Lizenz).

---

## *arr-API Integrationen

| Service | Auth-Header | Zweck |
|---|---|---|
| Sonarr (v3) | `X-Api-Key` | Serien/Episoden-Liste, File-Paths, Webhooks (OnDownload) |
| Radarr (v3) | `X-Api-Key` | Film-Liste, File-Paths, Webhooks (OnDownload) |
| Jellyfin/Emby | `X-MediaBrowser-Token` | Library-Refresh nach neuen Untertiteln |

## Subtitle Provider System

Eigenstaendiges Provider-System ersetzt Bazarr fuer Subtitle-Sourcing.

### Provider-Architektur

```
VideoQuery → ProviderManager.search()
              ├── AnimeTosho    (kein Auth, Fansub ASS, Feed API)
              ├── Jimaku        (API Key, Anime-fokussiert, AniList ID)
              ├── OpenSubtitles (API Key, REST v2, breite Abdeckung)
              └── SubDL         (API Key, Subscene-Nachfolger, ZIP)
           → Score & Sort (ASS bekommt +50 Bonus)
           → Download best → Save/Translate
```

### Provider-Prioritaet (Anime/ASS)

| # | Provider | ASS-Qualitaet | Auth | Besonderheit |
|---|---|---|---|---|
| 1 | AnimeTosho | Sehr hoch (Fansub) | Keine | Extrahiert Subs aus Releases, XZ-komprimiert |
| 2 | Jimaku | Hoch | API-Key | Anime-spezifisch, ZIP/RAR Archive, AniList ID |
| 3 | OpenSubtitles | Variabel | API-Key | Groesste DB, REST v2 API |
| 4 | SubDL | Variabel | API-Key | Subscene-Nachfolger, ZIP-Download, breite Abdeckung |

### Scoring-System (aus Bazarr/subliminal adaptiert)

Episode-Weights: hash(359), series(180), year(90), season(30), episode(30),
release_group(14), source(7), resolution(2), **format_bonus(50 fuer ASS)**

### Provider-Konfiguration

```env
SUBLARR_PROVIDER_PRIORITIES=animetosho,jimaku,opensubtitles,subdl
SUBLARR_PROVIDERS_ENABLED=           # Leer = alle aktiv
SUBLARR_OPENSUBTITLES_API_KEY=...
SUBLARR_OPENSUBTITLES_USERNAME=...
SUBLARR_OPENSUBTITLES_PASSWORD=...
SUBLARR_JIMAKU_API_KEY=...
SUBLARR_SUBDL_API_KEY=...
```

---

## Architektur

```
sublarr/
├── LICENSE                    # GPL-3.0
├── .env.example               # Alle konfigurierbaren Variablen (SUBLARR_ Prefix)
├── docker-compose.yml         # ${VAR} Referenzen, env_file
├── Dockerfile                 # Multi-Stage (Node + Python + ffmpeg + unrar)
├── Modelfile                  # Ollama Modell-Referenz
├── logo.svg                   # Sublarr Logo (Teal #1DB8D4)
│
├── backend/
│   ├── requirements.txt       # flask, flask-socketio, pydantic-settings, rarfile, etc.
│   ├── config.py              # Pydantic Settings, zentralisierte Config
│   ├── database.py            # SQLite (Jobs, DailyStats, ConfigEntries, ProviderCache, SubtitleDownloads)
│   ├── auth.py                # Optionale API-Key-Auth Middleware
│   ├── server.py              # Flask Blueprint /api/v1/, SPA Fallback, WebSocket
│   ├── translator.py          # Drei-Stufen Pipeline, Provider-Integration
│   ├── ass_utils.py           # Parametrisierte Language Tags, Style-Klassifizierung
│   ├── ollama_client.py       # Prompt-Template aus Config
│   ├── sonarr_client.py       # Sonarr v3 API (Serien, Episoden, Tags, Metadata)
│   ├── radarr_client.py       # Radarr v3 API (Filme, Tags, Metadata)
│   ├── jellyfin_client.py     # Jellyfin/Emby Library-Refresh
│   ├── wanted_scanner.py      # Wanted-Scanner (Sonarr/Radarr Scan, Scheduler)
│   ├── wanted_search.py       # Wanted-Search (Query-Builder, Process, Batch)
│   │
│   └── providers/             # ★ NEU: Eigenstaendiges Provider-System
│       ├── __init__.py        # ProviderManager (Priority, Search-All, Score, Download)
│       ├── base.py            # SubtitleProvider ABC, VideoQuery, SubtitleResult, Scoring
│       ├── http_session.py    # RetryingSession mit Rate-Limit-Handling
│       ├── opensubtitles.py   # OpenSubtitles.com REST API v2
│       ├── jimaku.py          # Jimaku Anime-Provider (AniList, ZIP/RAR)
│       ├── animetosho.py      # AnimeTosho Feed API (Fansub ASS, XZ)
│       └── subdl.py           # SubDL REST API (Subscene successor, ZIP)
│
└── frontend/                  # React + TypeScript + Tailwind CSS
    ├── src/
    │   ├── App.tsx            # Router + QueryClient
    │   ├── hooks/             # React Query Hooks + WebSocket (useApi, useWebSocket)
    │   ├── components/
    │   │   ├── layout/        # Sidebar (arr-style Teal Theme)
    │   │   └── shared/        # StatusBadge, ProgressBar, Toast, ErrorBoundary
    │   ├── pages/             # Dashboard, Activity, Library, Wanted, Queue, Settings, Logs, NotFound
    │   └── index.css          # Tailwind + arr-style CSS Variables
    └── public/favicon.svg
```

---

## Container-Details

| Parameter | Wert |
|---|---|
| **Container-Name** | `sublarr` |
| **Image** | Multi-Stage Build (Node 20 + Python 3.11-slim + ffmpeg + unrar-free) |
| **Port** | 5765 |
| **Volumes** | `/config` (DB, Logs), `/media` (Medien-Dateien) |
| **Restart** | unless-stopped |
| **WSGI** | gunicorn, 2 Workers, 4 Threads, 300s Timeout |

### Config-System

Alle Settings via Umgebungsvariablen mit `SUBLARR_` Prefix oder `.env` Datei.
Pydantic-Settings mit Type-Validation. Beispiel: `SUBLARR_TARGET_LANGUAGE=de`

Runtime-Config-Aenderungen via UI werden in `config_entries` DB-Tabelle gespeichert
und ueberschreiben Env/File-Werte beim naechsten Reload.

---

## API-Endpoints

### Translation & Jobs

| Methode | Pfad | Beschreibung |
|---|---|---|
| GET | `/api/v1/health` | Health Check (alle Services + Provider) — keine Auth |
| POST | `/api/v1/translate` | Async Uebersetzung (gibt job_id zurueck) |
| POST | `/api/v1/translate/sync` | Synchrone Uebersetzung |
| GET | `/api/v1/status/<job_id>` | Job-Status abfragen |
| GET | `/api/v1/jobs` | Paginierte Job-History aus DB |
| POST | `/api/v1/batch` | Batch-Verarbeitung (dry_run, Pagination) |
| GET | `/api/v1/batch/status` | Batch-Fortschritt |

### Subtitle Providers

| Methode | Pfad | Beschreibung |
|---|---|---|
| GET | `/api/v1/providers` | Status aller Provider (Name, Health, Enabled) |
| POST | `/api/v1/providers/test/<name>` | Provider-Konnektivitaet testen |
| POST | `/api/v1/providers/search` | Manuelle Provider-Suche (series, episode, language, format) |

### Library & Config

| Methode | Pfad | Beschreibung |
|---|---|---|
| GET | `/api/v1/stats` | Gesamtstatistiken |
| GET | `/api/v1/config` | Aktuelle Config (ohne Secrets) |
| PUT | `/api/v1/config` | Config updaten (invalidiert Provider-Manager) |
| GET | `/api/v1/library` | Serien/Filme mit Sub-Status |

### Language Profiles

| Methode | Pfad | Beschreibung |
|---|---|---|
| GET | `/api/v1/language-profiles` | Alle Profile listen |
| POST | `/api/v1/language-profiles` | Neues Profil erstellen |
| PUT | `/api/v1/language-profiles/<id>` | Profil bearbeiten |
| DELETE | `/api/v1/language-profiles/<id>` | Profil loeschen (nicht Default) |
| PUT | `/api/v1/language-profiles/assign` | Serie/Film einem Profil zuweisen |

### Wanted Search & Process

| Methode | Pfad | Beschreibung |
|---|---|---|
| POST | `/api/v1/wanted/<id>/search` | Provider-Suche fuer ein Wanted-Item (Target + Source Results) |
| POST | `/api/v1/wanted/<id>/process` | Download + Translate fuer ein Item (async) |
| POST | `/api/v1/wanted/batch-search` | Alle Wanted-Items verarbeiten (async, WebSocket-Progress) |
| GET | `/api/v1/wanted/batch-search/status` | Batch-Progress abfragen |

### Webhooks & Live

| Methode | Pfad | Beschreibung |
|---|---|---|
| POST | `/api/v1/webhook/sonarr` | Sonarr Download-Event |
| POST | `/api/v1/webhook/radarr` | Radarr Download-Event |
| GET | `/api/v1/logs` | Paginierte Logs |
| WS | `/socket.io/` | Live Updates (job_update, batch_progress, wanted_batch_progress) |

---

## Kernkonzepte

### Drei-Stufen Prioritaetskette (translator.py)

- **Case A:** Target ASS vorhanden → Skip
- **Case B:** Target SRT vorhanden → Upgrade-Versuch:
  - B1: **Provider suchen** nach Target ASS (ersetzt Bazarr)
  - B2: Source ASS embedded → uebersetzen zu .{lang}.ass
  - B3: Kein Upgrade moeglich → SRT behalten
- **Case C:** Kein Target Sub → Volle Pipeline:
  - C1: Source ASS embedded → .{lang}.ass
  - C2: Source SRT (embedded/extern) → .{lang}.srt
  - C3: **Provider suchen** nach Source Sub → uebersetzen
  - C4: Nichts gefunden → Fail
- Alle Sprach-Referenzen parametrisiert via `config.py` oder Language Profile

### Provider-System (providers/)

- **ProviderManager:** Singleton, initialisiert alle aktivierten Provider nach Priority
- **Search-Flow:** Alle Provider parallel durchsuchen → Ergebnisse scoren → Bestes downloaden
- **Scoring:** Hash-Match (359) > Series-Match (180) > Episode-Match (30) + ASS-Bonus (50)
- **Fallback:** Wenn Provider 1 fehlschlaegt → naechster Provider automatisch
- **Config-Reload:** `invalidate_manager()` bei Settings-Aenderung → neue Provider-Instanzen

### Multi-Language & Language Profiles

- `source_language` / `target_language` konfigurierbar (Default: en→de)
- Language-Tags automatisch generiert (z.B. "de" → {"de", "deu", "ger", "german"})
- Prompt-Template dynamisch aus Sprach-Konfiguration
- **Language Profiles:** Pro Serie/Film konfigurierbar, mehrere Zielsprachen moeglich
  - Default-Profil wird automatisch aus globaler Config erstellt
  - Wanted-Scanner erzeugt ein Item pro fehlender Sprache
  - Translation-Pipeline akzeptiert `target_language` Parameter (Fallback auf Config)

### Style-Klassifizierung (ass_utils.py)

- Dialog-Styles → werden uebersetzt
- Signs/Songs-Styles → bleiben original
- Heuristik: Styles mit >80% `\pos()`/`\move()` → Signs

### Persistence (database.py)

- SQLite mit WAL Mode, 9 Tabellen:
  - `jobs` — Translation Job-Tracking, Stats, Fehler
  - `daily_stats` — Aggregierte Tagesstatistiken
  - `config_entries` — Runtime-Config-Aenderungen
  - `provider_cache` — Suchergebnisse cachen (TTL-basiert)
  - `subtitle_downloads` — Download-History pro Provider
  - `language_profiles` — Multi-Language Profile (Name, Source, Targets)
  - `series_language_profiles` — Profil-Zuweisung pro Sonarr-Serie
  - `movie_language_profiles` — Profil-Zuweisung pro Radarr-Film

### Authentication (auth.py)

- Optional: API Key via `SUBLARR_API_KEY`
- Header `X-Api-Key` oder Query `?apikey=`
- Health + Webhook Endpoints exempt

---

## Git-Branching

```
main                        ← Stabil, nur nach Beta-Release
  └── feature/sublarr-public  ← Basis-Features (UI, Sonarr/Radarr, Translation)
        └── feature/provider-system  ← Provider-System + Milestones 1-6
```

**Main bleibt unberuehrt** bis eine gute Beta existiert.
Feature-Branches werden schrittweise nach oben gemergt.

---

## Sicherheitsregeln

1. **KEINE Medien-Dateien loeschen oder ueberschreiben** — nur `.{lang}.ass`/`.{lang}.srt` erstellen
2. **Container-Rebuild** erfordert Bestaetigung
3. **Batch-Verarbeitung** belastet GPU/CPU stark
4. Container hat RW-Zugriff auf Media-Volume
5. API-Key-Auth optional aber empfohlen fuer Produktions-Einsatz
6. Keine Secrets in docker-compose.yml — alles via `.env`
7. Provider-API-Keys nur in config_entries (DB) oder `.env` — nie in Code/Commits
8. Provider-Downloads nur in Media-Verzeichnisse — kein beliebiger Dateizugriff

---

## Technische Erkenntnisse

### Bazarr-Code-Uebernahme (GPL-3.0 kompatibel)

Folgende Bazarr-Komponenten wurden adaptiert oder als Referenz genutzt:

- **Provider-Interface:** `list_subtitles()` / `download_subtitle()` Signatur
- **Scoring-Weights:** Episode/Movie Score-Dictionaries aus subliminal_patch
- **Jimaku-Provider:** Architektur aus `subliminal_patch/providers/jimaku.py`
- **AnimeTosho-Provider:** Feed-API-Pattern aus `subliminal_patch/providers/animetosho.py`
- **Archive-Handling:** ZIP/RAR/XZ Extraction Pattern aus Provider-Mixins
- **RetryingSession:** HTTP-Retry mit Rate-Limit-Awareness

### Was NICHT uebernommen wurde (zu komplex / nicht noetig)

- Metaclass-basierte Provider-Auto-Discovery (fragil)
- SubZero Subtitle Modifications (OCR-Fixes, 1000+ Zeilen)
- ffsubsync (numpy-Dependency, Nischenfunktion)
- SignalR Real-Time Client (Webhooks reichen)
- Dynaconf Config-System (Pydantic ist besser fuer unseren Fall)
- Cloudflare-Bypass (CFSession — rechtlich grau)

### Provider-spezifische Hinweise

- **OpenSubtitles:** API-Key pflicht seit 2024, 5 req/s Rate-Limit, Login gibt hoehere Download-Limits
- **Jimaku:** Primaer japanische Subs, API-Token aus Account-Settings, ZIP/RAR Archive haeufig
- **AnimeTosho:** Kein Auth noetig, XZ-komprimierte Subs, AniDB-Episode-ID verbessert Matching
- **SubDL:** Subscene-Nachfolger seit Mai 2024, API-Key erforderlich, ZIP-Download, 2000 Downloads/Tag Limit
