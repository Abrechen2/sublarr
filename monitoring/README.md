# Sublarr Monitoring

Pre-built Prometheus metrics and Grafana dashboards for monitoring Sublarr performance, database health, cache efficiency, and provider status.

## Quick Start

### 1. Enable Prometheus scraping

Sublarr exposes metrics at `GET /metrics` (unauthenticated). Add a scrape target to your `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: "sublarr"
    scrape_interval: 30s
    static_configs:
      - targets: ["sublarr:5765"]
```

### 2. Provision Grafana dashboards

Mount the `monitoring/grafana/` directory into your Grafana container:

```yaml
# docker-compose.yml excerpt
grafana:
  image: grafana/grafana:latest
  volumes:
    - ./monitoring/grafana/provisioning:/etc/grafana/provisioning
    - ./monitoring/grafana/dashboards:/var/lib/grafana/dashboards
```

The dashboards will be auto-imported on Grafana startup under the "Sublarr" folder.

### 3. Full example with Docker Compose

```yaml
services:
  sublarr:
    image: sublarr:latest
    ports:
      - "5765:5765"
    volumes:
      - ./config:/config
      - /path/to/media:/media
    environment:
      - SUBLARR_REDIS_URL=redis://redis:6379/0  # optional

  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    command:
      - "--config.file=/etc/prometheus/prometheus.yml"

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    volumes:
      - ./monitoring/grafana/provisioning:/etc/grafana/provisioning
      - ./monitoring/grafana/dashboards:/var/lib/grafana/dashboards
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin

  redis:  # optional -- Sublarr falls back to in-memory when unavailable
    image: redis:7-alpine
```

## Dashboards

### Sublarr Overview (`sublarr-overview`)

Main operational dashboard with four sections:

- **System Overview** -- Translation operation rates (success/failed/skipped) and active job count
- **Provider Performance** -- Search and download rates per provider with status breakdown
- **HTTP API** -- Request duration percentiles (p95) and request rate by status code
- **System Resources** -- CPU usage gauge, memory usage, database size, circuit breaker states

### Sublarr Database (`sublarr-database`)

Database-focused dashboard for performance tuning:

- **Connection Pool** -- Pool size, checked-out connections, overflow count, pool utilization percentage
- **Query Performance** -- Query duration percentiles (p95) by operation type, query rate by operation
- **Cache** -- Cache hit rate gauge, cache size by backend
- **Redis & Queue** (collapsed) -- Redis connection status, Redis memory usage, queue depth over time

## Metric Reference

All metrics use the `sublarr_` prefix.

### System Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `sublarr_cpu_usage_percent` | Gauge | -- | CPU usage percentage |
| `sublarr_memory_usage_bytes` | Gauge | -- | Process memory usage (RSS) in bytes |
| `sublarr_disk_usage_percent` | Gauge | `mount` | Disk usage percentage |

### HTTP Request Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `sublarr_http_request_duration_seconds` | Histogram | `method`, `endpoint`, `status` | HTTP request duration |
| `sublarr_http_requests_total` | Counter | `method`, `endpoint`, `status` | Total HTTP requests |
| `sublarr_http_requests_in_progress` | Gauge | -- | Requests currently being processed |

### Database Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `sublarr_database_size_bytes` | Gauge | -- | Database file size |
| `sublarr_db_query_duration_seconds` | Histogram | `operation` | Query duration by operation |
| `sublarr_db_queries_total` | Counter | `operation` | Total queries by operation |
| `sublarr_db_pool_size` | Gauge | -- | Connection pool size |
| `sublarr_db_pool_checked_out` | Gauge | -- | Connections currently in use |
| `sublarr_db_pool_overflow` | Gauge | -- | Pool overflow count |
| `sublarr_db_backend_info` | Info | -- | Database backend dialect |

### Translation Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `sublarr_translation_total` | Counter | `status`, `format` | Translation operations |
| `sublarr_translation_duration_seconds` | Histogram | -- | Translation duration |

### Provider Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `sublarr_provider_search_total` | Counter | `provider`, `status` | Provider search operations |
| `sublarr_provider_download_total` | Counter | `provider`, `format` | Provider download operations |
| `sublarr_circuit_breaker_state` | Gauge | `provider` | Circuit breaker state (0=closed, 1=open, 2=half_open) |

### Cache Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `sublarr_cache_hits_total` | Counter | `backend` | Cache hits |
| `sublarr_cache_misses_total` | Counter | `backend` | Cache misses |
| `sublarr_cache_size` | Gauge | `backend` | Number of cached items |

### Redis Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `sublarr_redis_connected` | Gauge | -- | Connection status (1=connected, 0=disconnected) |
| `sublarr_redis_memory_used_bytes` | Gauge | -- | Redis memory usage |

### Queue Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `sublarr_job_queue_size` | Gauge | -- | Queued translation jobs |
| `sublarr_wanted_queue_size` | Gauge | -- | Wanted subtitle items |
| `sublarr_queue_size` | Gauge | `backend` | Jobs in queue by backend |
| `sublarr_queue_active_jobs` | Gauge | `backend` | Actively running jobs |
| `sublarr_queue_failed_jobs` | Gauge | `backend` | Failed jobs |

### Application Info

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `sublarr_info` | Info | -- | Application version and build info |

## Requirements

Metrics are only exposed when `prometheus_client` and `psutil` are installed. Both are included in the default Docker image. Without these packages, the `/metrics` endpoint returns a plain text message indicating metrics are unavailable.

```bash
pip install prometheus_client psutil
```

## Notes

- The `/metrics` endpoint is unauthenticated by design (standard for Prometheus scraping)
- Dashboard JSON files use the `${DS_PROMETHEUS}` variable for datasource -- Grafana auto-resolves this when using provisioning
- The Redis & Queue row on the database dashboard is collapsed by default (shown only when Redis is active)
- All histogram buckets are tuned for typical Sublarr workloads (sub-second for DB queries, multi-second for HTTP requests)
