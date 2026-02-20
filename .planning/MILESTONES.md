# Milestones

## v0.9.0-beta — Open Platform + Advanced Features (Shipped: 2026-02-20)

**Phases:** 0-16 (17 phases, 71 plans)
**Timeline:** 2026-02-13 → 2026-02-20 (7 days)
**Lines of code:** ~50K Python backend + ~24K TypeScript frontend
**Files changed:** 173 files, 34,070 insertions(+), 732 deletions(-)

**Key accomplishments:**
1. Refactored monolithic server.py (2618 lines) + database.py (2154 lines) into Application Factory with 9 Blueprint routes and 9 DB domain modules (Phase 0)
2. Plugin system with auto-discovery, hot-reload, declarative config_fields + 8 new built-in subtitle providers with health monitoring and auto-disable (Phase 1)
3. 5 translation backends (Ollama, DeepL, LibreTranslate, OpenAI-compatible, Google Cloud) with per-profile selection, fallback chains, and quality metrics (Phase 2)
4. Plex and Kodi media server support + Whisper speech-to-text fallback via faster-whisper and Subgen API (Phases 3-4)
5. Standalone folder-watch mode (no Sonarr/Radarr), forced subtitle detection, event bus with script hooks and outgoing webhooks, configurable scoring (Phases 5-7)
6. EN/DE i18n, ZIP backup/restore, Recharts statistics, dark/light theme, OpenAPI/Swagger at /api/docs, incremental scan, React.lazy code splitting (Phases 8-9)
7. SQLAlchemy ORM with optional PostgreSQL + Redis + RQ job queue (zero-config SQLite default preserved) + ASS/SRT inline editor with CodeMirror and timeline (Phases 10-11)
8. Multi-select batch operations, FTS5 global search (Ctrl+K), saved filter presets, subtitle comparison, timing sync, health check with auto-fix (Phases 12-13)
9. Drag-and-drop dashboard widgets, FAB quick actions, keyboard shortcuts, Jinja2 notification templates, subtitle deduplication engine (Phases 14-15)
10. Extended health diagnostics, Bazarr migration with DB mapping report, Plex/Kodi compatibility checks, multi-format export (Phase 16)

**Archive:** `.planning/milestones/v0.9.0-beta-ROADMAP.md`

---

