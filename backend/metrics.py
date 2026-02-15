"""Prometheus metrics for Sublarr monitoring.

Exposes system, business, queue, database, and resilience metrics.
Scraped via ``GET /metrics`` (unauthenticated, for Prometheus).

Requires: ``prometheus_client``, ``psutil``
"""

import os
import logging
from typing import Optional

try:
    import psutil
    from prometheus_client import (
        Counter,
        Gauge,
        Histogram,
        Info,
        generate_latest,
        CONTENT_TYPE_LATEST,
        CollectorRegistry,
        REGISTRY,
    )

    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False

logger = logging.getLogger(__name__)

# ── Metric Definitions ───────────────────────────────────────────────────────

if METRICS_AVAILABLE:
    # System
    CPU_USAGE = Gauge("sublarr_cpu_usage_percent", "CPU usage percentage")
    MEMORY_USAGE = Gauge("sublarr_memory_usage_bytes", "Memory usage in bytes")
    DISK_USAGE = Gauge("sublarr_disk_usage_percent", "Disk usage percentage for /config", ["mount"])

    # Business — translation
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

    # Business — providers
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

    # Queue
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


# ── Collection helpers ───────────────────────────────────────────────────────


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
        from database import get_pending_job_count, get_wanted_summary
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
            CIRCUIT_BREAKER_STATE.labels(provider=name).set(
                state_map.get(cb.state.value, -1)
            )
    except Exception as exc:
        logger.debug("Failed to collect circuit breaker metrics: %s", exc)


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


# ── Endpoint helper ──────────────────────────────────────────────────────────


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

    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
