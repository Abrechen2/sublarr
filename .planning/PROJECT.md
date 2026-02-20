# Sublarr — Open Subtitle Platform mit LLM-Uebersetzung

## What This Is

Sublarr ist eine open platform fuer Anime/Media Subtitle-Management mit LLM-Uebersetzung.
Es sucht Untertitel bei 12+ Providern (AnimeTosho, Jimaku, OpenSubtitles, SubDL + 8 Plugins),
downloadet die besten ASS/SRT-Dateien, uebersetzt via 5 konfigurierbaren Backends (Ollama, DeepL, LibreTranslate, OpenAI, Google)
und bietet Browser-Editor, Batch-Operationen, Whisper-Fallback und vollstaendige Bazarr-Migration.
Zielgruppe: Self-Hosted/Homelab-User, die ohne Sonarr/Radarr oder damit arbeiten.

## Core Value

ASS-first Anime Subtitle-Automation mit LLM-Uebersetzung — automatisch die besten Untertitel finden,
herunterladen und in die Zielsprache uebersetzen, ohne Styles oder Signs/Songs zu zerstoeren.

## Requirements

### Validated

<!-- Phase 1 (v1.0-beta) — shipped and working -->
- ✓ Provider-System mit 4 Built-in Providern (AnimeTosho, Jimaku, OpenSubtitles, SubDL) — M1+M6
- ✓ Provider-Scoring (hash, series, year, season, episode, release_group, ASS-Bonus) — M1
- ✓ Provider-Cache + Download-History — M1
- ✓ Eigenstaendiges Wanted-System (Sonarr/Radarr Library-Scan, fehlende Subs erkennen) — M2
- ✓ Such- und Download-Workflow (Provider-Suche, Download, Translate Pipeline) — M3
- ✓ Provider-UI + Management (Enable/Disable, Credentials, Test, Priority) — M4
- ✓ Upgrade-System (SRT→ASS, Score-Delta, Zeitfenster-Schutz) — M5
- ✓ Webhook-Integration (Sonarr/Radarr Download → Auto-Scan → Auto-Search) — M5
- ✓ Language-Profile System (Multi-Target-Languages, per Serie/Film) — M6
- ✓ Blacklist-System (Provider-Filterung, UI) — M7
- ✓ Download-History mit Statistiken — M7
- ✓ HI-Tag Removal (Hearing-Impaired, konfigurierbar) — M7
- ✓ Embedded Subtitle Detection (ffprobe, Cache, Extraction) — M8
- ✓ Glossar-System (DB, API, Translation-Pipeline-Integration) — M9
- ✓ Uebersetzungs-Validierung (Zeilenanzahl, Halluzination, Length-Ratio) — M9
- ✓ Prompt-Presets (DB, Settings-UI) — M9
- ✓ Radarr-Vollintegration + Multi-Library (Multi-Instance Sonarr/Radarr) — M10
- ✓ Jellyfin/Emby Library-Refresh — M10
- ✓ Notification-System via Apprise (90+ Services) — M11
- ✓ Docker Multi-Arch (amd64, arm64), Onboarding-Wizard — M12
- ✓ Three-Case Translation Pipeline (A: Skip, B: Upgrade, C: Full) — Core
- ✓ ASS Style-Klassifizierung (Dialog vs Signs/Songs) — Core
- ✓ Optional API-Key Auth (X-Api-Key Header) — Safety
- ✓ Error Handling Hierarchie (SublarrError, structured JSON responses) — S5
- ✓ Circuit Breaker (per-provider, CLOSED/OPEN/HALF_OPEN) — S5
- ✓ Database Backup System (SQLite backup API, rotation, scheduler) — S6
- ✓ Prometheus Metrics (graceful degradation) — S7
- ✓ CI/CD Pipeline (GitHub Actions, pytest, vitest, ruff, mypy, ESLint) — S1+S2

<!-- Phase 2+3 (v0.9.0-beta) — all shipped -->
- ✓ Application Factory + 9 Blueprint-Routen, database.py in 9 Module aufgeteilt — v0.9.0-beta (Phase 0)
- ✓ Plugin-System mit Auto-Discovery, Hot-Reload, declarative config_fields — v0.9.0-beta (Phase 1)
- ✓ 8 neue Built-in Provider (Gestdown, Podnapisi, Kitsunekko, Napisy24, Titrari, LegendasDivx, WhisperSubgen) — v0.9.0-beta (Phase 1)
- ✓ Provider Health-Monitoring (Response Time, Auto-Disable, Cooldown) — v0.9.0-beta (Phase 1)
- ✓ 5 Translation Backends (Ollama, DeepL, LibreTranslate, OpenAI-compatible, Google Cloud) — v0.9.0-beta (Phase 2)
- ✓ Backend-Auswahl pro Language-Profile + konfigurierbarer Fallback-Chain — v0.9.0-beta (Phase 2)
- ✓ Plex und Kodi Backend + Multi-Server Config (JSON-Array) — v0.9.0-beta (Phase 3)
- ✓ Whisper Case D: faster-whisper + Subgen API als Fallback wenn alle Provider scheitern — v0.9.0-beta (Phase 4)
- ✓ Standalone-Modus: Folder-Watch, guessit Parser, TMDB/AniList/TVDB Metadata-Lookup — v0.9.0-beta (Phase 5)
- ✓ Forced/Signs Subtitle Detection, Suche und per-Series Konfiguration — v0.9.0-beta (Phase 6)
- ✓ Event-Bus (blinker), Shell-Script Hooks, Outgoing Webhooks, Custom Scoring-Gewichtungen — v0.9.0-beta (Phase 7)
- ✓ EN/DE i18n (react-i18next), ZIP Backup/Restore, Recharts Statistiken, Dark/Light Theme — v0.9.0-beta (Phase 8)
- ✓ OpenAPI/Swagger UI at /api/docs, inkrementeller Scan, React.lazy Code-Splitting — v0.9.0-beta (Phase 9)
- ✓ SQLAlchemy ORM + Alembic Migrations, optionales PostgreSQL/Redis/RQ-Fallback — v0.9.0-beta (Phase 10)
- ✓ ASS/SRT Inline-Editor (CodeMirror, Timeline, Diff, Backup) — v0.9.0-beta (Phase 11)
- ✓ Multi-Select Batch-Operations, FTS5 Global-Search (Ctrl+K), Saved Filter Presets — v0.9.0-beta (Phase 12)
- ✓ Side-by-Side Subtitle Comparison, Timing-Sync, Health-Check mit Auto-Fix — v0.9.0-beta (Phase 13)
- ✓ Drag-and-Drop Dashboard Widgets (react-grid-layout), FAB Quick-Actions, Keyboard Shortcuts — v0.9.0-beta (Phase 14)
- ✓ API-Key Management, Jinja2 Notification Templates, Subtitle Deduplication Engine — v0.9.0-beta (Phase 15)
- ✓ Extended Health Diagnostics (alle 5 Clients), Bazarr DB Mapping Report, Plex/Kodi Compat Check, Multi-Format Export — v0.9.0-beta (Phase 16)

### Active

(none — all v0.9.0-beta requirements shipped. Awaiting next milestone definition.)

### Out of Scope (unchanged)

### Out of Scope

- Mobile App — Web-first, responsive reicht
- Real-time Chat/Community — Nicht Kernfunktion
- Multi-User/RBAC — Single-User Self-Hosted Fokus
- subliminal als Dependency — Eigenes leichtgewichtiges Provider-System
- Bezahl-Provider — Nur kostenlose/API-Key-basierte Provider

## Context

**v0.9.0-beta shipped 2026-02-20:** Phase 2+3 vollstaendig abgeschlossen.
~50.000 Zeilen Python Backend + ~24.000 Zeilen TypeScript Frontend.
17 Phasen, 71 Plans in 7 Tagen (2026-02-13 → 2026-02-20).

**Architektur (nach Phase 0 Refactoring):**
- Flask 3.1 App Factory (app.py) + 9 Blueprint-Routen (routes/) + 9 DB-Module (db/)
- React 19 + TypeScript + Tailwind v4 + TanStack Query Frontend
- SQLAlchemy ORM + Alembic Migrations (SQLite default, PostgreSQL optional)
- 12+ Provider (4 built-in + 8 neue + Plugin-System), 5 Translation Backends, 3 Whisper Backends

**Bekannte technische Schulden nach v0.9.0-beta:**
- 28 pre-existing test failures in integration/performance tests (existed before Phase 0)
- PERF-05 (Redis Sessions/Rate-Limiting) deferred — stateless API-key Auth reicht
- SQLite StaticPool fuer Tests (kein echter Pool) — unkritisch

## Context

**Brownfield-Projekt:** Phase 1 komplett implementiert und als v1.0.0-beta auf Docker Hub veroeffentlicht.
~10.300 Zeilen Backend + Frontend Code. 12 Milestones abgeschlossen. Safety Roadmap S1-S8 implementiert.

**Existierende Architektur:**
- Flask 3.1 Backend (server.py: 2618 Zeilen, monolithisch) mit SQLite WAL + thread-safe `_db_lock`
- React 19 + TypeScript + Tailwind v4 + TanStack Query Frontend
- 4 Provider (AnimeTosho, Jimaku, OpenSubtitles, SubDL) mit SubtitleProvider ABC
- Ollama-basierte LLM-Uebersetzung mit Batch-Processing und Glossar-Support
- Sonarr/Radarr v3 API Integration + Jellyfin/Emby Refresh
- Docker Multi-Stage Build (Node 20 + Python 3.11 + ffmpeg + unrar)

**Bekannte technische Schulden:**
- `server.py` ist monolithisch (2618 Zeilen) — koennte aufgeteilt werden
- `database.py` ist monolithisch (2153 Zeilen)
- SQLite-Limitationen bei hoher Concurrency
- In-Process Job-Queue geht bei Restart verloren

**Existierende Detailplanung:**
Die ROADMAP.md enthaelt bereits extrem detaillierte Milestone-Beschreibungen mit konkreten
Dateipfaden, API-Endpoints, DB-Schema-Aenderungen und Zeilenschaetzungen. Diese dient als
primaere Referenz fuer die GSD-Phase-Planung.

## Constraints

- **Tech Stack**: Python 3.11+ Backend (Flask), React 19 + TypeScript Frontend — bestehend, nicht aendern
- **Database**: SQLite bleibt Default, PostgreSQL nur als optionale Alternative (M23)
- **Docker**: Non-root User (PUID/PGID), Multi-Arch (amd64/arm64), Resource Limits
- **Backward-Compat**: Keine Breaking Changes an bestehender API ohne Migration-Guide
- **ASS-First**: ASS-Format hat immer Prioritaet, Styles werden nie zerstoert
- **Self-Hosted**: Alle Features muessen ohne Cloud-Dienste funktionieren (Cloud optional)
- **Provider-Architektur**: Bestehende SubtitleProvider ABC beibehalten, Plugin-System erweitert sie

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Eigenes Provider-System statt subliminal | subliminal: 15+ transitive Deps, Bazarr-Fork schwer wartbar | ✓ Good |
| Ollama als Default Translation-Backend | Self-Hosted, GPU-nutzbar, Custom Prompts, Glossar-Support | ✓ Good |
| ASS-Bonus im Scoring (+50) | ASS bewahrt Styles, wichtig fuer Anime | ✓ Good |
| SQLite mit WAL + _db_lock | Einfach, keine externe DB noetig, ausreichend fuer Single-Instance | ✓ Good |
| Flask statt FastAPI | Einfacher, Flask-SocketIO gut integriert, bestehende Codebase | ✓ Good |
| Hybrid GSD-Phase-Mapping | Grosse Milestones einzeln, kleine gruppiert — balanciert Granularitaet | ✓ Good |
| 1:1 Wave-Reihenfolge | Bestehende Abhaengigkeitsanalyse beibehalten | ✓ Good |
| Plugin-Config via config_entries | plugin.<name>.<key> Namespacing statt eigenem Table | ✓ Good |
| Lazy Backend Creation | Misconfigured backends blockieren nicht andere | ✓ Good |
| SQLAlchemy + Alembic | render_as_batch=True fuer SQLite ALTER TABLE Compat | ✓ Good |
| Single active Whisper backend | Kein Fallback-Chain fuer Whisper (nur ein Modell aktiviert) | ✓ Good |
| FTS5 Trigram fuer Global Search | LIKE queries (nicht MATCH) fuer 2+ char Suche | ✓ Good |
| react-grid-layout v2 | Built-in TypeScript, responsive containers | ✓ Good |
| Jinja2 SandboxedEnvironment | Template Injection Prevention fuer Notification Templates | ✓ Good |

---
*Last updated: 2026-02-20 after v0.9.0-beta milestone*
