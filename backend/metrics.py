"""Prometheus metrics for Sublarr monitoring.

Exposes system, business, queue, database, cache, Redis, HTTP, and resilience metrics.
Scraped via ``GET /metrics`` (unauthenticated, for Prometheus).

Requires: ``prometheus_client``, ``psutil``
"""

import logging
import os

try:
    import psutil
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        REGISTRY,
        CollectorRegistry,  # noqa: F401 — imported for type hints in callers
        Counter,
        Gauge,
        Histogram,
        Info,
        generate_latest,
    )

    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False

logger = logging.getLogger(__name__)

# -- Metric Definitions -------------------------------------------------------

if METRICS_AVAILABLE:
    # System
    CPU_USAGE = Gauge("sublarr_cpu_usage_percent", "CPU usage percentage")
    MEMORY_USAGE = Gauge("sublarr_memory_usage_bytes", "Memory usage in bytes")
    DISK_USAGE = Gauge("sublarr_disk_usage_percent", "Disk usage percentage for /config", ["mount"])

    # Business -- translation
    TRANSLATION_TOTAL = Counter(
        "sublarr_translation_total",
        "Total translation operations",
        ["status", "format"],
    )
    TRANSLATION_DURATION = Histogram(
        "sublarr_translation_duration_seconds",
        "Translation duration in seconds",
        buckets=(1, 5, 10, 30, 60, 120, 300, 600),
    )

    # Business -- providers
    PROVIDER_SEARCH_TOTAL = Counter(
        "sublarr_provider_search_total",
        "Provider search operations",
        ["provider", "status"],
    )
    PROVIDER_DOWNLOAD_TOTAL = Counter(
        "sublarr_provider_download_total",
        "Provider download operations",
        ["provider", "format"],
    )

    # Queue (legacy)
    JOB_QUEUE_SIZE = Gauge("sublarr_job_queue_size", "Number of queued translation jobs")
    WANTED_QUEUE_SIZE = Gauge("sublarr_wanted_queue_size", "Number of wanted subtitle items")

    # Database
    DATABASE_SIZE = Gauge("sublarr_database_size_bytes", "SQLite database file size")

    # Resilience
    CIRCUIT_BREAKER_STATE = Gauge(
        "sublarr_circuit_breaker_state",
        "Circuit breaker state (0=closed, 1=open, 2=half_open)",
        ["provider"],
    )

    # App info
    APP_INFO = Info("sublarr", "Sublarr application information")

    # ── HTTP Request Metrics ─────────────────────────────────────────────────
    HTTP_REQUEST_DURATION = Histogram(
        "sublarr_http_request_duration_seconds",
        "HTTP request duration",
        ["method", "endpoint", "status"],
        buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    )
    HTTP_REQUEST_TOTAL = Counter(
        "sublarr_http_requests_total",
        "Total HTTP requests",
        ["method", "endpoint", "status"],
    )
    HTTP_REQUESTS_IN_PROGRESS = Gauge(
        "sublarr_http_requests_in_progress",
        "HTTP requests currently being processed",
    )

    # ── Database Query Metrics ───────────────────────────────────────────────
    DB_QUERY_DURATION = Histogram(
        "sublarr_db_query_duration_seconds",
        "Database query duration",
        ["operation"],  # select, insert, update, delete
        buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5),
    )
    DB_QUERY_TOTAL = Counter(
        "sublarr_db_queries_total",
        "Total database queries",
        ["operation"],
    )
    DB_POOL_SIZE = Gauge(
        "sublarr_db_pool_size",
        "Database connection pool current size",
    )
    DB_POOL_CHECKED_OUT = Gauge(
        "sublarr_db_pool_checked_out",
        "Database connections currently checked out",
    )
    DB_POOL_OVERFLOW = Gauge(
        "sublarr_db_pool_overflow",
        "Database connection pool overflow count",
    )
    DB_BACKEND = Info(
        "sublarr_db_backend",
        "Database backend information",
    )

    # ── Cache Metrics ────────────────────────────────────────────────────────
    CACHE_HITS_TOTAL = Counter(
        "sublarr_cache_hits_total",
        "Cache hit counter",
        ["backend"],  # redis, memory
    )
    CACHE_MISSES_TOTAL = Counter(
        "sublarr_cache_misses_total",
        "Cache miss counter",
        ["backend"],
    )
    CACHE_SIZE = Gauge(
        "sublarr_cache_size",
        "Number of items in cache",
        ["backend"],
    )

    # ── Redis Metrics ────────────────────────────────────────────────────────
    REDIS_CONNECTED = Gauge(
        "sublarr_redis_connected",
        "Redis connection status (1=connected, 0=disconnected)",
    )
    REDIS_MEMORY_USED = Gauge(
        "sublarr_redis_memory_used_bytes",
        "Redis memory usage in bytes",
    )

    # ── Queue Backend Metrics ────────────────────────────────────────────────
    QUEUE_SIZE = Gauge(
        "sublarr_queue_size",
        "Number of jobs in queue",
        ["backend"],  # rq, memory
    )
    QUEUE_ACTIVE = Gauge(
        "sublarr_queue_active_jobs",
        "Number of actively running jobs",
        ["backend"],
    )
    QUEUE_FAILED = Gauge(
        "sublarr_queue_failed_jobs",
        "Number of failed jobs",
        ["backend"],
    )


# -- Collection helpers --------------------------------------------------------


def collect_system_metrics() -> None:
    """Update system resource gauges."""
    if not METRICS_AVAILABLE:
        return

    try:
        CPU_USAGE.set(psutil.cpu_percent(interval=None))
        process = psutil.Process()
        MEMORY_USAGE.set(process.memory_info().rss)

        for path, label in [("/config", "config"), ("/media", "media")]:
            try:
                usage = psutil.disk_usage(path)
                DISK_USAGE.labels(mount=label).set(usage.percent)
            except (FileNotFoundError, OSError):
                pass
    except Exception as exc:
        logger.debug("Failed to collect system metrics: %s", exc)


def collect_queue_metrics() -> None:
    """Update queue gauges from the database."""
    if not METRICS_AVAILABLE:
        return

    try:
        from db.jobs import get_pending_job_count
        from db.wanted import get_wanted_summary

        JOB_QUEUE_SIZE.set(get_pending_job_count())
        summary = get_wanted_summary()
        WANTED_QUEUE_SIZE.set(summary.get("wanted", 0))
    except Exception as exc:
        logger.debug("Failed to collect queue metrics: %s", exc)


def collect_database_metrics(db_path: str) -> None:
    """Update database size gauge."""
    if not METRICS_AVAILABLE:
        return

    try:
        if os.path.exists(db_path):
            DATABASE_SIZE.set(os.path.getsize(db_path))
    except Exception:
        pass


def collect_circuit_breaker_metrics() -> None:
    """Update circuit breaker state gauges."""
    if not METRICS_AVAILABLE:
        return

    try:
        from providers import get_provider_manager

        manager = get_provider_manager()
        state_map = {"closed": 0, "open": 1, "half_open": 2}
        for name, cb in manager._circuit_breakers.items():
            CIRCUIT_BREAKER_STATE.labels(provider=name).set(state_map.get(cb.state.value, -1))
    except Exception as exc:
        logger.debug("Failed to collect circuit breaker metrics: %s", exc)


def collect_db_pool_metrics() -> None:
    """Update database connection pool gauges."""
    if not METRICS_AVAILABLE:
        return
    try:
        from extensions import db as sa_db

        pool = sa_db.engine.pool
        # NullPool (SQLite) doesn't have these attrs
        if hasattr(pool, "size"):
            DB_POOL_SIZE.set(pool.size())
            DB_POOL_CHECKED_OUT.set(pool.checkedout())
            DB_POOL_OVERFLOW.set(pool.overflow())
        DB_BACKEND.info({"dialect": sa_db.engine.dialect.name})
    except Exception as exc:
        logger.debug("Failed to collect DB pool metrics: %s", exc)


def collect_cache_metrics() -> None:
    """Update cache gauges from app cache backend."""
    if not METRICS_AVAILABLE:
        return
    try:
        from flask import current_app

        cache = getattr(current_app, "cache_backend", None)
        if cache:
            stats = cache.get_stats()
            backend = stats.get("backend", "unknown")
            CACHE_HITS_TOTAL.labels(backend=backend)  # ensure label initialized
            CACHE_SIZE.labels(backend=backend).set(stats.get("size", 0))
    except Exception:
        pass


def collect_redis_metrics() -> None:
    """Update Redis connection and memory gauges."""
    if not METRICS_AVAILABLE:
        return
    try:
        from flask import current_app

        cache = getattr(current_app, "cache_backend", None)
        if cache and hasattr(cache, "redis"):
            REDIS_CONNECTED.set(1)
            info = cache.redis.info("memory")
            REDIS_MEMORY_USED.set(info.get("used_memory", 0))
        else:
            REDIS_CONNECTED.set(0)
    except Exception:
        REDIS_CONNECTED.set(0)


def collect_queue_job_metrics() -> None:
    """Update queue depth gauges from app job queue."""
    if not METRICS_AVAILABLE:
        return
    try:
        from flask import current_app

        queue = getattr(current_app, "job_queue", None)
        if queue:
            info = queue.get_backend_info()
            backend = info.get("type", "unknown")
            QUEUE_SIZE.labels(backend=backend).set(queue.get_queue_length())
            QUEUE_ACTIVE.labels(backend=backend).set(len(queue.get_active_jobs()))
            QUEUE_FAILED.labels(backend=backend).set(len(queue.get_failed_jobs(100)))
    except Exception:
        pass


# -- Recording helpers ---------------------------------------------------------


def record_translation(status: str, fmt: str, duration: float) -> None:
    """Record a translation operation."""
    if not METRICS_AVAILABLE:
        return
    TRANSLATION_TOTAL.labels(status=status, format=fmt).inc()
    TRANSLATION_DURATION.observe(duration)


def record_provider_search(provider: str, status: str) -> None:
    """Record a provider search operation."""
    if not METRICS_AVAILABLE:
        return
    PROVIDER_SEARCH_TOTAL.labels(provider=provider, status=status).inc()


def record_provider_download(provider: str, fmt: str) -> None:
    """Record a provider download operation."""
    if not METRICS_AVAILABLE:
        return
    PROVIDER_DOWNLOAD_TOTAL.labels(provider=provider, format=fmt).inc()


def record_http_request(method: str, endpoint: str, status: str, duration: float) -> None:
    """Record an HTTP request metric."""
    if not METRICS_AVAILABLE:
        return
    HTTP_REQUEST_DURATION.labels(method=method, endpoint=endpoint, status=status).observe(duration)
    HTTP_REQUEST_TOTAL.labels(method=method, endpoint=endpoint, status=status).inc()


def record_db_query(operation: str, duration: float) -> None:
    """Record a database query metric."""
    if not METRICS_AVAILABLE:
        return
    DB_QUERY_DURATION.labels(operation=operation).observe(duration)
    DB_QUERY_TOTAL.labels(operation=operation).inc()


# -- Endpoint helper -----------------------------------------------------------


def generate_metrics(db_path: str) -> tuple[bytes, str]:
    """Collect all metrics and return Prometheus text output.

    Returns:
        (body_bytes, content_type)
    """
    if not METRICS_AVAILABLE:
        return b"# prometheus_client not installed\n", "text/plain"

    collect_system_metrics()
    collect_queue_metrics()
    collect_database_metrics(db_path)
    collect_circuit_breaker_metrics()
    collect_db_pool_metrics()
    collect_cache_metrics()
    collect_redis_metrics()
    collect_queue_job_metrics()

    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
