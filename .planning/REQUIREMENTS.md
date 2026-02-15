# Requirements: Sublarr Phase 2+3

**Defined:** 2026-02-15
**Core Value:** ASS-first Anime Subtitle-Automation mit LLM-Uebersetzung — automatisch die besten Untertitel finden, herunterladen und uebersetzen, ohne Styles zu zerstoeren.

## v1 Requirements

### Architecture Refactoring (Phase 0 — Research-surfaced prerequisite)

- [ ] **ARCH-01**: Flask Application Factory pattern implementiert (create_app() function)
- [ ] **ARCH-02**: server.py in thematische Blueprints aufgeteilt (translate, providers, library, wanted, config, webhooks, system)
- [ ] **ARCH-03**: Module-level Singletons durch Flask Extensions/App-Context ersetzt
- [ ] **ARCH-04**: database.py in modulare Komponenten aufgeteilt (connection, models, queries)

### Provider Plugin System (M13)

- [ ] **PLUG-01**: Plugin-Verzeichnis mit Auto-Discovery (SubtitleProvider-Subclass Scan)
- [ ] **PLUG-02**: Plugin-Manifest + Validation (name collision, required methods, safe import)
- [ ] **PLUG-03**: Hot-Reload Support (API-Endpoint + optionaler File-Watcher)
- [ ] **PLUG-04**: Plugin-Config-System (dynamische config_fields, Settings-UI rendert automatisch)
- [ ] **PLUG-05**: Plugin-Template + Entwickler-Dokumentation

### Built-in Provider Expansion (M13)

- [ ] **PROV-01**: Addic7ed Provider (Web-Scraping, TV-Serien, Rate-Limit 24/Tag)
- [ ] **PROV-02**: Podnapisi Provider (REST API, europaeische Sprachen)
- [ ] **PROV-03**: Gestdown Provider (Subscene-Nachfolger, REST API)
- [ ] **PROV-04**: Kitsunekko Provider (Japanische Anime-Subs, Scraping)
- [ ] **PROV-05**: Whisper-Subgen Provider (externe Subgen-Instanz als Provider)
- [ ] **PROV-06**: Napisy24 Provider (polnische Subs)
- [ ] **PROV-07**: Titrari Provider (rumaenische Subs)
- [ ] **PROV-08**: LegendasDivx Provider (brasilianisch/portugiesisch)
- [ ] **PROV-09**: Provider Health Monitoring (Fehler-Tracking, Auto-Disable, Cooldown)
- [ ] **PROV-10**: Provider-Statistiken Dashboard (Erfolgsrate, Response Time, Downloads)

### Translation Multi-Backend (M14)

- [ ] **TRAN-01**: TranslationBackend ABC (translate_batch, health_check, get_config_fields)
- [ ] **TRAN-02**: Ollama Backend (Migration von ollama_client.py, bleibt Default)
- [ ] **TRAN-03**: DeepL Backend (Free + Pro, Glossar-Support via DeepL API)
- [ ] **TRAN-04**: LibreTranslate Backend (Self-Hosted, optional API-Key)
- [ ] **TRAN-05**: OpenAI-Compatible Backend (OpenAI, Azure, LM Studio, vLLM)
- [ ] **TRAN-06**: Google Cloud Translation Backend (API v3, Glossar-Support)
- [ ] **TRAN-07**: Backend-Auswahl pro Language-Profile
- [ ] **TRAN-08**: Fallback-Chain (konfigurierbare Reihenfolge)
- [ ] **TRAN-09**: Backend-Config UI (Settings Tab, Test-Button, Fallback-Editor)
- [ ] **TRAN-10**: Quality-Metrics pro Backend (DB-Tracking, Dashboard-Widget)

### Whisper Speech-to-Text (M15)

- [ ] **WHSP-01**: Whisper Backend ABC (transcribe, health_check, get_available_models)
- [ ] **WHSP-02**: faster-whisper Backend (CTranslate2, GPU+CPU, VAD-Filter)
- [ ] **WHSP-03**: Subgen-API Backend (externe Instanz via HTTP)
- [ ] **WHSP-04**: Audio-Extraktion (ffmpeg, japanischen Track bevorzugen)
- [ ] **WHSP-05**: Translation-Pipeline Case D (Whisper-Fallback nach Provider-Failure)
- [ ] **WHSP-06**: Whisper-Queue-System (Max-Concurrent, Progress, WebSocket-Events)
- [ ] **WHSP-07**: Whisper-UI (Settings-Tab, Transcribe-Button, Activity-Page, Dashboard)
- [ ] **WHSP-08**: Sprach-Erkennung + Validation (erkannte vs erwartete Source-Language)

### Media-Server Abstraction (M16)

- [ ] **MSRV-01**: MediaServer ABC (refresh_item, get_item_by_path, health_check)
- [ ] **MSRV-02**: Jellyfin/Emby Backend (Migration von jellyfin_client.py)
- [ ] **MSRV-03**: Plex Backend (PlexAPI, Token-Auth, Library-Refresh, Webhook)
- [ ] **MSRV-04**: Kodi Backend (JSON-RPC, Multi-Instance)
- [ ] **MSRV-05**: Multi-Server Config (JSON-Array, mehrere gleichzeitig)
- [ ] **MSRV-06**: Media-Server Settings-UI (Typ-Dropdown, Multi-Server-Editor, Test-Button)
- [ ] **MSRV-07**: Onboarding-Update (Multi-Server, Multi-Type)

### Standalone Mode (M17)

- [ ] **STND-01**: Filesystem-Watcher (watchdog, konfigurierbare Verzeichnisse, Debounce)
- [ ] **STND-02**: Media-File-Parser (guessit, Anime-Patterns, Ordnerstruktur)
- [ ] **STND-03**: TMDB Client (API v3, Suche, Serien-Info)
- [ ] **STND-04**: AniList Client (GraphQL, Anime-Erkennung, Episode-Mapping)
- [ ] **STND-05**: TVDB Client (API v4, Alternative Serien-ID)
- [ ] **STND-06**: Standalone-Library-Manager (DB-Tabellen, Auto-Grouping, Metadata-Enrichment)
- [ ] **STND-07**: Wanted-Scanner Integration (Standalone-Items in wanted_items)
- [ ] **STND-08**: Settings-UI (Library Sources Tab, Folder-Watch Config)
- [ ] **STND-09**: Onboarding-Update (Standalone-Pfad ohne Sonarr/Radarr)

### Forced/Signs Subtitle Management (M18)

- [ ] **FRCD-01**: Forced-Sub Kategorie in DB (subtitle_type Feld, separate Zaehlung)
- [ ] **FRCD-02**: Forced-Sub Provider-Suche (forced_only Parameter, Provider-spezifisch)
- [ ] **FRCD-03**: Smart-Detection (ffprobe Forced-Flag, ASS-Analyse, Benennungs-Patterns)
- [ ] **FRCD-04**: Per-Serie Forced-Preference (disabled/separate/auto in Language-Profile)
- [ ] **FRCD-05**: Frontend-Updates (Filter, Status-Badge, Settings)

### Event-System + Script-Hooks (M19)

- [ ] **EVNT-01**: Internes Event-System (Publish/Subscribe Event-Bus)
- [ ] **EVNT-02**: Hook-Engine (Shell-Script Ausfuehrung, Umgebungsvariablen, Timeout)
- [ ] **EVNT-03**: Hook-UI (Event-Liste, Script-Editor, Test-Button, Log)
- [ ] **EVNT-04**: Custom Outgoing Webhooks (HTTP, JSON-Payload, Retry-Logik)

### Custom Scoring (M19)

- [ ] **SCOR-01**: Scoring-Gewichtungen konfigurierbar (hash, series, year, etc.)
- [ ] **SCOR-02**: Provider-spezifische Scoring-Modifier (Bonus/Malus pro Provider)

### Frontend i18n (M20)

- [ ] **I18N-01**: react-i18next Setup (Namespaces, Sprach-Umschaltung, Persistenz)
- [ ] **I18N-02**: Englische Basis-Uebersetzung (alle Pages + Components)
- [ ] **I18N-03**: Deutsche Uebersetzung (vollstaendig, korrekte Fachbegriffe)

### Backup/Restore (M20)

- [ ] **BKUP-01**: Backup-System (Config + DB als ZIP, automatisch + manuell)
- [ ] **BKUP-02**: Restore-System (ZIP-Upload, Schema-Validation, Merge-Strategie)
- [ ] **BKUP-03**: Backup-UI (Settings Tab, Download, Upload, Auto-Toggle)

### Admin Polish + Statistics (M20)

- [ ] **ADMN-01**: Umfangreiche Statistics-Page (Charts, Zeitraum-Filter, Export)
- [ ] **ADMN-02**: Log-Verbesserungen (Level-Filter, Download, Rotation-Config)
- [ ] **ADMN-03**: Dark/Light Theme (Toggle, Tailwind dark: Prefix, Persistenz)
- [ ] **ADMN-04**: Subtitle Processing Tools (Adjust Times, Remove Tags, Common Fixes)

### OpenAPI + Performance (M21)

- [ ] **OAPI-01**: OpenAPI-Spec (apispec, alle Endpoints dokumentiert, Swagger-UI)
- [ ] **OAPI-02**: Wanted-Scan Optimierung (inkrementell, parallel ffprobe)
- [ ] **OAPI-03**: Provider-Suche Optimierung (parallel, Result-Streaming, Connection-Pooling)
- [ ] **OAPI-04**: Frontend Performance (Code-Splitting, Virtual-Scrolling)
- [ ] **OAPI-05**: Health-Endpoint Erweiterung (/health/detailed)
- [ ] **OAPI-06**: Task-Scheduler Dashboard / Tasks-Seite

### Release + Community (M22)

- [ ] **RELS-01**: Migration Guide v1.0.0-beta → v0.9.0-beta
- [ ] **RELS-02**: Plugin-Entwickler Guide (erweitert)
- [ ] **RELS-03**: User-Guide (Setup-Szenarien, Troubleshooting, FAQ)
- [ ] **RELS-04**: Community-Provider-Repository Setup
- [ ] **RELS-05**: Release-Vorbereitung (CHANGELOG, Tag, Docker, Unraid)

### Performance & Scalability (M23)

- [ ] **PERF-01**: SQLAlchemy als ORM + PostgreSQL-Option (SQLite bleibt Default)
- [ ] **PERF-02**: Database Connection Pooling
- [ ] **PERF-03**: Database Indexing-Optimierungen
- [ ] **PERF-04**: Redis fuer Provider-Cache (optional, Fallback zu SQLite)
- [ ] **PERF-05**: Redis fuer Session + Rate-Limiting
- [ ] **PERF-06**: Redis + RQ fuer persistente Job Queue
- [ ] **PERF-07**: Prometheus Metrics Export Erweiterung
- [ ] **PERF-08**: Grafana-Dashboards (vordefiniert)
- [ ] **PERF-09**: Backward-Compatibility (SQLite Default, Redis optional, Graceful Degradation)

### Subtitle-Vorschau & Editor (M24)

- [ ] **EDIT-01**: Vorschau-Komponente (ASS/SRT Parser, Syntax-Highlighting, Timeline)
- [ ] **EDIT-02**: Vorschau-Integration (Wanted, History, SeriesDetail)
- [ ] **EDIT-03**: Editor-Komponente (CodeMirror, Undo/Redo, Validierung)
- [ ] **EDIT-04**: Editor-Integration (SeriesDetail, History, Backup vor Edit)
- [ ] **EDIT-05**: Editor-Features (Live-Preview, Diff-View, Find & Replace)

### Batch-Operations & Smart-Filter (M25)

- [ ] **BATC-01**: Library Batch-Operations (Multi-Select, Bulk-Actions)
- [ ] **BATC-02**: Wanted Batch-Operations (Bulk-Search, Bulk-Process)
- [ ] **BATC-03**: History Batch-Operations (Bulk-Blacklist, Bulk-Export)
- [ ] **BATC-04**: Erweiterte Filter-Optionen (Multi-Filter, AND/OR)
- [ ] **BATC-05**: Gespeicherte Filter-Presets
- [ ] **BATC-06**: Quick-Filter-Buttons (konfigurierbar)
- [ ] **BATC-07**: Global-Search (Header-Suchleiste, Fuzzy, Ctrl+K)

### Subtitle-Vergleichstool & Quality-Metrics (M26)

- [ ] **COMP-01**: Vergleichs-Komponente (Side-by-Side, Diff-Highlighting)
- [ ] **COMP-02**: Multi-Compare (bis zu 4 Versionen)
- [ ] **COMP-03**: Per-Serie Quality-Metrics (Score-Trend, Provider-Erfolgsrate)
- [ ] **COMP-04**: Global Quality-Metrics Dashboard
- [ ] **COMP-05**: Quality-Warnings (automatische Problemerkennung)

### Subtitle-Sync & Health-Check (M27)

- [ ] **SYNC-01**: Sync-Engine (Offset, Speed-Multiplikator, Frame-Rate)
- [ ] **SYNC-02**: Sync-UI (SeriesDetail, manuelle + Auto-Detect Offsets)
- [ ] **SYNC-03**: Health-Check-Engine (Duplikate, Encoding, Timing, Styles)
- [ ] **SYNC-04**: Health-Check-UI (Badge, Dashboard-Widget)
- [ ] **SYNC-05**: Auto-Fix-Optionen (pro Problem, Preview, Batch)

### Dashboard-Widgets & Quick-Actions (M28)

- [ ] **DASH-01**: Widget-System (Library, Drag-and-Drop, Size, Visibility)
- [ ] **DASH-02**: Vordefinierte Widgets (8+ Widget-Types)
- [ ] **DASH-03**: Quick-Actions Toolbar (FAB, Keyboard-Shortcuts)
- [ ] **DASH-04**: Context-Specific Actions (seitenabhaengig)

### API-Key-Management & Export/Import (M29)

- [ ] **KEYS-01**: Zentrale Key-Verwaltung (Liste, Status, Maskierung)
- [ ] **KEYS-02**: Key-Features (Test, Rotation, Export/Import)
- [ ] **KEYS-03**: Erweiterte Export-Funktionen (Profiles, Glossare, Config als ZIP)
- [ ] **KEYS-04**: Import-Funktionen (Sublarr-Export, CSV)
- [ ] **KEYS-05**: Bazarr-Migration-Tool (Config, Profiles, Blacklist)

### Notification-Templates & Filter (M30)

- [ ] **NOTF-01**: Template-System (Editor, Variablen, Preview)
- [ ] **NOTF-02**: Template-Zuweisung (pro Service, pro Event-Type)
- [ ] **NOTF-03**: Advanced Event-Filter (Include/Exclude, Content-Filter)
- [ ] **NOTF-04**: Quiet-Hours (Zeitfenster, Ausnahmen)
- [ ] **NOTF-05**: Notification-History (Page, Re-Send, Export)

### Subtitle-Deduplizierung & Cleanup (M31)

- [ ] **DEDU-01**: Deduplizierungs-Engine (Content-Hash, Metadata-Vergleich)
- [ ] **DEDU-02**: Deduplizierungs-UI (Scan, Gruppierung, Batch-Delete)
- [ ] **DEDU-03**: Cleanup-Dashboard (Optionen, Preview, Statistiken)
- [ ] **DEDU-04**: Scheduled Cleanup (automatisch, Regeln konfigurierbar)
- [ ] **DEDU-05**: Disk-Space-Analyse (Widget, Trends, Warnung)

### Externe Tool-Integrationen (M32)

- [ ] **INTG-01**: Erweiterte Bazarr-Migration (DB-Reader, Mapping, Report)
- [ ] **INTG-02**: Plex-Kompatibilitaets-Check
- [ ] **INTG-03**: Sonarr/Radarr Health-Check (erweitert)
- [ ] **INTG-04**: Jellyfin/Emby Health-Check (erweitert)
- [ ] **INTG-05**: Export-Formate (Bazarr, Plex, Kodi, Generic)

## v2 Requirements

(Deferred — not in current scope)

- Frontend E2E Tests (Playwright) — geplant fuer spaeter
- Performance Tests (locust/pytest-benchmark) — geplant fuer spaeter
- Multi-User/RBAC — Single-User Self-Hosted Fokus
- Mobile App — Web-first
- Telemetrie — nur als Opt-in in M22 angedacht, niedrige Prioritaet

## Out of Scope

| Feature | Reason |
|---------|--------|
| subliminal als Dependency | Eigenes Provider-System, 15+ transitive Deps vermieden |
| Bezahl-Provider (nur API-Key-basierte) | Self-Hosted Fokus, keine Abo-Modelle |
| Real-time Chat/Community | Nicht Kernfunktion eines Subtitle-Managers |
| Video-Playback im Browser | Zu komplex, Subtitle-Preview reicht |
| Cloud-hosted Version | Nur Self-Hosted, Docker-First |
| RabbitMQ/Kafka | Redis Streams reichen fuer Event-Bus, Overkill vermeiden |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| ARCH-01..04 | Phase 0 | Pending |
| PLUG-01..05 | Phase 1 (M13) | Pending |
| PROV-01..10 | Phase 1 (M13) | Pending |
| TRAN-01..10 | Phase 2 (M14) | Pending |
| WHSP-01..08 | Phase 4 (M15) | Pending |
| MSRV-01..07 | Phase 3 (M16) | Pending |
| STND-01..09 | Phase 5 (M17) | Pending |
| FRCD-01..05 | Phase 6 (M18) | Pending |
| EVNT-01..04 | Phase 7 (M19) | Pending |
| SCOR-01..02 | Phase 7 (M19) | Pending |
| I18N-01..03 | Phase 8 (M20) | Pending |
| BKUP-01..03 | Phase 8 (M20) | Pending |
| ADMN-01..04 | Phase 8 (M20) | Pending |
| OAPI-01..06 | Phase 9 (M21+M22) | Pending |
| RELS-01..05 | Phase 9 (M21+M22) | Pending |
| PERF-01..09 | Phase 10 (M23) | Pending |
| EDIT-01..05 | Phase 11 (M24) | Pending |
| BATC-01..07 | Phase 12 (M25) | Pending |
| COMP-01..05 | Phase 13 (M26+M27) | Pending |
| SYNC-01..05 | Phase 13 (M26+M27) | Pending |
| DASH-01..04 | Phase 14 (M28) | Pending |
| KEYS-01..05 | Phase 15 (M29+M30+M31) | Pending |
| NOTF-01..05 | Phase 15 (M29+M30+M31) | Pending |
| DEDU-01..05 | Phase 15 (M29+M30+M31) | Pending |
| INTG-01..05 | Phase 16 (M32) | Pending |

**Coverage:**
- v1 requirements: 134 total
- Mapped to phases: 134
- Unmapped: 0 ✓

---
*Requirements defined: 2026-02-15*
*Last updated: 2026-02-15 after initial definition*
