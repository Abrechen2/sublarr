# Sublarr — Standalone Subtitle Manager & Translator (*arr-Style)

Eigenstaendiger Subtitle-Manager fuer Anime/Media mit LLM-Uebersetzung via Ollama.
Durchsucht Provider (AnimeTosho, Jimaku, OpenSubtitles, SubDL), downloadt beste Subs
(ASS bevorzugt, +50 Scoring-Bonus) und uebersetzt automatisch. GPL-3.0.

## Commands

```bash
# Dev-Server (Backend + Frontend parallel)
npm run dev                    # oder einzeln:
npm run dev:backend            # Flask auf :5765
npm run dev:frontend           # Vite auf :5173 (Proxy → :5765)

# Tests
cd backend && python -m pytest # Backend (pytest, siehe pytest.ini)
cd frontend && npm test        # Frontend (vitest)

# Docker
docker build -t sublarr:dev .  # Multi-Stage: Node 20 + Python 3.11 + ffmpeg + unrar
docker compose up -d           # Production (Port 5765, Volumes: /config, /media)

# Lint
cd frontend && npm run lint    # ESLint
```

## Architektur

```
backend/
  server.py              # Flask /api/v1/, SPA Fallback, WebSocket (Socket.IO)
  config.py              # Pydantic Settings (SUBLARR_ Prefix), Runtime-Override via DB
  database.py            # SQLite WAL, 17 Tabellen
  translator.py          # Drei-Stufen Pipeline (A: Skip, B: Upgrade, C: Volle Suche)
  ass_utils.py           # ASS Style-Klassifizierung (Dialog vs Signs/Songs)
  ollama_client.py       # LLM-Uebersetzung, Prompt aus Config
  sonarr_client.py       # Sonarr v3 API
  radarr_client.py       # Radarr v3 API
  jellyfin_client.py     # Jellyfin/Emby Library-Refresh
  wanted_scanner.py      # Fehlende Subs erkennen (Scheduler)
  wanted_search.py       # Provider-Suche + Download fuer Wanted-Items
  anidb_mapper.py        # AniDB Episode-ID Mapping
  hi_remover.py          # Hearing-Impaired Tag Entfernung
  notifier.py            # Apprise Benachrichtigungen
  upgrade_scorer.py      # SRT→ASS Upgrade Scoring
  auth.py                # Optionale API-Key-Auth (X-Api-Key Header)
  providers/
    __init__.py          # ProviderManager (Singleton, Priority, Score, Download)
    base.py              # SubtitleProvider ABC, VideoQuery, SubtitleResult
    http_session.py      # RetryingSession mit Rate-Limit
    animetosho.py        # Feed API, Fansub ASS, XZ-komprimiert, kein Auth
    jimaku.py            # Anime-spezifisch, ZIP/RAR, AniList ID, API-Key
    opensubtitles.py     # REST v2, 5 req/s Limit, API-Key + Login
    subdl.py             # Subscene-Nachfolger, ZIP, 2000 DL/Tag, API-Key
  tests/                 # pytest: test_server, test_database, test_config, test_auth, test_ass_utils

frontend/                # React 19 + TypeScript + Tailwind v4 + TanStack Query
  src/
    App.tsx              # Router + QueryClient
    api/client.ts        # Axios API Client
    hooks/               # useApi (React Query), useWebSocket (Socket.IO)
    lib/types.ts         # TypeScript Interfaces
    components/layout/   # Sidebar (*arr-style Teal Theme)
    components/shared/   # StatusBadge, ProgressBar, Toast, ErrorBoundary
    pages/               # Dashboard, Activity, Library, Wanted, SeriesDetail,
                         # Settings, Logs, History, Blacklist, Onboarding, Queue
```

## Kernkonzepte

**Translation-Pipeline (translator.py):**
- Case A: Target ASS vorhanden → Skip
- Case B: Target SRT → Upgrade via Provider (B1) oder Uebersetzung (B2)
- Case C: Kein Target → Volle Pipeline (embedded → Provider → Translate)

**Provider-Scoring:** hash(359) > series(180) > year(90) > season(30) > episode(30) > release_group(14) + ASS-Bonus(50)

**Config-Kaskade:** Env/`.env` → Pydantic Settings → Runtime-Override in `config_entries` DB-Tabelle

**Language Profiles:** Pro Serie/Film, mehrere Zielsprachen, Default aus globaler Config (en→de)

**Style-Klassifizierung:** Dialog-Styles → uebersetzen, Signs/Songs (>80% `\pos()`/`\move()`) → original

## API (alle unter /api/v1/)

Translate: `POST /translate`, `/translate/sync`, `GET /status/<id>`, `/jobs`, `/batch`
Providers: `GET /providers`, `POST /providers/test/<name>`, `/providers/search`
Library: `GET /library`, `/stats`, `/config`, `PUT /config`
Wanted: `POST /wanted/<id>/search`, `/wanted/<id>/process`, `/wanted/batch-search`
Profiles: `GET|POST /language-profiles`, `PUT|DELETE /language-profiles/<id>`
Webhooks: `POST /webhook/sonarr`, `/webhook/radarr`
Live: `GET /logs`, `WS /socket.io/`

## Sicherheitsregeln

1. **KEINE Medien-Dateien loeschen/ueberschreiben** — nur `.{lang}.ass`/`.{lang}.srt` erstellen
2. **Container-Rebuild** erfordert Bestaetigung
3. **Secrets** nur in `.env` oder `config_entries` DB — nie in Code/Commits
4. **Provider-Downloads** nur in Media-Verzeichnisse — kein beliebiger Dateizugriff
5. **Batch-Verarbeitung** belastet GPU/CPU stark — vorher bestaetigen

## Versionsstrategie

Sublarr folgt Semantic Versioning (SemVer) mit konservativer Beta-Strategie:

**Aktueller Stand:**
- ✅ **v1.0.0-beta** (Phase 1: Foundation) — veröffentlicht

**Phase 2: Open Platform (v0.x Serie)**
- **v0.2.0-beta** — Nach Milestone 13-15 (Plugin-System, Translation-Backend, Whisper)
- **v0.3.0-beta** — Nach Milestone 16-18 (Media-Server, Standalone, Forced-Subs)
- **v0.4.0-beta** — Nach Milestone 19-21 (Events/Hooks, i18n, OpenAPI)
- **v0.5.0-beta** — Nach Milestone 23 (Performance-Optimierungen)
- **v0.9.0-beta** — Stabilisierung (alle Phase 2 Features, Bugfixes)
- **v0.9.1, v0.9.2, ...** — Weitere Bugfixes und Stabilisierung
- **v1.0.0** — Final Release (nach ausreichendem Testing und Community-Feedback)

**Phase 3: Advanced Features (v1.x Serie)**
- **v1.1.0-beta** — Nach Phase 3 Milestones (Advanced Features & UX)
- **v1.2.0, v1.3.0, ...** — Weitere Feature-Releases
- **v2.0.0** — Nur bei Breaking Changes

**Release-Strategie:**
- Beta-Releases: Neue Features, koennen Breaking Changes enthalten
- RC (Release Candidate): Feature-complete, nur noch Bugfixes
- Final Release: Production-ready, ausreichend getestet
- Patch-Releases (x.x.1, x.x.2): Nur Bugfixes, keine neuen Features
