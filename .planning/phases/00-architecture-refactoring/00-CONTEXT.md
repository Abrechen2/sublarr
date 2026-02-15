# Phase 0: Architecture Refactoring - Context

**Gathered:** 2026-02-15
**Status:** Ready for planning

<domain>
## Phase Boundary

Convert the monolithic server.py (~2600 lines, 67 routes on one Blueprint) and database.py (76KB, 17 tables) into Application Factory pattern with Blueprint-based routing. This unblocks all subsequent phases (plugin registration, backend registration, media server registration). No new features — pure reorganization.

</domain>

<decisions>
## Implementation Decisions

### Directory layout after refactor

New structure introduces `routes/` and `db/` packages inside `backend/`:

```
backend/
  app.py                    # create_app() factory, extension init
  extensions.py             # socketio, db — lazy init, no app binding
  routes/
    __init__.py             # register_blueprints() helper
    translate.py            # /translate, /batch, /retranslate, /status, /jobs
    providers.py            # /providers, /providers/test, /search, /stats, /cache
    library.py              # /library, /series, /episodes, /sonarr, /radarr
    wanted.py               # /wanted, /wanted/batch-search, /wanted/search-all
    config.py               # /config, /settings, /onboarding, /config/export|import
    webhooks.py             # /webhook/sonarr, /webhook/radarr
    system.py               # /health, /database, /logs, /stats, /notifications
    profiles.py             # /language-profiles, /glossary, /prompt-presets
    blacklist.py            # /blacklist, /history
  db/
    __init__.py             # get_db(), init_db(), schema DDL
    jobs.py                 # jobs, daily_stats tables
    config.py               # config_entries table
    providers.py            # provider_cache, provider_stats tables
    library.py              # subtitle_downloads, upgrade_history tables
    wanted.py               # wanted_items table
    blacklist.py            # blacklist_entries table
    profiles.py             # language_profiles, series/movie_language_profiles
    translation.py          # translation_config_history, glossary, prompt_presets
    cache.py                # ffprobe_cache, anidb_mappings
  providers/                # unchanged (already modular)
  # standalone modules stay flat: translator.py, ollama_client.py,
  # sonarr_client.py, radarr_client.py, jellyfin_client.py,
  # wanted_scanner.py, wanted_search.py, ass_utils.py, etc.
```

- `routes/` not `blueprints/` — shorter, describes contents
- `db/` not `database/` — shorter, Flask convention
- `server.py` is removed after migration — `app.py` replaces it
- Existing standalone modules (translator.py, sonarr_client.py, etc.) stay flat — already right-sized
- Safety infrastructure (error_handler.py, circuit_breaker.py, transaction_manager.py, etc.) stays flat

### Route grouping into Blueprints (9 blueprints)

Mapped from the 67 existing routes on the current single `api` Blueprint:

| Blueprint | URL prefix | Routes | Description |
|-----------|-----------|--------|-------------|
| `translate` | `/api/v1` | /translate, /translate/sync, /status/\<id>, /jobs, /jobs/\<id>/retry, /batch, /batch/status, /retranslate/* | Translation jobs and retranslation |
| `providers` | `/api/v1` | /providers, /providers/test/\<name>, /providers/search, /providers/stats, /providers/cache/clear | Provider management and search |
| `library` | `/api/v1` | /library, /library/series/\<id>, /sonarr/*, /radarr/*, /episodes/* | Library browsing and *arr instances |
| `wanted` | `/api/v1` | /wanted, /wanted/summary, /wanted/refresh, /wanted/\<id>/*, /wanted/batch-search/*, /wanted/search-all | Missing subtitle queue |
| `config` | `/api/v1` | /config (GET/PUT), /settings/*, /onboarding/*, /config/export, /config/import | Configuration and onboarding |
| `webhooks` | `/api/v1` | /webhook/sonarr, /webhook/radarr | Incoming webhook handlers |
| `system` | `/api/v1` | /health, /health/detailed, /stats, /database/*, /logs, /notifications/* | System health, DB admin, logs |
| `profiles` | `/api/v1` | /language-profiles/*, /glossary/*, /prompt-presets/* | Language profiles, glossary, presets |
| `blacklist` | `/api/v1` | /blacklist/*, /history/* | Blacklist and download history |

All blueprints share the `/api/v1` prefix. The `app.py` level handles `/metrics` and the SPA fallback route.

### Database domain boundaries (9 modules)

Tables grouped by feature domain, not by access pattern:

| Module | Tables | Rationale |
|--------|--------|-----------|
| `db/jobs.py` | jobs, daily_stats | Job lifecycle and aggregate stats |
| `db/config.py` | config_entries | Runtime config overrides |
| `db/providers.py` | provider_cache, provider_stats | Provider caching and metrics |
| `db/library.py` | subtitle_downloads, upgrade_history | Download tracking and upgrades |
| `db/wanted.py` | wanted_items | Missing subtitle queue |
| `db/blacklist.py` | blacklist_entries | Blocked results |
| `db/profiles.py` | language_profiles, series_language_profiles, movie_language_profiles | All profile assignment |
| `db/translation.py` | translation_config_history, glossary_entries, prompt_presets | Translation configuration data |
| `db/cache.py` | ffprobe_cache, anidb_mappings | Ephemeral caches and ID mappings |

Schema DDL stays in `db/__init__.py` — all tables share one SQLite file, schema should be defined in one place.

### Backward compatibility scope

- **Tests:** Import path changes are acceptable (mechanical, not logic). All test *assertions* must still pass. Test files may be updated with new import paths.
- **Docker:** Entry point changes from `python server.py` to new app.py entry. Acceptable — Docker users rebuild images.
- **npm scripts:** `npm run dev:backend` updated to new entry point. Dev workflow preserved.
- **No compatibility shim:** No `server.py` wrapper for old imports. Clean break.
- **API contract unchanged:** All HTTP endpoints remain at same paths with same request/response formats. Zero impact on frontend or external consumers.

### Claude's Discretion

- How to implement `create_app()` internals (extension init order, config loading)
- How to handle the StructuredJSONFormatter and WebSocket log handler migration
- How to wire Socket.IO events into the factory pattern
- Exact `extensions.py` implementation (init_app pattern vs. lazy init)
- How to handle the module-level `settings = get_settings()` pattern across route files
- Migration order (which files to split first)
- Whether to use `flask.current_app` vs. other patterns for accessing app context

</decisions>

<specifics>
## Specific Ideas

No specific requirements — open to standard Flask Application Factory approaches. The existing codebase already uses Blueprint (single `api` Blueprint in server.py) and Flask-SocketIO, so the patterns are familiar.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 00-architecture-refactoring*
*Context gathered: 2026-02-15*
