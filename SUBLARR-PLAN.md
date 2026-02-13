# Sublarr — Von CCAnimeTranslator zum Open-Source *arr-Tool

## Context

CCAnimeTranslator ist ein funktionierender Anime-Untertitel-Uebersetzer (EN→DE via Ollama), der aktuell als privater Docker-Container auf einem Unraid-Homelab laeuft. Er soll in **Sublarr** umgewandelt werden — ein oeffentliches Open-Source-Projekt im *arr-Style (wie Sonarr/Radarr/Bazarr) mit Web UI, Multi-Language-Support und sauberer Konfiguration.

**Entscheidungen:**
- Name: **Sublarr** (Subtitle + Language + arr)
- Frontend: React + TypeScript + shadcn/ui + Tailwind CSS (Dark Theme)
- Sprache: Multi-Language (konfigurierbare Ziel- und Quellsprache)
- Lizenz: GPL-3.0
- Backend bleibt: Python/Flask

**Logo:**
- Primaerfarbe: **Teal (#1DB8D4)** — einzigartig im *arr-Oekosystem (zwischen Sonarr-Blau und Lidarr-Gruen)
- Form: Runder Container mit stilisierter **Sprechblase + Uebersetzungspfeil** (bidirektional)
- Stil: Flat Design, wie alle *arr-Apps
- Sprechblase = Untertitel/Kommunikation, Pfeil = Uebersetzung
- SVG-basiert, skalierbar von 16px Favicon bis 512px+
- Wird als `logo.svg` im Root und als `favicon.ico` + `favicon.svg` in frontend/public/ abgelegt

**Arr-API Integrationen:**

| Service | Auth-Header | Zweck |
|---|---|---|
| Sonarr (v3) | `X-Api-Key` | Serien/Episoden-Liste, File-Paths, Webhooks (OnDownload) |
| Radarr (v3) | `X-Api-Key` | Film-Liste, File-Paths, Webhooks (OnDownload) |
| Bazarr | `X-API-KEY` | Wanted-Liste, Subtitle-Search/Download, Scan-Disk |
| Jellyfin/Emby | `X-MediaBrowser-Token` | Library-Refresh nach neuen Untertiteln |

---

## Neuer Branch

```bash
git checkout -b feature/sublarr-public
```

---

## Phase 1: Rebranding + Security + Config (Fundament)

### 1.1 Repository-Struktur

```
sublarr/
├── LICENSE                    # GPL-3.0
├── README.md                  # Badges, Quick Start, Screenshots
├── .env.example               # Alle konfigurierbaren Variablen
├── .gitignore                 # Erweitert: .env, node_modules, dist/
├── .dockerignore              # Erweitert: frontend/node_modules
├── docker-compose.yml         # Nur ${VAR} Referenzen, keine Secrets
├── Dockerfile                 # Multi-Stage (Node + Python)
├── Modelfile                  # Ollama Modell-Referenz
│
├── backend/
│   ├── requirements.txt       # + pydantic, flask-socketio, SQLAlchemy
│   ├── config.py              # NEU: Pydantic Settings, zentralisierte Config
│   ├── database.py            # NEU: SQLite Models (Jobs, Stats, Config)
│   ├── auth.py                # NEU: Optionale API-Key-Auth Middleware
│   ├── server.py              # Refactored: Blueprint /api/v1/, statische Files
│   ├── translator.py          # Refactored: Sprach-Parameter statt Hardcoding
│   ├── ass_utils.py           # Minimal: language_tags parametrisiert
│   ├── ollama_client.py       # Refactored: Prompt-Template aus Config
│   ├── bazarr_client.py       # Refactored: URLs aus Config
│   ├── sonarr_client.py       # NEU: Sonarr v3 API (Serien, Episoden, Tags)
│   ├── radarr_client.py       # NEU: Radarr v3 API (Filme, Tags)
│   └── jellyfin_client.py     # NEU: Jellyfin/Emby Library-Refresh
│
└── frontend/
    ├── package.json
    ├── tsconfig.json
    ├── vite.config.ts
    ├── tailwind.config.ts
    ├── index.html
    └── src/
        ├── main.tsx
        ├── App.tsx
        ├── api/                # API Client (fetch wrapper)
        ├── components/         # shadcn/ui Komponenten
        │   ├── ui/             # shadcn Primitives (Button, Card, Table, etc.)
        │   ├── layout/         # Sidebar, Navbar, PageHeader
        │   └── shared/         # StatusBadge, ProgressBar, LogViewer
        ├── pages/
        │   ├── Dashboard.tsx
        │   ├── Activity.tsx
        │   ├── Wanted.tsx
        │   ├── Queue.tsx
        │   ├── Settings.tsx
        │   └── Logs.tsx
        ├── hooks/              # useJobs, useStats, useWebSocket
        └── lib/                # utils, constants, types
```

### 1.2 Logo erstellen

**`logo.svg`** im Projekt-Root:
- Runder Container (viewBox 512x512)
- Teal (#1DB8D4) Hintergrundkreis
- Weisse Sprechblase mit gebogenem Doppelpfeil (Uebersetzungssymbol)
- Minimalistisch, flat, sofort erkennbar als Favicon

Ableitungen:
- `frontend/public/favicon.svg` — direkt verwenden
- `frontend/public/favicon.ico` — 32x32 generiert
- `frontend/public/logo-192.png` + `logo-512.png` — fuer PWA/Manifest

### 1.3 Config-System (`backend/config.py`)

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # General
    port: int = 5765
    api_key: str = ""              # Leer = keine Auth
    log_level: str = "INFO"
    media_path: str = "/media"
    db_path: str = "/config/sublarr.db"

    # Ollama
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:14b-instruct"
    batch_size: int = 15
    request_timeout: int = 90
    temperature: float = 0.3

    # Translation
    source_language: str = "en"
    target_language: str = "de"
    target_language_name: str = "German"
    prompt_template: str = ""      # Leer = Auto-generiert

    # Bazarr (optional)
    bazarr_url: str = ""
    bazarr_api_key: str = ""

    # Sonarr (optional)
    sonarr_url: str = ""
    sonarr_api_key: str = ""

    # Radarr (optional — fuer Anime-Filme)
    radarr_url: str = ""
    radarr_api_key: str = ""

    # Jellyfin/Emby (optional — Library-Refresh)
    jellyfin_url: str = ""
    jellyfin_api_key: str = ""

    class Config:
        env_prefix = "SUBLARR_"
        env_file = ".env"
```

### 1.4 Dateien in Phase 1

| Datei | Aktion | Details |
|---|---|---|
| `backend/config.py` | NEU | Pydantic Settings, Sprach-Defaults, Validation |
| `backend/auth.py` | NEU | Flask-Middleware: API-Key-Check (optional) |
| `backend/database.py` | NEU | SQLite Models: Job, Stat, ConfigEntry |
| `docker-compose.yml` | REWRITE | `env_file: .env`, keine Hardcoded-Werte |
| `.env.example` | NEU | Alle SUBLARR_* Variablen mit Kommentaren |
| `LICENSE` | NEU | GPL-3.0 Text |
| `.gitignore` | EDIT | + .env, node_modules/, dist/, *.db |
| `logo.svg` | NEU | Sublarr Logo (Teal, Sprechblase + Pfeil) |

---

## Phase 2: Backend Refactoring (Multi-Language + Persistence + *arr APIs)

### 2.1 Sprach-Abstraktion (`backend/translator.py`)

Hardcoded Patterns werden dynamisch aus Config generiert:

```python
# Vorher (hardcoded):
GERMAN_ASS_PATTERNS = [".de.ass", ".deu.ass", ".ger.ass", ".german.ass"]

# Nachher (aus config):
def get_target_patterns(lang_code, lang_tags):
    return [f".{tag}.ass" for tag in lang_tags]
```

- `detect_existing_german()` → `detect_existing_target()`
- `has_german_stream()` → `has_target_language_stream()`
- Output-Suffix: `.{target_language}.ass` statt `.de.ass`
- Prompt dynamisch: `"Translate from {source} to {target}"`

### 2.2 Prompt-Template (`backend/ollama_client.py`)

```python
# Default-Prompt (auto-generiert wenn leer):
f"Translate these anime subtitle lines from {source_name} to {target_name}.\n"
f"Return ONLY the translated lines, one per line, same count.\n"
f"Preserve \\N exactly as \\N (hard line break).\n"
f"Do NOT add numbering or prefixes.\n\n"
```

- CJK-Filter bleibt aktiv (Qwen2.5 halluziniert unabhaengig von Zielsprache)
- `OLLAMA_URL` etc. kommen aus `config.py` statt `os.environ`

### 2.3 Persistence (`backend/database.py`)

SQLite mit SQLAlchemy-lite (oder raw sqlite3):

```python
# Jobs-Tabelle
class Job:
    id: str (UUID)
    file_path: str
    status: str (queued/running/completed/failed)
    source_format: str (ass/srt)
    output_path: str
    stats_json: str
    error: str
    created_at: datetime
    completed_at: datetime

# Stats-Tabelle (aggregiert)
class DailyStat:
    date: date
    translated: int
    failed: int
    skipped: int
    by_format_json: str
```

- In-Memory `jobs` OrderedDict → SQLite
- In-Memory `stats` dict → SQLite mit Aggregation
- Stats-Lock bleibt (fuer Writes), Reads sind lock-free

### 2.4 *arr API Clients (NEU)

**`backend/sonarr_client.py`** — Sonarr v3 Integration:
```python
class SonarrClient:
    # GET /api/v3/series            → Alle Serien (mit Tags fuer Anime-Filter)
    # GET /api/v3/episode?seriesId= → Episoden einer Serie
    # GET /api/v3/episodefile/{id}  → File-Pfad einer Episode
    # GET /api/v3/tag               → Tags (z.B. "anime")
    # POST /api/v3/command          → RescanSeries nach neuen Subs
```
- Ersetzt die bisherige Sonarr-ID-Weitergabe ueber Bazarr
- Direkte Episoden-Enumeration fuer Library-Seite
- Tag-basierter Anime-Filter (konfigurierbar)

**`backend/radarr_client.py`** — Radarr v3 Integration:
```python
class RadarrClient:
    # GET /api/v3/movie             → Alle Filme
    # GET /api/v3/moviefile/{id}    → File-Pfad eines Films
    # GET /api/v3/tag               → Tags
    # POST /api/v3/command          → RescanMovie nach neuen Subs
```
- Fuer Anime-Filme (z.B. Studio Ghibli, Makoto Shinkai)
- Gleiche Translate-Pipeline wie Serien (MKV → Sub extrahieren → uebersetzen)

**`backend/jellyfin_client.py`** — Jellyfin/Emby Notification:
```python
class JellyfinClient:
    # POST /Items/{id}/Refresh      → Metadata-Refresh nach neuem Subtitle
    # POST /Library/Refresh         → Kompletter Library-Scan (Fallback)
```
- Optional: Nach erfolgreicher Uebersetzung Jellyfin/Emby benachrichtigen
- Emby nutzt identische API-Struktur

**Webhook-Empfang** (`backend/server.py`):
```python
# POST /api/v1/webhook/sonarr    → Sonarr OnDownload Event
# POST /api/v1/webhook/radarr    → Radarr OnDownload Event
```
- Sonarr/Radarr koennen Webhooks senden wenn neue Medien importiert werden
- Sublarr wartet konfigurierbare Zeit (Default: 30min, damit Bazarr zuerst suchen kann)
- Dann prueft Sublarr ob Uebersetzung noetig ist

### 2.5 API Versioning (`backend/server.py`)

```python
api = Blueprint("api", __name__, url_prefix="/api/v1")

# Bestehende Endpoints:
# GET  /api/v1/health
# POST /api/v1/translate
# POST /api/v1/translate/sync
# POST /api/v1/translate/wanted
# GET  /api/v1/status/<job_id>
# GET  /api/v1/status/bazarr
# POST /api/v1/batch
# GET  /api/v1/batch/status
# GET  /api/v1/stats

# Neue Endpoints:
# GET  /api/v1/config          — Aktuelle Config (ohne Secrets)
# PUT  /api/v1/config          — Config updaten (speichert in DB + .env)
# GET  /api/v1/jobs             — Paginierte Job-History aus DB
# GET  /api/v1/logs             — Paginierte Logs
# GET  /api/v1/library          — Serien/Filme mit Sub-Status (via Sonarr/Radarr)
# POST /api/v1/webhook/sonarr   — Sonarr Download-Event
# POST /api/v1/webhook/radarr   — Radarr Download-Event
# WS   /ws/logs                 — Live-Log-Stream via WebSocket

# SPA Fallback:
@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_spa(path):
    return send_from_directory("static", "index.html")
```

### 2.6 Dateien in Phase 2

| Datei | Aktion | Details |
|---|---|---|
| `backend/translator.py` | REFACTOR | Sprach-Patterns parametrisiert, Funktionen umbenannt |
| `backend/ass_utils.py` | EDIT | `GERMAN_LANG_TAGS` → parametrisiert, `has_german_stream` → `has_target_stream` |
| `backend/ollama_client.py` | REFACTOR | Prompt aus Config, Settings aus config.py |
| `backend/bazarr_client.py` | REFACTOR | URLs/Keys aus config.py statt os.environ |
| `backend/sonarr_client.py` | NEU | Sonarr v3: series, episodes, episodefile, tags, command |
| `backend/radarr_client.py` | NEU | Radarr v3: movie, moviefile, tags, command |
| `backend/jellyfin_client.py` | NEU | Jellyfin/Emby: Items/{id}/Refresh, Library/Refresh |
| `backend/server.py` | REFACTOR | Blueprint, API v1, DB, Webhook-Endpoints, neue Endpoints |
| `backend/database.py` | EDIT | Schema finalisieren |
| `backend/requirements.txt` | EDIT | + pydantic-settings, flask-socketio |

---

## Phase 3: React Frontend (arr-Style UI)

### 3.1 Projekt-Setup

```bash
npm create vite@latest frontend -- --template react-ts
cd frontend
npx shadcn@latest init     # Dark theme, Tailwind
npm install @tanstack/react-query axios socket.io-client
```

### 3.2 Layout & Navigation

**Sidebar (immer sichtbar, links):**
```
[Sublarr Logo]
─────────────
  Dashboard        /
  Activity         /activity
  Wanted           /wanted
  Queue            /queue
  Settings         /settings
  Logs             /logs
─────────────
  System: Healthy
v0.1.0
```

**Farbschema (arr-style dark):**
- Background: `#1a1d23` (fast schwarz)
- Surface: `#242731` (Karten, Sidebar)
- Border: `#2d3139`
- Text Primary: `#e1e3e8`
- Text Secondary: `#8b8f96`
- Accent/Brand: `#1DB8D4` (Sublarr Teal)
- Success: `#22c55e`
- Error: `#ef4444`
- Warning: `#f59e0b`

### 3.3 Seiten

**Dashboard (`/`):**
- 4 Status-Cards oben: Ollama Status, Bazarr Status, Uebersetzt Heute, Queue-Groesse
- Aktive Jobs mit Fortschrittsbalken
- Letzte 10 Activities (Tabelle)
- Quick-Stats Chart (optional: letzte 7 Tage)
- Verbindungsstatus aller konfigurierter Services (Sonarr/Radarr/Bazarr/Jellyfin)

**Activity (`/activity`):**
- Vollstaendige Job-Tabelle mit Pagination
- Spalten: Datei, Status, Format, Quelle, Dauer, Zeitstempel
- Filter: Status, Format, Datum
- Expandable Row: Quality Warnings, vollstaendige Stats

**Wanted (`/wanted`):**
- Bazarr Wanted-Liste (nur wenn Bazarr konfiguriert)
- Pro Episode: Serie, Staffel, Episode, fehlende Sprachen
- "Translate" Button pro Episode
- "Translate All" Button (mit Limit-Eingabe)

**Queue (`/queue`):**
- Laufende Uebersetzungen mit Live-Fortschritt
- Batch-Status wenn aktiv
- Abbrechen-Button

**Settings (`/settings`):**
- Tabs: General | Ollama | Bazarr | Sonarr | Radarr | Jellyfin | Translation | UI
- Formular-basiert mit shadcn Form-Komponenten
- "Test Connection" Button fuer jeden Service (Ollama/Bazarr/Sonarr/Radarr/Jellyfin)
- Connection-Status-Badge neben jedem Service-Tab
- "Save" Button mit Toast-Notification

**Logs (`/logs`):**
- Live-Log-Viewer (WebSocket-basiert)
- Log-Level-Filter (DEBUG, INFO, WARNING, ERROR)
- Suchfeld
- Auto-Scroll + Pause-Toggle

### 3.4 Dateien in Phase 3

| Datei/Ordner | Aktion | Details |
|---|---|---|
| `frontend/` | NEU | Komplettes React-Projekt |
| `frontend/src/pages/Dashboard.tsx` | NEU | Status-Cards, Activity-Feed, Quick-Stats |
| `frontend/src/pages/Activity.tsx` | NEU | Job-Tabelle mit Filter + Pagination |
| `frontend/src/pages/Wanted.tsx` | NEU | Bazarr Wanted-Liste + Translate-Buttons |
| `frontend/src/pages/Queue.tsx` | NEU | Laufende Jobs + Fortschritt |
| `frontend/src/pages/Settings.tsx` | NEU | Tabbed Config-Formular |
| `frontend/src/pages/Logs.tsx` | NEU | Live Log-Viewer |
| `frontend/src/components/layout/Sidebar.tsx` | NEU | *arr-Style Navigation |
| `frontend/src/api/client.ts` | NEU | Axios-Wrapper fuer /api/v1/ |
| `frontend/src/hooks/` | NEU | React Query Hooks |

---

## Phase 4: Docker + Deployment

### 4.1 Multi-Stage Dockerfile

```dockerfile
# Stage 1: Build React Frontend
FROM node:20-alpine AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# Stage 2: Python Backend + Frontend Bundle
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
COPY --from=frontend /build/dist ./static
EXPOSE 5765
VOLUME ["/config", "/media"]
HEALTHCHECK --interval=30s --timeout=10s CMD curl -f http://localhost:5765/api/v1/health || exit 1
CMD ["gunicorn", "--bind", "0.0.0.0:5765", "--workers", "2", "--threads", "4", "--timeout", "300", "server:app"]
```

### 4.2 docker-compose.yml (Public)

```yaml
services:
  sublarr:
    build: .
    container_name: sublarr
    ports:
      - "${SUBLARR_PORT:-5765}:5765"
    volumes:
      - ./config:/config
      - ${MEDIA_PATH:-/media}:/media:rw
    env_file: .env
    restart: unless-stopped
```

### 4.3 Dateien in Phase 4

| Datei | Aktion | Details |
|---|---|---|
| `Dockerfile` | REWRITE | Multi-Stage Node + Python |
| `docker-compose.yml` | REWRITE | Sauber mit env_file |
| `.env.example` | FINALIZE | Alle Variablen dokumentiert |
| `.dockerignore` | EDIT | + frontend/node_modules |

---

## Phase 5: Dokumentation + Polish

| Datei | Inhalt |
|---|---|
| `README.md` | Badges, Screenshots, Features, Quick Start (Docker), Config-Referenz, API-Doku-Link |
| `LICENSE` | GPL-3.0 Volltext |
| `CONTRIBUTING.md` | Setup-Anleitung, Code-Style, PR-Prozess |
| `docs/api.md` | Alle Endpoints mit Request/Response-Beispielen |
| `CLAUDE.md` | Aktualisiert fuer neues Projekt (Sublarr statt AnimeTranslator) |

---

## Abhaengigkeiten

```
Phase 1 (Config + Security + Logo)
  ↓
Phase 2 (Backend Refactoring + *arr APIs)
  ↓
Phase 3 (React Frontend)  ← kann teilweise parallel zu Phase 2
  ↓
Phase 4 (Docker Build)    ← braucht Phase 2 + 3
  ↓
Phase 5 (Docs + Polish)
```

---

## Verifizierung

Nach jeder Phase:
1. `docker compose build` — Baut ohne Fehler
2. `curl http://localhost:5765/api/v1/health` — Backend laeuft
3. Browser `http://localhost:5765/` — UI laed (ab Phase 3)
4. Test-Uebersetzung: `POST /api/v1/translate/sync` mit einer Anime-Episode
5. Settings ueber UI aendern → Restart → Aenderung persistent

End-to-End nach Phase 5:
1. Frisches `git clone` + `cp .env.example .env` + Config editieren
2. `docker compose up -d --build`
3. Browser oeffnen → Dashboard zeigt Status
4. Episode uebersetzen → Activity zeigt Ergebnis
5. Logs zeigen Uebersetzungs-Fortschritt live
