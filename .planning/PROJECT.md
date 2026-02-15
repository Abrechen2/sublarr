# Sublarr — Open Subtitle Platform mit LLM-Uebersetzung

## What This Is

Sublarr ist ein eigenstaendiger Subtitle-Manager fuer Anime und Media mit integrierter LLM-Uebersetzung.
Es durchsucht Provider (AnimeTosho, Jimaku, OpenSubtitles, SubDL), downloadt die besten Subs
(ASS bevorzugt, Scoring-System) und uebersetzt automatisch via Ollama. Zielgruppe: Self-Hosted/Homelab-User,
insbesondere Anime-Fans die hochwertige ASS-Untertitel mit korrekter Style-Behandlung brauchen.

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

### Active

<!-- Phase 2 + 3: Milestones 13-32 -->

**Phase 2: Open Platform**
- [ ] Provider Plugin-Architektur + 8 neue Built-in Provider (M13)
- [ ] Translation Multi-Backend: DeepL, LibreTranslate, OpenAI-Compat, Google (M14)
- [ ] Whisper Speech-to-Text Integration (faster-whisper, Subgen-API) (M15)
- [ ] Media-Server Abstraction: Plex, Kodi (+ Jellyfin/Emby Migration) (M16)
- [ ] Standalone-Modus: Folder-Watch, TMDB/AniList/TVDB Metadata (M17)
- [ ] Forced/Signs Subtitle Management (M18)
- [ ] Event-System, Script-Hooks, Outgoing Webhooks, Custom Scoring (M19)
- [ ] UI i18n (EN/DE), Backup/Restore, Statistics-Page, Dark/Light Theme (M20)
- [ ] OpenAPI/Swagger, Performance-Optimierung, Tasks-Page, Health-Endpoint (M21)
- [ ] v0.9.0-beta Release + Community-Launch, Dokumentation (M22)
- [ ] Performance & Scalability: PostgreSQL-Option, Redis, RQ Job Queue (M23)

**Phase 3: Advanced Features & UX**
- [ ] Subtitle-Vorschau & Inline-Editor (M24)
- [ ] Batch-Operations & Smart-Filter, Global-Search (M25)
- [ ] Subtitle-Vergleichstool & Quality-Metrics (M26)
- [ ] Subtitle-Sync & Health-Check Tools (M27)
- [ ] Konfigurierbare Dashboard-Widgets & Quick-Actions (M28)
- [ ] API-Key-Management & Export/Import-Erweiterungen, Bazarr-Migration (M29)
- [ ] Notification-Templates & Advanced-Filter, Quiet-Hours (M30)
- [ ] Subtitle-Deduplizierung & Cleanup-Tools (M31)
- [ ] Externe Tool-Integrationen & Migration-Tools (M32)

### Out of Scope

- Mobile App — Web-first, responsive reicht
- Real-time Chat/Community — Nicht Kernfunktion
- Multi-User/RBAC — Single-User Self-Hosted Fokus
- subliminal als Dependency — Eigenes leichtgewichtiges Provider-System
- Bezahl-Provider — Nur kostenlose/API-Key-basierte Provider

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
| Hybrid GSD-Phase-Mapping | Grosse Milestones einzeln, kleine gruppiert — balanciert Granularitaet | — Pending |
| 1:1 Wave-Reihenfolge | Bestehende Abhaengigkeitsanalyse beibehalten | — Pending |

---
*Last updated: 2026-02-15 after initialization*
