# Sublarr — Subtitle Translation Service (*arr-Style)

> **Teil des DIYHaus Hub** — Open-Source Anime/Media Untertitel-Uebersetzer

## Zweck

Automatische Uebersetzung von Anime-Untertiteln via Ollama LLM.
Multi-Language-Support (konfigurierbare Quell- und Zielsprache), ASS und SRT Formate.
Arbeitet mit dem *arr-Oekosystem zusammen: Sonarr, Radarr, Bazarr, Jellyfin/Emby.

**Primaerziel:** Zielsprache ASS-Untertitel fuer jede Anime-Episode.

## *arr-API Integrationen

| Service | Auth-Header | Zweck |
|---|---|---|
| Sonarr (v3) | `X-Api-Key` | Serien/Episoden-Liste, File-Paths, Webhooks (OnDownload) |
| Radarr (v3) | `X-Api-Key` | Film-Liste, File-Paths, Webhooks (OnDownload) |
| Bazarr | `X-API-KEY` | Wanted-Liste, Subtitle-Search/Download, Scan-Disk |
| Jellyfin/Emby | `X-MediaBrowser-Token` | Library-Refresh nach neuen Untertiteln |

---

## Architektur

```
sublarr/
├── LICENSE                    # GPL-3.0
├── .env.example               # Alle konfigurierbaren Variablen (SUBLARR_ Prefix)
├── docker-compose.yml         # ${VAR} Referenzen, env_file
├── Dockerfile                 # Multi-Stage (Node + Python)
├── Modelfile                  # Ollama Modell-Referenz
├── logo.svg                   # Sublarr Logo (Teal #1DB8D4)
│
├── backend/
│   ├── requirements.txt       # flask, flask-socketio, pydantic-settings, etc.
│   ├── config.py              # Pydantic Settings, zentralisierte Config
│   ├── database.py            # SQLite Models (Jobs, DailyStats, ConfigEntries)
│   ├── auth.py                # Optionale API-Key-Auth Middleware
│   ├── server.py              # Flask Blueprint /api/v1/, SPA Fallback, WebSocket
│   ├── translator.py          # Sprach-Parameter statt Hardcoding
│   ├── ass_utils.py           # Parametrisierte Language Tags
│   ├── ollama_client.py       # Prompt-Template aus Config
│   ├── bazarr_client.py       # URLs/Keys aus config.py
│   ├── sonarr_client.py       # Sonarr v3 API (Serien, Episoden, Tags)
│   ├── radarr_client.py       # Radarr v3 API (Filme, Tags)
│   └── jellyfin_client.py     # Jellyfin/Emby Library-Refresh
│
└── frontend/                  # React + TypeScript + Tailwind CSS
    ├── src/
    │   ├── App.tsx            # Router + QueryClient
    │   ├── api/client.ts      # Axios-Wrapper fuer /api/v1/
    │   ├── hooks/             # React Query Hooks + WebSocket
    │   ├── components/        # Layout (Sidebar), Shared (StatusBadge, ProgressBar)
    │   ├── pages/             # Dashboard, Activity, Wanted, Queue, Settings, Logs
    │   └── lib/               # Utils, Types
    └── public/favicon.svg
```

---

## Container-Details

| Parameter | Wert |
|---|---|
| **Container-Name** | `sublarr` |
| **Image** | Multi-Stage Build (Node 20 + Python 3.11-slim + ffmpeg) |
| **Port** | 5765 |
| **Volumes** | `/config` (DB, Logs), `/media` (Medien-Dateien) |
| **Restart** | unless-stopped |
| **WSGI** | gunicorn, 2 Workers, 4 Threads, 300s Timeout |

### Config-System

Alle Settings via Umgebungsvariablen mit `SUBLARR_` Prefix oder `.env` Datei.
Pydantic-Settings mit Type-Validation. Beispiel: `SUBLARR_TARGET_LANGUAGE=de`

---

## API-Endpoints

| Methode | Pfad | Beschreibung |
|---|---|---|
| GET | `/api/v1/health` | Health Check (alle Services) — keine Auth |
| POST | `/api/v1/translate` | Async Uebersetzung (gibt job_id zurueck) |
| POST | `/api/v1/translate/sync` | Synchrone Uebersetzung |
| POST | `/api/v1/translate/wanted` | Bazarr Wanted-List verarbeiten |
| GET | `/api/v1/status/<job_id>` | Job-Status abfragen |
| GET | `/api/v1/status/bazarr` | Bazarr-Integration Status |
| GET | `/api/v1/jobs` | Paginierte Job-History aus DB |
| POST | `/api/v1/batch` | Batch-Verarbeitung (dry_run, Pagination) |
| GET | `/api/v1/batch/status` | Batch-Fortschritt |
| GET | `/api/v1/stats` | Gesamtstatistiken |
| GET | `/api/v1/config` | Aktuelle Config (ohne Secrets) |
| PUT | `/api/v1/config` | Config updaten |
| GET | `/api/v1/library` | Serien/Filme mit Sub-Status |
| POST | `/api/v1/webhook/sonarr` | Sonarr Download-Event |
| POST | `/api/v1/webhook/radarr` | Radarr Download-Event |
| GET | `/api/v1/logs` | Paginierte Logs |
| WS | `/socket.io/` | Live Updates (job_update, batch_progress) |

---

## Kernkonzepte

### Drei-Stufen Prioritaetskette (translator.py)

- **Case A:** Target ASS vorhanden → Skip
- **Case B:** Target SRT vorhanden → Upgrade-Versuch (Bazarr ASS → Source ASS uebersetzen → SRT behalten)
- **Case C:** Kein Target Sub → Volle Pipeline (Source ASS → Source SRT → Bazarr fetch → Fail)
- Alle Sprach-Referenzen parametrisiert via `config.py`

### Multi-Language

- `source_language` / `target_language` konfigurierbar (Default: en→de)
- Language-Tags automatisch generiert (z.B. "de" → {"de", "deu", "ger", "german"})
- Prompt-Template dynamisch aus Sprach-Konfiguration

### Style-Klassifizierung (ass_utils.py)

- Dialog-Styles → werden uebersetzt
- Signs/Songs-Styles → bleiben original
- Heuristik: Styles mit >80% `\pos()`/`\move()` → Signs

### Persistence (database.py)

- SQLite mit WAL Mode
- Jobs-Tabelle: Status-Tracking, Stats, Fehler
- DailyStats-Tabelle: Aggregierte Tagesstatistiken
- ConfigEntries: Runtime-Config-Aenderungen

### Authentication (auth.py)

- Optional: API Key via `SUBLARR_API_KEY`
- Header `X-Api-Key` oder Query `?apikey=`
- Health + Webhook Endpoints exempt

---

## Sicherheitsregeln

1. **KEINE Medien-Dateien loeschen oder ueberschreiben** — nur `.{lang}.ass`/`.{lang}.srt` erstellen
2. **Container-Rebuild** erfordert Bestaetigung
3. **Batch-Verarbeitung** belastet GPU/CPU stark
4. Container hat RW-Zugriff auf Media-Volume
5. API-Key-Auth optional aber empfohlen fuer Produktions-Einsatz
6. Keine Secrets in docker-compose.yml — alles via `.env`
