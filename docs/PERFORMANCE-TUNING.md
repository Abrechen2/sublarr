# Performance Tuning

Sublarr performs well out of the box, but there are several knobs available for large libraries or resource-constrained environments.

---

## LLM Translation Speed

Translation speed depends almost entirely on the LLM backend.

### Use GPU Acceleration

If you have a GPU, ensure Ollama uses it:

```bash
# Verify GPU is detected
ollama run qwen2.5:7b-instruct "hello" --verbose
# Look for "using GPU" in output
```

GPU translation is typically 10-20x faster than CPU.

### Choose the Right Model Size

| Model | VRAM Required | Speed | Quality |
|---|---|---|---|
| 3B models | ~2.5GB | Very fast | Acceptable |
| 7B models | ~5GB | Fast | Very good |
| 14B models | ~9GB | Medium | Excellent |
| 32B models | ~20GB | Slow | Best |

For most anime translation workflows, `qwen2.5:7b-instruct` is the best speed/quality trade-off.

### Increase Batch Size

Larger batches reduce the number of LLM calls:

```
SUBLARR_BATCH_SIZE=25
```

Risk: larger batches may hit context window limits for very long episodes. If you see truncated translations, reduce to 15.

### Translation Memory

Enable translation memory to skip re-translating identical lines:

Configure in **Settings → Translation → Translation Memory**. For series with consistent dialogue patterns (slice-of-life, long-running shows), this can reduce translation time by 30-60%.

---

## Provider Search Speed

### Parallel Provider Search

Providers are searched in parallel by default. The effective speed is limited by the slowest responding provider.

Disable slow providers if you do not use them:
- Go to **Settings → Providers**
- Toggle off providers you never use

### Tune Dynamic Timeouts

```
SUBLARR_PROVIDER_DYNAMIC_TIMEOUT_ENABLED=true
SUBLARR_PROVIDER_DYNAMIC_TIMEOUT_MIN_SAMPLES=5
SUBLARR_PROVIDER_DYNAMIC_TIMEOUT_MULTIPLIER=2.0
```

Lowering the multiplier from 3.0 to 2.0 makes timed-out providers fail faster. Only do this if your network connection to providers is stable.

### Provider Cache

Repeat searches within the cache TTL return instant results:

```
SUBLARR_PROVIDER_CACHE_TTL_MINUTES=10
```

Increasing this is safe — search results do not change that quickly.

---

## Wanted Scanner

The wanted scanner is the most I/O-intensive operation. It runs ffprobe on every video file to detect embedded subtitles.

### Reduce Worker Count

```
SUBLARR_SCAN_METADATA_MAX_WORKERS=2
```

Default is 4. Reducing this lowers CPU and I/O pressure at the cost of slower scans.

### Increase Scan Interval

```
SUBLARR_WANTED_SCAN_INTERVAL_HOURS=12
```

For libraries that rarely change, scanning every 12-24 hours is fine.

### Adaptive Backoff

```
SUBLARR_WANTED_ADAPTIVE_BACKOFF_ENABLED=true
SUBLARR_WANTED_BACKOFF_BASE_HOURS=2.0
SUBLARR_WANTED_BACKOFF_CAP_HOURS=168
```

Items that fail repeatedly are retried less frequently, reducing load from hopeless searches.

---

## Database

### SQLite Tuning (default)

SQLite performs well for most use cases. WAL mode is enabled by default for better concurrency.

For large libraries (1000+ series):

1. Run `VACUUM` periodically via Settings → System → Maintenance
2. Enable incremental scanning (only rescans changed files)
3. Consider migrating to PostgreSQL

### PostgreSQL Migration

For libraries over 1000 series or when running multiple processes:

```
SUBLARR_DATABASE_URL=postgresql://sublarr:password@postgres:5432/sublarr
```

PostgreSQL benefits:
- Better concurrency (multiple workers)
- Row-level locking (no full-table locks)
- Better query planner for complex filters
- Native JSON operators for JSON columns

Run the migration with the provided migration script:

```bash
python3 backend/scripts/migrate_sqlite_to_postgres.py   --sqlite /config/sublarr.db   --postgres postgresql://sublarr:pass@postgres:5432/sublarr
```

---

## Redis (Advanced)

Redis enables distributed caching and job queues. Useful when:
- Running multiple Sublarr instances
- Offloading provider search cache from SQLite
- Using RQ for background job processing

```
SUBLARR_REDIS_URL=redis://redis:6379/0
SUBLARR_REDIS_CACHE_ENABLED=true
SUBLARR_REDIS_QUEUE_ENABLED=true
```

Without Redis, Sublarr uses in-memory caches and SQLite-backed job tracking, which is sufficient for single-instance deployments.

---

## Docker Resource Limits

Recommended resource limits for typical use:

```yaml
deploy:
  resources:
    limits:
      cpus: '2.0'
      memory: 2G
    reservations:
      cpus: '0.5'
      memory: 512M
```

During active translation jobs, CPU usage spikes to the Ollama container, not Sublarr itself. Sublarr's own memory usage is typically 200-400MB.

---

## Single Gunicorn Worker Requirement

Sublarr uses Flask-SocketIO for WebSocket communication. Flask-SocketIO requires a single Gunicorn worker for state consistency. Do not increase `--workers` — it will break WebSocket sessions.

If you need higher throughput, use Redis + multiple processes with a Redis-backed Socket.IO adapter (advanced setup, not officially supported yet).

---

## Logging

Reduce log verbosity to INFO or WARNING in production:

```
SUBLARR_LOG_LEVEL=INFO
```

DEBUG logging can significantly increase disk I/O on busy systems. Use `json` format for structured log aggregation:

```
SUBLARR_LOG_FORMAT=json
```

---

## Monitoring

The health endpoint provides performance metrics:

```bash
curl http://localhost:5765/api/v1/health/detailed
```

Subsystem categories reported:
- Provider health (success rates, response times)
- Translation backend health
- Media server connectivity
- Whisper backend status
- Scheduler status
- Database health

Use these metrics with Prometheus or Uptime Kuma to alert on degradation.
