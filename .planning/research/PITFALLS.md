# Pitfalls Research

**Domain:** Subtitle management platform (Phase 2+3 feature expansion)
**Researched:** 2026-02-15
**Confidence:** HIGH (based on Bazarr issue tracker, official docs, Sublarr codebase analysis, multiple corroborating sources)

## Critical Pitfalls

### Pitfall 1: Monolith Refactoring Breaks Singleton State Management

**What goes wrong:**
Sublarr's `server.py` (2618 lines) uses module-level singletons everywhere: `_manager` in providers, `_scanner` in wanted_scanner, `_client` in sonarr_client, plus a module-level `settings = get_settings()` at import time. Moving to Flask Application Factory + Blueprints breaks all of these because the `app` object no longer exists at import time, and module-level state is shared across test isolation boundaries. The `_db_lock` threading.Lock in database.py is also module-level -- splitting database.py into multiple modules means coordinating a shared lock across files or fundamentally rethinking the concurrency model.

**Why it happens:**
Developers refactor file structure (splitting into blueprints) without first converting singletons to application-context-aware objects. Flask's `current_app` and `g` proxies only work inside a request context. Background threads (wanted_scanner scheduler, job processing) run outside request context and break when they try to access `current_app`. The existing `get_settings()` pattern called at module scope fires before `create_app()` runs.

**How to avoid:**
1. Convert singletons to Flask extensions that register on the app (`init_app(app)` pattern) BEFORE splitting into blueprints.
2. Replace module-level `settings = get_settings()` with lazy access inside functions.
3. Use `app.extensions['provider_manager']` instead of module-level `_manager`.
4. For background threads, pass the app instance explicitly: `threading.Thread(target=fn, args=(app._get_current_object(),))`.
5. Refactor in two discrete steps: (a) convert to Application Factory with singletons-as-extensions, (b) then split into Blueprints. Never do both simultaneously.

**Warning signs:**
- `RuntimeError: Working outside of application context` in tests or background threads
- Tests that pass individually but fail when run together (shared singleton state)
- Import-time side effects (database connections opening at import)
- Circular import errors after moving files

**Phase to address:**
Must be tackled BEFORE Plugin System (M13), because plugins need a stable extension registration mechanism. Recommend a dedicated "Architecture Refactoring" milestone or as the first task in M13. This is the single highest-risk refactoring in the entire roadmap.

---

### Pitfall 2: Plugin System Security -- Python Cannot Be Sandboxed

**What goes wrong:**
Developers assume they can run third-party Python plugin code safely by restricting imports or using `exec()` with limited `__builtins__`. Python's object model makes this fundamentally impossible -- any object reference can traverse `__class__.__bases__[0].__subclasses__()` to reach `os.system`, `subprocess.Popen`, or `open()`. A malicious plugin could read secrets from environment variables, modify the database, or delete media files.

**Why it happens:**
The natural instinct is "plugins are just Python modules, I'll restrict what they can import." This has been proven broken repeatedly. Checkmarx, the Python Wiki, and multiple security researchers confirm: Python sandboxing at the language level is not viable. RestrictedPython, `exec()` with custom globals, and blocklists are all bypassable.

**How to avoid:**
1. Do NOT attempt language-level sandboxing. Accept that plugins run with full application permissions.
2. Use a trust-based model: plugins must be explicitly installed by the admin (like Bazarr, OctoPrint, Home Assistant).
3. Define a strict Plugin API surface using `SubtitleProvider` ABC as the template. Plugins implement interfaces, not arbitrary code.
4. Use `importlib.metadata` entry_points for discovery (the Python Packaging User Guide recommended approach).
5. Validate plugin metadata (version compatibility, required API version) at load time.
6. Run each provider's network calls through the existing `CircuitBreaker` and rate limiter.
7. For paranoid users, document Docker's `--read-only` filesystem and `cap_drop: ALL` as defense-in-depth.

**Warning signs:**
- Anyone proposing `exec()`, `eval()`, or RestrictedPython for plugin execution
- Plugin API that exposes raw database cursors or file system access
- No version compatibility checking between plugin API version and installed plugins

**Phase to address:**
M13 (Provider Plugin Architecture). This is a design decision, not a code fix. Must be decided at architecture time.

---

### Pitfall 3: Translation Multi-Backend Cost Explosion

**What goes wrong:**
Adding DeepL, OpenAI, and Google Translate alongside Ollama introduces per-character/per-token billing. A batch subtitle translation job (e.g., 500 episodes, each with 300+ subtitle lines) can silently rack up hundreds of dollars. Users configure a cloud backend, run a "process all wanted" batch, and discover a $200 API bill. This is not hypothetical -- it is one of the most commonly reported issues with LLM-powered tools in production.

**Why it happens:**
The existing Ollama backend is free (self-hosted), so there are no cost controls in the codebase. The translation pipeline processes ALL dialogue lines in batch. There is no concept of "cost per translation" or "spending limit" because it was never needed. Adding paid backends without adding cost controls is like removing the guardrails from a highway.

**How to avoid:**
1. Implement a cost estimation layer BEFORE adding paid backends: `estimate_cost(text_length, backend) -> float`.
2. Add configurable spending limits: daily, monthly, per-job maximums.
3. Show cost estimate in UI before confirming batch operations.
4. Default to Ollama (free) -- paid backends must be explicitly configured.
5. Track cumulative spend in a new `translation_costs` database table.
6. Add a confirmation step for batch operations that exceed a threshold (e.g., >$5).
7. Implement token counting per backend (DeepL: characters, OpenAI: tokens, Google: characters).

**Warning signs:**
- No cost tracking table in database schema
- Batch translate endpoint lacks a `dry_run` or `estimate` mode
- Missing spending limits in settings
- No per-backend usage counters visible in UI

**Phase to address:**
M14 (Translation Multi-Backend). Cost controls must be part of the same milestone, not deferred. Ship cost tracking with the first paid backend.

---

### Pitfall 4: Whisper GPU Memory OOM Kills Container

**What goes wrong:**
Adding faster-whisper for speech-to-text means loading a large model into GPU VRAM. The `large-v3` model requires ~4.7 GB VRAM (with INT8 quantization). If Ollama is already using the same GPU for translation (Qwen2.5:14b needs ~10 GB), loading Whisper simultaneously causes an OOM kill. The Docker container crashes with no useful error message -- just `Killed` or SIGKILL from the OOM killer. On systems without GPU (Raspberry Pi, low-spec NAS), Whisper falls back to CPU and a single episode takes 30+ minutes, appearing "frozen."

**Why it happens:**
Ollama and faster-whisper both want exclusive GPU access. Docker's `--gpus` flag shares the full GPU, not partitioned VRAM. There is no built-in coordination between two GPU-consuming processes in the same container. The existing Sublarr architecture runs translation in-process (via `ollama_client.py` HTTP calls to Ollama), so adding Whisper in-process creates a resource conflict.

**How to avoid:**
1. Make Whisper a separate optional service, not embedded in the main container. Recommend the `linuxserver/faster-whisper` Docker image or a `subgen` sidecar.
2. If embedding Whisper, use a semaphore to prevent concurrent GPU operations (translation OR transcription, never both).
3. Default to `base` or `small` Whisper model, not `large-v3`. Let users upgrade after verifying VRAM.
4. Implement a GPU VRAM check at startup: `nvidia-smi --query-gpu=memory.free --format=csv`.
5. Add clear CPU-only fallback with honest time estimates in the UI ("Estimated: 25 minutes for this episode on CPU").
6. Queue Whisper jobs separately from translation jobs -- never run them simultaneously.

**Warning signs:**
- Docker container exits with code 137 (OOM killed)
- Translation jobs start failing after Whisper integration
- No GPU memory monitoring in health endpoint
- Whisper jobs silently queuing but never completing

**Phase to address:**
M15 (Whisper Integration). Architecture decision: external service vs. embedded. Must be decided before implementation begins.

---

### Pitfall 5: Forced/Signs Subtitle Detection Creates Wanted-Queue Spam

**What goes wrong:**
This is Bazarr's most persistent pain point, documented across issues #1057, #1505, #1580, #2226, and #2288. When "Forced" subtitles are enabled, the wanted system cannot reliably distinguish between: (a) a full subtitle track, (b) a forced/signs-only track, and (c) a regular track with the forced flag set on some entries. This causes three cascading problems:
- Items perpetually appear in the wanted queue even when the user has subtitles they consider adequate
- Downloading a forced subtitle satisfies the "wanted" state and suppresses the search for full subtitles
- Embedded forced tracks are not detected as forced, triggering unnecessary downloads

**Why it happens:**
"Forced" subtitles have no universal standard. MKV files can flag individual subtitle entries as forced, or have an entire track that contains only forced content, or have a track named "Signs/Songs" that is functionally forced content. Providers also label them inconsistently. Sublarr's existing `classify_styles()` in `ass_utils.py` already handles the ASS Signs/Songs case (via `\pos()`/`\move()` detection), but this logic does not extend to embedded MKV forced flags or provider-reported forced status.

**How to avoid:**
1. Model forced/signs as a separate dimension, not a boolean. A subtitle has: type (full | forced | signs_songs | commentary), language, and format.
2. The wanted system must track wants per (language, type) pair, not just per language.
3. Downloading a forced subtitle must NOT satisfy a "full subtitle" want (Bazarr #1580 lesson).
4. Use a multi-signal approach for forced detection: MKV forced flag + track title heuristics ("Signs", "Songs", "Forced") + line count threshold (forced tracks typically have <50 lines per episode).
5. Add a "Forced Subtitle Policy" setting: "Ignore", "Download Both", "Download Only Full".
6. Show forced/full status clearly in the UI wanted list.

**Warning signs:**
- Wanted queue count keeps growing despite successful downloads
- Users report "I already have subs but it keeps searching"
- Provider downloads marked as forced being treated as satisfying full subtitle wants
- The same episode appearing repeatedly in the wanted queue

**Phase to address:**
M18 (Forced/Signs Subtitle Management). This requires changes to the wanted system (M2 territory) and provider scoring, so it has dependencies on core architecture.

---

### Pitfall 6: Gunicorn + Flask-SocketIO Single Worker Limitation

**What goes wrong:**
Sublarr's Dockerfile runs `gunicorn --workers 2 --worker-class gthread`. Flask-SocketIO's documentation explicitly states: "it is not possible to use more than one worker process" with gunicorn because WebSocket connections establish a persistent TCP connection to a specific worker, but gunicorn's load balancer may route subsequent requests to different workers. This causes WebSocket connections to constantly disconnect and reconnect ("thrashing"), making the live log stream and real-time job progress updates unreliable.

**Why it happens:**
The current Dockerfile uses `--workers 2` which works for REST API calls but breaks WebSocket. With `gthread` worker class and `simple-websocket`, each WebSocket connection occupies a thread. With only 1 worker allowed, the thread pool becomes the bottleneck for concurrent connections.

**How to avoid:**
1. Change to `--workers 1 --threads 8` (or higher) for the gthread approach. This is already mostly what the Dockerfile does but with 2 workers.
2. For scaling beyond one worker: deploy multiple single-worker instances behind nginx with `ip_hash` for sticky sessions.
3. Add Redis as a message queue backend for SocketIO (`flask-socketio[redis]`) to enable multi-worker coordination if needed.
4. The `simple-websocket` package (already in requirements) is the correct choice for `gthread` mode -- do NOT switch to eventlet or gevent (they have monkey-patching compatibility issues with many Python libraries).

**Warning signs:**
- WebSocket connections dropping and reconnecting in browser console
- Log stream showing gaps or duplicate entries
- Real-time progress updates lagging or missing
- Multiple users reporting different job statuses

**Phase to address:**
Should be fixed immediately (it is a bug in the current Dockerfile). Then revisited in M23 (Performance & Scalability) for multi-instance deployment with Redis message queue.

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Module-level singletons (`_manager`, `_client`, `_scanner`) | Simple, no DI framework needed | Breaks Application Factory, test isolation, plugin system | Only in Phase 1. Must convert before M13. |
| Raw SQL strings in database.py | No ORM overhead, full control | 2153-line file, no migration system, PostgreSQL compat requires rewriting queries | Acceptable for SQLite-only. Must add migration tool before M23. |
| `threading.Lock()` for database concurrency | Works for SQLite WAL + single process | Cannot scale to multi-process, PostgreSQL uses connection pooling not locks | Acceptable until M23. Abstract behind a DB access layer. |
| In-process job queue (threading) | No external dependencies | Jobs lost on restart, no persistence, no retry with backoff | Never acceptable for production. Should move to persistent queue in M23 or earlier. |
| `settings = get_settings()` at module scope | Convenient, fast access | Fires at import time, cannot reconfigure without restart, breaks testing | Must fix during refactoring before M13. |
| All API endpoints in server.py | Single file to understand | 2618 lines, merge conflicts, hard to navigate, impedes contributor onboarding | Acceptable for solo dev. Must split before community launch (M22). |

## Integration Gotchas

Common mistakes when connecting to external services.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Sonarr/Radarr API | Hardcoding v3 API paths; API silently returns 200 with empty results when path mapping is wrong | Detect API version at connection time (`/api/v3/system/status`). Validate path mapping by checking if the mapped path exists on the filesystem. |
| Path Mapping (multi-system) | Using path mapping when containers share the same volume mounts (mapping becomes double-mapping) | Only enable path mapping when Sonarr and Sublarr see different filesystem paths. Add a "Test Path" button that checks `os.path.exists()` after mapping. Bazarr issue #2307 documents this exact confusion. |
| OpenSubtitles API v2 | Not handling the JWT token refresh; 5 req/s limit is per API key, not per user | Cache JWT token, refresh before expiry. Implement per-API-key rate limiting (not per-instance). Track daily download quota (existing code has this). |
| Jellyfin/Emby API | Assuming identical APIs; Jellyfin forked from Emby at version 3.5, and some endpoints have diverged | Use the `X-Emby-Authorization` header for both, but test specific endpoints. Jellyfin's `/Library/Refresh` has different parameters than Emby's. Maintain a compatibility layer. |
| Plex API (new in M16) | Using XML API instead of REST; authentication requires Plex token via MyPlex claim | Use `plexapi` Python library, not raw HTTP. Plex tokens expire and need refresh. Library scan triggers differently than Jellyfin (per-section, not per-item). |
| DeepL API (new in M14) | Using DeepL Free API endpoint for DeepL Pro keys (different base URLs) | DeepL Free: `api-free.deepl.com`. DeepL Pro: `api.deepl.com`. Detect from API key suffix (`:fx` = free). Character limit: 500,000/month free. |
| TMDB API (new in M17) | Not caching responses; TMDB API has a 40 req/10s rate limit | Cache all metadata lookups for 24h minimum. Use batch/multi endpoints where available. Implement exponential backoff on 429 responses. |
| faster-whisper/Subgen | Assuming Subgen's API matches faster-whisper's Python API | Subgen has its own HTTP API that wraps faster-whisper. If supporting both, abstract behind an interface. GPU model loading is slow (~10s) -- keep model loaded between jobs. |

## Performance Traps

Patterns that work at small scale but fail as usage grows.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| SQLite `_db_lock` serializes ALL database access | API response times increase linearly with concurrent users; job processing slows down | Abstract database access behind a connection pool interface; SQLite WAL handles concurrent reads without locking | >5 concurrent active users or >10 concurrent background jobs |
| In-memory provider search cache | Memory grows unboundedly; no eviction policy | Add TTL-based eviction (already have `provider_cache_ttl_minutes`). Move to Redis in M23 for shared cache across workers. | >10,000 cached search results (~50 MB) |
| `ThreadPoolExecutor` for provider searches without backpressure | All providers queried simultaneously; slow provider holds thread; rate limits hit across all providers at once | Implement per-provider concurrency limits (max 2 concurrent per provider). Add queue depth monitoring. | >20 simultaneous wanted searches |
| ffprobe called per-file without caching during library scan | Full library scan of 5000 files takes 30+ minutes; hammers NAS storage | Already have `ffprobe_cache` table -- ensure cache hit rate is >95% by never invalidating unless mtime changes | >1000 files in library |
| Ollama translation with `stream: False` | Single 300-line batch takes 60-90s; no progress feedback; request timeout kills long translations | Switch to streaming mode for progress reporting. Reduce batch size if timeout approaches. | >500 subtitle lines per file OR slow GPU |
| WebSocket log broadcasting to all connected clients | Every log line is serialized and sent to every browser tab; high-frequency logs cause browser lag | Rate-limit log emission (max 10 lines/second). Use log level filtering per client. Batch multiple log lines per WebSocket frame. | >3 browser tabs open OR debug-level logging enabled |

## Security Mistakes

Domain-specific security issues beyond general web security.

| Mistake | Risk | Prevention |
|---------|------|------------|
| Plugin executing arbitrary code accessing environment variables | Plugin reads `SUBLARR_OPENSUBTITLES_API_KEY`, `SUBLARR_SONARR_API_KEY` and exfiltrates them | Do not pass env vars to plugin context. Plugins receive only their own config section. Document that plugins run with app permissions. |
| Provider download writing to arbitrary paths via ZIP extraction | Zip slip attack: malicious subtitle archive contains `../../etc/cron.d/backdoor` | Already mitigate partially with file path validation. Add explicit `os.path.commonpath()` check that extracted files stay within the target media directory. |
| Ollama/LLM prompt injection via subtitle content | Adversarial subtitle text tricks the LLM into ignoring translation instructions and outputting harmful content | Sanitize subtitle text before sending to LLM. Use system prompt + user prompt separation. Validate output format matches expected subtitle structure. |
| Webhook endpoints without authentication | Anyone who discovers the webhook URL can trigger library scans and download operations | The existing `require_api_key` decorator exists but webhooks from Sonarr/Radarr often cannot send custom headers. Add a webhook secret token as a URL parameter: `/webhook/sonarr?token=xxx`. |
| SQLite database accessible via path traversal | If `db_path` config is set to a predictable location and the web server serves static files | Already mitigated by serving from `/config/` not `/app/static/`. Ensure no route serves files from the `/config/` volume. |

## UX Pitfalls

Common user experience mistakes in this domain.

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Showing "No subtitles found" without explaining why | User assumes the tool is broken; actually, all providers returned results that scored below threshold | Show: "5 results found, all below minimum score (180). Best match: [provider] scored 120 (missing: season match, release group match). Lower minimum score?" |
| Path mapping errors showing raw Python tracebacks | Homelab users are not developers; they cannot debug `FileNotFoundError: /data/anime/...` | Show: "Sonarr reports file at `/data/anime/Show/ep.mkv` but Sublarr cannot find it. You may need path mapping. Sonarr's path starts with `/data/`, Sublarr's media path is `/media/`." |
| Batch operations with no progress or cancel button | User starts "Search All Wanted" for 500 items, then waits 45 minutes with no feedback | Show per-item progress. Allow cancellation. Show ETA based on average time per item. Use WebSocket for real-time updates (already have SocketIO). |
| Onboarding wizard asks for optional settings | New user overwhelmed by Jimaku API key, SubDL API key, Radarr URL, etc. | Wizard should only require: (1) media path, (2) Ollama URL, (3) source/target language. Everything else is optional and discoverable later. |
| Translation quality issues with no way to retry/fix | User sees bad translation but has no recourse except deleting the file and re-running | Add a "Retranslate" button per file. Keep the source subtitle for re-translation. Show side-by-side comparison in M24 (Subtitle Preview). |
| Wanted queue shows thousands of items with no filtering | Overwhelming wall of text; user cannot find what they care about | Default to grouped view (by series). Add filters: language, status, age, provider availability. Show counts per series, not individual episodes. |

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **Plugin System:** Often missing version compatibility checking between plugin API and installed plugins -- verify that a plugin built for API v1 fails gracefully when loaded into API v2
- [ ] **Translation Multi-Backend:** Often missing cost tracking and spending limits -- verify that batch operations show estimated cost BEFORE execution
- [ ] **Whisper Integration:** Often missing CPU fallback time estimates -- verify that the UI shows realistic processing time when no GPU is available
- [ ] **Media Server Integration:** Often missing path validation -- verify that after configuring Plex/Jellyfin, a "Test Connection" also validates that media paths are accessible
- [ ] **Standalone Mode:** Often missing fallback for unrecognized filename patterns -- verify that `My.Show.2024.S01E01.mkv` and `[SubGroup] Show Name - 01 (1080p).mkv` and `Show/Season 1/episode1.mkv` all parse correctly
- [ ] **Forced Subtitles:** Often missing the forced/full distinction in wanted tracking -- verify that downloading a forced sub does NOT mark the full sub want as satisfied
- [ ] **SQLite to PostgreSQL:** Often missing data migration testing with production data -- verify migration with a real database dump, not just empty schema
- [ ] **Redis Integration:** Often missing graceful degradation -- verify that the app starts and functions normally when Redis is unavailable
- [ ] **i18n:** Often missing pluralization rules -- verify that "1 subtitle" vs "2 subtitles" vs German "1 Untertitel" vs "2 Untertitel" all render correctly
- [ ] **Flask Refactoring:** Often missing background thread context -- verify that the wanted scanner and job processor still work after converting to Application Factory

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Monolith refactoring breaks singletons | MEDIUM | Revert to pre-refactoring state (git). Add integration tests covering background thread behavior before re-attempting. |
| Plugin escapes sandbox | HIGH | Cannot be recovered at code level. Revoke compromised API keys. Audit what the plugin accessed. Switch to trust-based model. |
| Translation cost explosion | LOW | Disable paid backend immediately. Costs cannot be recovered but cap future spend. Add spending limits. |
| Whisper OOM kills container | LOW | Restart container. Reduce Whisper model size or switch to external service. Add VRAM check. |
| Forced subtitle wanted-spam | MEDIUM | Clear wanted queue. Redesign data model to track (language, type) pairs. Re-scan library. |
| Gunicorn multi-worker WebSocket breakage | LOW | Change `--workers` to 1. Increase `--threads`. No data loss. |
| SQLite to PostgreSQL data loss | HIGH | Restore from SQLite backup (database_backup.py already exists). Re-run migration after fixing schema mapping. Always keep SQLite backup until PostgreSQL is verified. |
| Redis connection failure | LOW | If graceful degradation is implemented: nothing to recover. If not: restart app, fix Redis connection, restart again. |
| i18n missing translations | LOW | Fall back to English. Add the missing translation strings. No user data affected. |
| Path mapping misconfiguration | LOW | Fix mapping in settings. Re-scan library. No data lost, just incorrect file references in wanted queue. |

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Monolith singleton breakage | Pre-M13 (Architecture Refactoring) | All existing tests pass after converting to Application Factory. Background scanner runs correctly. |
| Plugin security model | M13 (Plugin Architecture) | Security review of plugin API surface. No raw DB/filesystem access exposed. Entry point discovery works. |
| Translation cost explosion | M14 (Multi-Backend) | Cost tracking table exists. Spending limits enforced. Batch operations show cost estimate. Test with $0.01 limit. |
| Whisper GPU OOM | M15 (Whisper) | VRAM check at startup. Concurrent GPU operation prevented. CPU fallback tested with timing. |
| Media server API divergence | M16 (Media Server Abstraction) | Integration tests against Jellyfin AND Plex (even if mocked). Path validation on connection test. |
| Standalone filename parsing | M17 (Standalone Mode) | Test suite with 50+ filename patterns from real-world releases (Scene, P2P, fansub, nested folders). |
| Forced/signs wanted-spam | M18 (Forced Subs) | Wanted queue count does not grow when forced subs are downloaded. Manual verification with anime that has signs-only tracks. |
| Event system infinite loops | M19 (Event System) | Circuit breaker on outgoing webhooks. Max recursion depth for event chains. Test with event that triggers itself. |
| i18n missing translations | M20 (i18n) | CI check that all translation keys exist in all supported locales. RTL rendering test for Arabic. |
| Gunicorn WebSocket scaling | M23 (Performance) | Load test with 10 concurrent WebSocket clients. Redis message queue for multi-worker. |
| SQLite to PostgreSQL migration | M23 (Performance) | Migration script tested with production-size database. Record count validation. Boolean and datetime conversion verified. |
| Redis graceful degradation | M23 (Performance) | App starts and passes health check with Redis disabled. Cache falls back to in-memory. Job queue falls back to threading. |

## Sources

- [Bazarr FAQ and Troubleshooting](https://wiki.bazarr.media/Troubleshooting/FAQ/) -- forced subtitle issues, provider problems
- [Bazarr GitHub #1057](https://github.com/morpheus65535/bazarr/issues/1057) -- forced subs in wanted queue
- [Bazarr GitHub #1505](https://github.com/morpheus65535/bazarr/issues/1505) -- forced/HI subtitle detection
- [Bazarr GitHub #1580](https://github.com/morpheus65535/bazarr/issues/1580) -- forced download suppresses full sub want
- [Bazarr GitHub #2226](https://github.com/morpheus65535/bazarr/issues/2226) -- provider not separating forced
- [Bazarr GitHub #2288](https://github.com/morpheus65535/bazarr/issues/2288) -- embedded forced detection
- [Bazarr GitHub #2307](https://github.com/morpheus65535/bazarr/issues/2307) -- path mapping issues
- [Bazarr GitHub #2512](https://github.com/morpheus65535/bazarr/issues/2512) -- path mapping not respected for sync
- [Bazarr Performance Tuning](https://wiki.bazarr.media/Additional-Configuration/Performance-Tuning/) -- resource usage
- [Flask-SocketIO Deployment Docs](https://flask-socketio.readthedocs.io/en/latest/deployment.html) -- single worker requirement
- [Flask-SocketIO GitHub #1915](https://github.com/miguelgrinberg/Flask-SocketIO/discussions/1915) -- async mode selection
- [Flask Application Factories](https://flask.palletsprojects.com/en/stable/patterns/appfactories/) -- circular import prevention
- [Miguel Grinberg: Flask Mega-Tutorial Part XV](https://blog.miguelgrinberg.com/post/the-flask-mega-tutorial-part-xv-a-better-application-structure) -- application factory refactoring
- [Checkmarx: Glass Sandbox](https://checkmarx.com/zero-post/glass-sandbox-complexity-of-python-sandboxing/) -- Python sandboxing impossibility
- [Python Wiki: SandboxedPython](https://wiki.python.org/moin/SandboxedPython) -- sandboxing limitations
- [Python Packaging: Creating and discovering plugins](https://packaging.python.org/en/latest/guides/creating-and-discovering-plugins/) -- entry_points approach
- [SQLite to PostgreSQL: Render Guide](https://render.com/articles/how-to-migrate-from-sqlite-to-postgresql) -- migration pitfalls
- [PostgreSQL Wiki: Converting from other Databases](https://wiki.postgresql.org/wiki/Converting_from_other_Databases_to_PostgreSQL) -- schema differences
- [faster-whisper GitHub](https://github.com/SYSTRAN/faster-whisper) -- GPU memory, quantization
- [Whisper GPU OOM Fix (Medium)](https://medium.com/@patelhet04/the-0-scalability-fix-how-whisper-microservice-saved-us-from-gpu-oom-65dfd41a2180) -- semaphore pattern
- [LinuxServer faster-whisper](https://docs.linuxserver.io/images/docker-faster-whisper/) -- Docker GPU setup
- [Redis Connection Pools Best Practices](https://www.pythontutorials.net/blog/how-do-i-properly-use-connection-pools-in-redis/) -- pool sizing
- [redis-py GitHub #932](https://github.com/redis/redis-py/issues/932) -- graceful reconnection
- [GuessIt PyPI](https://pypi.org/project/guessit/) -- filename parsing
- [Medusa GitHub #7743](https://github.com/pymedusa/Medusa/issues/7743) -- guessit regex dependency breakage
- [subgen GitHub](https://github.com/McCloudS/subgen) -- Whisper subtitle generation across media servers

---
*Pitfalls research for: Sublarr Phase 2+3 feature expansion*
*Researched: 2026-02-15*
