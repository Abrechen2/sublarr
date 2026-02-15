# Codebase Concerns

**Analysis Date:** 2026-02-15

## Tech Debt

**Monolithic server.py:**
- Issue: Flask app bundled into single 2618-line file with all API endpoints, background threads, WebSocket handlers, and route definitions
- Files: `backend/server.py`
- Impact: Difficult to maintain, test individual routes, and reason about application flow. High cyclomatic complexity. Violates single-responsibility principle
- Fix approach: Extract API endpoints into separate Blueprint modules (`/api/v1/translate.py`, `/api/v1/wanted.py`, `/api/v1/providers.py`, etc.). Move background job logic to separate service layer

**Large database.py:**
- Issue: 2153-line database module with 50+ functions mixing schema definitions, migrations, and CRUD operations across 17+ tables
- Files: `backend/database.py`
- Impact: Hard to locate specific operations, test individual functions, and maintain schema evolution. No separation between data access patterns
- Fix approach: Split into domain-specific modules (`db/jobs.py`, `db/wanted.py`, `db/providers.py`, `db/schemas.py`). Use Repository pattern or lightweight ORM (SQLAlchemy Core)

**Daemon threads without graceful shutdown:**
- Issue: Background translation jobs, wanted scans, and webhook processing spawn daemon threads (`threading.Thread(target=..., daemon=True)`) without cleanup mechanism
- Files: `backend/server.py` (lines 462, 666, 1637, 1708, 1779, 1802, 2000, 2066, 2162, 2232, 2363), `backend/wanted_scanner.py` (lines 625, 636), `backend/database_backup.py` (line 289)
- Impact: In-flight jobs terminated abruptly on application shutdown. Risk of incomplete translations, corrupted subtitle files, or database writes mid-transaction. No visibility into running jobs. Restart during active translation may leave orphaned job records
- Fix approach: Replace with ThreadPoolExecutor/ProcessPoolExecutor with shutdown(wait=True). Add job cancellation tokens. Track running jobs in database with heartbeat. Implement SIGTERM handler for graceful drain

**Direct `db.commit()` without transaction management:**
- Issue: Database operations manually call `db.commit()` 40+ times across `database.py` without rollback on error. Mix of explicit commits and auto-commit behavior
- Files: `backend/database.py` (lines 388, 423, 559, 627, 669, 701, 747, 762, 862, 871, 880, 999, 1063, 1075, 1089, 1097, 1180, 1236, 1287, 1352, 1413, 1430, 1501, 1513, 1606, 1617, 2067)
- Impact: Partial writes on exception leave database in inconsistent state. Multi-step operations (e.g., recording upgrade + deleting wanted item) not atomic. No rollback mechanism visible in error paths
- Fix approach: `transaction_manager.py` exists but underutilized. Wrap all DB write operations in `with transaction(db) as cursor:` context manager. Remove manual commits. Add integration tests verifying rollback behavior

**Legacy configuration fallback pattern:**
- Issue: `get_sonarr_instances()` and `get_radarr_instances()` support both new multi-instance JSON config and old single-instance config with complex fallback logic
- Files: `backend/config.py` (lines 332-357, 361-386)
- Impact: Config validation harder to reason about. Unclear when legacy path is used. Migration path ambiguous. Potential for config mismatches if both old and new configs partially set
- Fix approach: Deprecate legacy config in v2.0 with startup warning. Provide migration script converting old config to new JSON format. Simplify to single codepath after deprecation period

**Provider retry logic mixed with circuit breaker:**
- Issue: Providers have per-provider retry counts (`PROVIDER_RETRIES`), rate limits (`PROVIDER_RATE_LIMITS`), timeouts (`PROVIDER_TIMEOUTS`), AND circuit breakers. Overlapping failure-handling concerns
- Files: `backend/providers/__init__.py` (lines 70-93, 99, 136-187)
- Impact: Unclear which system handles which failure mode. Circuit breaker can open after retries exhausted, but retry logic unaware of circuit state. Complex interaction between `http_session.py` retry (HTTPAdapter), provider-level retry, and circuit breaker
- Fix approach: Consolidate into single resilience layer. Let circuit breaker handle failure threshold detection. Use http_session retry only for transient network errors. Remove provider-level retry duplication

**Translation validation insufficient:**
- Issue: `_call_ollama()` checks for CJK hallucinations but no validation for line count mismatch, empty responses, or model refusal to translate
- Files: `backend/ollama_client.py` (lines 26-28, 61-104)
- Impact: Batch translation of 15 lines returns 14 lines → silent failure or misaligned subtitles. Model responds with explanatory text instead of translations → invalid output written to file. English marker word detection (`ENGLISH_MARKER_WORDS`) in `translator.py` catches some cases but after full pipeline run
- Fix approach: Add strict line count validation before returning from `_call_ollama()`. Check for preamble/postamble ("Here are the translations:", "I translated..."). Add model output format enforcement (JSON structured output or strict line-by-line mode)

**Embedded subtitle extraction blocks Flask workers:**
- Issue: `extract_subtitle_stream()` calls `ffmpeg` with 60s timeout synchronously in request handler thread
- Files: `backend/ass_utils.py` (lines 381-404), called from `backend/translator.py`
- Impact: Large MKV files block worker thread during ffmpeg extraction. Gunicorn workers exhausted during batch processing. No concurrency limit on ffmpeg processes
- Fix approach: Move ffmpeg operations to background task queue (Celery/RQ). Add worker pool with max concurrency. Stream extraction progress via WebSocket. Return 202 Accepted immediately with job ID

**No WAL checkpoint management:**
- Issue: SQLite set to `PRAGMA journal_mode=WAL` but no explicit checkpointing strategy
- Files: `backend/database.py` (line 245)
- Impact: WAL file grows unbounded during high write load (batch translations, wanted scans). Checkpoint triggered only at connection close or 1000-page threshold. Slow startup after unclean shutdown due to WAL replay
- Fix approach: Add periodic `PRAGMA wal_checkpoint(TRUNCATE)` on scheduler. Monitor WAL size via `database_health.py`. Trigger checkpoint after batch operations complete

**ffprobe cache never expires:**
- Issue: `ffprobe_cache` table checks file mtime but no TTL-based expiration. Cache grows unbounded
- Files: `backend/database.py` (lines 167-174), `backend/ass_utils.py` (lines 322-378)
- Impact: Deleted/moved files leave orphaned cache entries. Database size grows proportionally to library size. No cleanup mechanism
- Fix approach: Add TTL column to `ffprobe_cache`, expire entries older than 30 days. Add cleanup task to `database_health.py`. Implement LRU eviction if cache exceeds size threshold

**Wanted scanner rescans entire library on startup:**
- Issue: `wanted_scan_on_startup=true` triggers full library scan (Sonarr + Radarr) synchronously during Flask app init if interval > 0
- Files: `backend/wanted_scanner.py` (lines 621-630)
- Impact: Application startup blocked until scan completes (5-30 minutes for large libraries). No progress indicator. Gunicorn timeout if scan exceeds `--timeout`
- Fix approach: Always run startup scan in background thread (never block). Add startup flag to API `/health` endpoint showing "warming up". Defer scheduler start until startup scan completes

**Provider cache sharing without locking:**
- Issue: `provider_cache` table queried/written from parallel provider threads via ThreadPoolExecutor but no transaction isolation
- Files: `backend/providers/__init__.py` (lines 402-480), `backend/database.py` (lines 54-60, 75-76)
- Impact: Race condition between cache check and insert. Duplicate cache entries for same query hash. Cache pollution during parallel searches
- Fix approach: Use `INSERT OR IGNORE` instead of `INSERT`. Wrap cache operations in `_db_lock`. Consider removing cache entirely (5-minute TTL insufficient for most use cases, adds complexity)

## Known Bugs

**AniDB mapping expires mid-translation:**
- Symptoms: Series with AniDB custom field fails provider search after 30 days since last use
- Files: `backend/database.py` (lines 2025-2069), `backend/anidb_mapper.py`
- Trigger: `anidb_cache_ttl_days` default 30, `last_used` updated only on read, mapping expires between scan and search
- Workaround: Set `anidb_cache_ttl_days=0` to disable expiration

**Threading.Timer reschedule race condition:**
- Symptoms: Wanted scanner stops running after first scheduled execution
- Files: `backend/wanted_scanner.py` (lines 655-684)
- Trigger: `_schedule_next_scan()` and `_schedule_next_search()` don't check if timer already running. Calling `stop_scheduler()` then `start_scheduler()` rapidly creates dangling timers
- Workaround: Restart application to reinitialize scheduler

**Webhook delay thread never cleans up:**
- Symptoms: Memory leak after processing many webhooks (Sonarr/Radarr)
- Files: `backend/server.py` (lines 1993-2010, 2057-2074)
- Trigger: Each webhook spawns daemon thread that sleeps for `webhook_delay_minutes`, runs job, exits. Thread objects accumulate in memory even after completion
- Workaround: Set `webhook_delay_minutes=0` to disable delay (process immediately)

**Batch translation empty returns "completed":**
- Symptoms: Batch translate reports "completed" but no subtitles created for some files
- Files: `backend/server.py` (lines 625-708), `backend/translator.py`
- Trigger: If all files in batch skip translation (Case A: target already exists), batch status updates to "completed" with success count 0. No distinction between "no work needed" and "all failed"
- Workaround: Check job error field. Success count 0 + empty error = nothing to do

**Provider circuit breaker stuck in OPEN:**
- Symptoms: Provider permanently disabled after network outage, never recovers
- Files: `backend/circuit_breaker.py` (lines 52-136)
- Trigger: Circuit opens after 5 consecutive failures (default). Transitions to HALF_OPEN after cooldown (60s), but if probe fails, returns to OPEN. No success bias or exponential backoff on cooldown
- Workaround: Restart application or call `/api/v1/providers/{name}/reset` (if endpoint exists, not found in review)

**Log file rotation missing:**
- Symptoms: `sublarr.log` grows unbounded, fills `/config` volume
- Files: `backend/server.py` (lines 98-112), log handler setup
- Trigger: SocketIOLogHandler emits to both file and WebSocket. File handler has no rotation. High-volume logging during batch operations
- Workaround: External logrotate or periodic manual truncation

## Security Considerations

**API key auth optional and weak:**
- Risk: API endpoints protected only if `SUBLARR_API_KEY` set. Empty key disables all auth. No rate limiting on auth attempts. HMAC comparison prevents timing attacks but no account lockout or logging
- Files: `backend/auth.py` (lines 67-89), `backend/server.py` (API Blueprint with `@require_api_key` decorator)
- Current mitigation: Designed for internal network use. No public exposure expected
- Recommendations: Add optional username/password auth with hashing. Add rate limiting via Flask-Limiter. Log failed auth attempts. Add session tokens for UI (currently relies on stateless API key in every request)

**Path traversal in map_path:**
- Risk: `SUBLARR_PATH_MAPPING` accepts arbitrary prefixes. Malicious config could map `/data/media=../../etc` to expose system files
- Files: `backend/config.py` (lines 210-240)
- Current mitigation: Path mapping applied only to paths from trusted *arr instances. No user input directly sets mappings
- Recommendations: Validate mapped paths stay within `SUBLARR_MEDIA_PATH`. Reject mappings with `..` or absolute paths outside allowed directories. Add security audit log for unusual path access

**Secrets logged in error messages:**
- Risk: Exception tracebacks may contain Ollama API URLs with auth tokens, provider API keys, or database paths with credentials
- Files: `backend/error_handler.py` (lines 37-120), Flask error handlers return full context in debug mode
- Current mitigation: Secrets redacted in `get_safe_config()`. Exception context filtering in `SublarrError` classes
- Recommendations: Add secret scrubbing to all log output (regex for common patterns like `api_key=`, `password=`, `token=`). Audit all `logger.exception()` calls for sensitive context. Never return raw exceptions to API clients

**No HTTPS/TLS support:**
- Risk: All API traffic (including API keys) sent in plaintext. Vulnerable to MITM in home network
- Files: Entire application (Flask runs HTTP only)
- Current mitigation: Intended for internal network use behind reverse proxy (NPM on Unraid-2)
- Recommendations: Document reverse proxy requirement in README. Add TLS support via Flask-Talisman for standalone deployments. Warn if API key set but not behind HTTPS

**Provider API keys stored in plaintext database:**
- Risk: `config_entries` table stores provider API keys as plaintext TEXT values
- Files: `backend/database.py` (lines 47-51), `backend/config.py` (Settings class)
- Current mitigation: SQLite database file permissions restrict access. No remote database exposure
- Recommendations: Encrypt sensitive config values at rest using Fernet (cryptography library). Store encryption key in environment variable separate from database. Transparent decryption on load

**Arbitrary file write via translation output:**
- Risk: `get_output_path()` builds subtitle paths from `mkv_path` + language extension. No validation that output stays within media directory
- Files: `backend/translator.py` (lines 61-73)
- Current mitigation: Input `mkv_path` comes from trusted sources (*arr APIs or local filesystem scan). Path mapping applied before reaching this function
- Recommendations: Validate output path resolves within `SUBLARR_MEDIA_PATH`. Reject if `os.path.commonpath()` differs from media root. Add allowlist for subtitle extensions (`.ass`, `.srt` only)

**Ollama model injection:**
- Risk: `SUBLARR_OLLAMA_MODEL` setting accepts arbitrary model names. Could trigger unintended model downloads or exploit Ollama vulnerabilities
- Files: `backend/config.py` (line 28), `backend/ollama_client.py` (lines 31-58 health check)
- Current mitigation: Health check validates model exists before use. Ollama API access restricted to configured URL
- Recommendations: Maintain allowlist of approved models. Reject model names with path traversal (`../`) or special characters. Add model fingerprint verification if Ollama API supports it

## Performance Bottlenecks

**Synchronous LLM translation:**
- Problem: `translate_all()` sends batches sequentially to Ollama with 90s timeout per batch. 500-line subtitle = 34 batches × 90s = 51 minutes worst case
- Files: `backend/ollama_client.py` (lines 148-322)
- Cause: Single-threaded request loop with exponential backoff on retry. Ollama API supports streaming but not utilized. Batch size fixed at 15 lines regardless of line length
- Improvement path: Stream responses via `/api/generate` with `stream=true`. Process response chunks as they arrive. Increase batch size for short lines (< 50 chars). Add async/await for parallel batch processing

**Provider search serial within priority order:**
- Problem: 4 providers searched in priority order (animetosho → jimaku → opensubtitles → subdl). Each waits for previous to complete before starting
- Files: `backend/providers/__init__.py` (lines 402-480)
- Cause: ThreadPoolExecutor used but `as_completed()` processes results in submission order, not completion order. First provider timeout (20s) delays all subsequent providers
- Improvement path: Search all enabled providers in parallel, merge results by score, take top match. Add early termination if high-score match found (e.g., hash match = 359 points, stop search)

**Wanted scanner N+1 queries:**
- Problem: Full library scan iterates all series → episodes → episode files. Each step queries Sonarr/Radarr API individually
- Files: `backend/wanted_scanner.py` (lines 71-545)
- Cause: No bulk API endpoints used. `get_series_episodes()` called per series instead of `/api/v3/episode?seriesId=...` batch query. Episode file path checked one at a time
- Improvement path: Use Sonarr `/api/v3/wanted/missing` endpoint directly (pre-filtered). Batch episode file checks via filesystem scan. Cache series metadata to avoid repeated API calls

**Database contention during batch operations:**
- Problem: Batch translation updates `jobs` table every 5-10 seconds from background threads while API serves `/api/v1/jobs` queries
- Files: `backend/database.py` (shared `_db_lock`), `backend/server.py` (jobs table heavy during batch)
- Cause: SQLite WAL mode allows concurrent reads but single writer. `_db_lock` ensures thread-safety but blocks all DB operations during write. High update frequency during translation creates lock contention
- Improvement path: Reduce job update frequency (every 30s instead of per-file). Use `IMMEDIATE` transactions to reduce lock hold time. Move to PostgreSQL if scaling beyond single instance. Add read replicas for queries

**pysubs2 parse/save overhead:**
- Problem: Every subtitle operation loads full ASS file into memory, parses styles/events, modifies, writes back
- Files: `backend/translator.py` (pysubs2 used throughout), `backend/ass_utils.py` (classify_styles, extract_tags, restore_tags)
- Cause: pysubs2 library parses entire file on load. 5000-event subtitle = 500KB text, 50ms parse time. Batch of 100 episodes = 5 seconds just parsing
- Improvement path: Cache parsed pysubs2.SSAFile objects keyed by (file_path, mtime). Stream-process large files (read events incrementally, translate batch, append to output). Consider switching to faster parser (libass bindings)

## Fragile Areas

**ASS style classification heuristic:**
- Files: `backend/ass_utils.py` (lines 103-153)
- Why fragile: Classifies styles as Dialog vs Signs/Songs based on \\pos() and \\move() tag frequency (> 80% threshold). Breaks for anime with frequent on-screen text in dialog (e.g., text message overlays). No fallback if classification ambiguous
- Safe modification: Add manual style override config (`signs_style_names`, `dialog_style_names`). Increase threshold to 90%. Add fuzzy style name matching ("Sign", "OP", "ED" keywords)
- Test coverage: `backend/tests/test_ass_utils.py` covers basic cases but no edge cases (50/50 split, empty styles, all-tagged dialog)

**Translation line-break restoration:**
- Files: `backend/translator.py` (lines 300-450), `backend/ass_utils.py` (`extract_tags`, `restore_tags`)
- Why fragile: ASS `\\N` hard line breaks extracted before translation, restored after. Regex assumes `\\N` never appears in dialogue text itself. Tag extraction/restoration order-dependent (tags must match line-by-line)
- Safe modification: Test extensively with `\\N` in character names or lyrics. Add validation that tag extraction and restoration produce same line count. Never modify tag extraction without corresponding restoration change
- Test coverage: Basic tests exist but no adversarial inputs (nested tags, malformed ASS, Unicode edge cases)

**Provider download archive extraction:**
- Files: `backend/providers/animetosho.py` (XZ extraction), `backend/providers/jimaku.py` (ZIP/RAR extraction), `backend/providers/subdl.py` (ZIP extraction)
- Why fragile: Archive formats assume single .ass or .srt file at root. Nested directories or multiple files cause silent failure. No validation of extracted content. RAR format requires external `unrar` binary
- Safe modification: Add archive structure validation before extraction. Handle nested directories recursively. Validate extracted file is valid subtitle format (pysubs2 parse). Return error if multiple candidate files found
- Test coverage: Integration tests use mock provider responses, not real archives

**Webhook delay timer accumulation:**
- Files: `backend/server.py` (lines 1993-2010 Sonarr, 2057-2074 Radarr)
- Why fragile: Each webhook creates 5-minute timer thread. Burst of 100 webhooks = 100 threads sleeping simultaneously. No deduplication if same episode updated multiple times
- Safe modification: Use single timer thread with queue of pending webhooks. Deduplicate by episode ID (last webhook wins). Add max queue depth with backpressure
- Test coverage: No webhook stress tests, only single-webhook happy path

**Config reload race condition:**
- Files: `backend/config.py` (lines 290-328 `reload_settings()`), `backend/server.py` (PUT `/api/v1/library/config` triggers reload)
- Why fragile: `reload_settings()` creates new Settings object and swaps `_settings` global. Background threads may read old settings mid-swap. Provider manager holds stale settings reference. No locking during reload
- Safe modification: Add `_settings_lock` around reload. Invalidate all cached objects (provider manager, scanner, etc.). Return 503 Service Unavailable during reload. Add atomic config validation before applying changes
- Test coverage: No concurrency tests for config reload

## Scaling Limits

**Single SQLite database:**
- Current capacity: 10K-50K episodes, 100K subtitle files, < 1TB media library
- Limit: WAL write throughput ~1000 ops/sec (constrained by disk fsync). Concurrent writers blocked by `_db_lock`. Database file grows to multiple GB (no compaction strategy)
- Scaling path: Migrate to PostgreSQL for multi-user deployments. Shard by series ID if single DB exceeds 10GB. Add read replicas for query scaling. Consider Redis for high-write tables (`jobs`, `provider_cache`)

**ThreadPoolExecutor for provider search:**
- Current capacity: 4 providers, 15s timeout each = worst case 60s if all timeout (parallel execution prevents)
- Limit: Python GIL limits actual parallelism. Adding 10+ providers would exhaust thread pool (default max_workers=4). Timeout handling inconsistent across providers
- Scaling path: Use ProcessPoolExecutor to bypass GIL. Add provider priority tiers (search tier 1 providers, only try tier 2 if no results). Implement provider circuit breaker aggregation (disable tier if success rate < 20%)

**In-memory WebSocket log buffer:**
- Current capacity: `log_buffer` deque (size unknown, likely unbounded)
- Limit: `SocketIOLogHandler` appends every log entry to memory buffer. Long-running instance with DEBUG logging = OOM risk. No client-side backpressure if WebSocket slow
- Scaling path: Limit buffer to 1000 entries. Add overflow flag and notify client "logs truncated". Use external log aggregator (Loki) for persistent history. Add log level filtering at handler level

**Synchronous ffmpeg calls:**
- Current capacity: 10-20 concurrent extractions before worker pool exhausted
- Limit: Gunicorn default 4 workers × 1 ffmpeg per request = 4 parallel extractions. Large MKV (50GB) takes 60s to extract → all workers blocked
- Scaling path: Move to background task queue (Celery with Redis backend). Add worker pool dedicated to ffmpeg operations (isolated from API workers). Stream subtitle extraction progress via chunked HTTP response or WebSocket

## Dependencies at Risk

**pysubs2:**
- Risk: Last updated 2023, minimal maintenance activity. No async support. Inefficient for large files
- Impact: Core subtitle parsing/writing depends on this library. No drop-in replacement with same API. Migration would require rewriting entire translation pipeline
- Migration plan: Evaluate alternatives (ass-parser, libass Python bindings). Add abstraction layer (`subtitle_parser.py`) wrapping pysubs2 to enable future swaps. Consider contributing upstream fixes if bugs found

**Flask-SocketIO:**
- Risk: WebSocket support depends on simple-websocket backend (single-threaded). Eventlet/gevent not used (compatibility with gunicorn)
- Impact: WebSocket connections limited by single-thread performance. Log streaming may drop messages under high load
- Migration plan: Add optional redis message queue for Socket.IO clustering. Consider switching to FastAPI + WebSockets for async support. Document gunicorn `--worker-class gevent` requirement if using eventlet

**rarfile:**
- Risk: Requires external `unrar` binary (not pure Python). Licensing restrictions on UnRAR source. Archive format used by Jimaku provider
- Impact: Jimaku provider fails if `unrar` not in PATH. Docker image must include unrar-free or non-free variant (GPL compatibility issue)
- Migration plan: Prefer ZIP archives from providers. Add provider config to reject RAR downloads. Fall back to subprocess `unrar` if rarfile import fails

## Test Coverage Gaps

**Translation pipeline integration:**
- What's not tested: Case B1 (SRT→ASS upgrade via provider search), Case C2 (embedded subtitle extraction failure recovery)
- Files: `backend/translator.py` (lines 400-800), `backend/tests/integration/test_translator_pipeline.py` (covers basic cases only)
- Risk: Provider search called during upgrade path but no tests verify correct scoring and download. Fallback logic between embedded→provider→translate not validated end-to-end
- Priority: High

**Webhook processing under load:**
- What's not tested: Burst of 100 webhooks from Sonarr. Duplicate webhooks for same episode. Webhook received during active batch translation
- Files: `backend/server.py` (lines 1900-2100), no webhook stress tests exist
- Risk: Memory leak from timer thread accumulation. Race condition between webhook and manual search. Duplicate wanted items created
- Priority: Medium

**Provider circuit breaker state transitions:**
- What's not tested: OPEN → HALF_OPEN → CLOSED cycle. Multiple probe failures extending cooldown. Circuit breaker interaction with retry logic
- Files: `backend/circuit_breaker.py`, no integration tests for circuit breaker exist
- Risk: Provider permanently stuck in OPEN state. Cooldown timer never resets. Thread safety of state transitions
- Priority: High

**Database backup under write load:**
- What's not tested: Backup triggered during batch translation. Restore while application running. Backup rotation cleanup edge cases (exactly N backups)
- Files: `backend/database_backup.py`, basic tests exist but no load testing
- Risk: Backup corruption if concurrent writes occur. WAL checkpoint fails during backup. Restore overwrites active database
- Priority: Medium

**Config reload during active translation:**
- What's not tested: Change `SUBLARR_OLLAMA_MODEL` mid-batch. Update provider priorities during provider search. Disable provider while circuit breaker in HALF_OPEN
- Files: `backend/config.py`, no concurrency tests
- Risk: Stale settings used by background threads. Provider manager references deallocated session objects. Job completion uses wrong config hash
- Priority: High

**ffprobe cache invalidation:**
- What's not tested: File modified externally (same path, different content). Race between cache check and ffprobe call. Cache entry with invalid JSON
- Files: `backend/database.py` (ffprobe cache functions), `backend/ass_utils.py` (run_ffprobe)
- Risk: Stale probe data returns wrong stream info. Cache poisoned with malformed JSON crashes parser. mtime collision returns wrong cached result
- Priority: Low

---

*Concerns audit: 2026-02-15*
