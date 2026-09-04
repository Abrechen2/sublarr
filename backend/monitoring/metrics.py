"""Prometheus metrics for the Sublarr scheduler.

These metrics are registered on the default ``prometheus_client`` REGISTRY,
so they are automatically scraped by the existing ``/api/v1/metrics`` endpoint
(which calls ``prometheus_client.generate_latest(REGISTRY)``).

Defined separately from ``backend/metrics.py`` to keep scheduler concerns
isolated and to avoid touching the older, broader metrics module.
"""

from prometheus_client import Counter, Gauge, Histogram

scheduler_job_runs_total = Counter(
    "scheduler_job_runs_total",
    "Total scheduler job executions by id and final status.",
    labelnames=["job_id", "status"],
)

scheduler_job_duration_seconds = Histogram(
    "scheduler_job_duration_seconds",
    "Scheduler job execution duration in seconds.",
    labelnames=["job_id"],
    buckets=(0.1, 0.5, 1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600),
)

scheduler_interrupted_runs_total = Counter(
    "scheduler_interrupted_runs_total",
    "Rows reconciled as InterruptedByShutdown at startup (SIGKILL indicator).",
)

# Translation platform — Phase A1
translation_cost_micro_usd_total = Counter(
    "translation_cost_micro_usd_total",
    "Total translation cost in micro-USD by backend + status.",
    labelnames=["backend", "status"],
)

translation_tokens_total = Counter(
    "translation_tokens_total",
    "Total LLM tokens consumed by backend + direction.",
    labelnames=["backend", "direction"],
)

translation_cache_hits_total = Counter(
    "translation_cache_hits_total",
    "Total translation-memory cache hits by backend.",
    labelnames=["backend"],
)

translation_latency_seconds = Histogram(
    "translation_latency_seconds",
    "Translation request latency by backend.",
    labelnames=["backend"],
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60, 120),
)

translation_concurrency_in_use = Gauge(
    "translation_concurrency_in_use",
    "Current in-use concurrency slots per backend.",
    labelnames=["backend"],
)

translation_concurrency_limit = Gauge(
    "translation_concurrency_limit",
    "Configured concurrency limit per backend.",
    labelnames=["backend"],
)

# Heavy media subprocesses (remux / extraction / sync) share one gate,
# services.media_io_gate. In-use vs limit shows queueing behind array IO.
media_io_gate_in_use = Gauge(
    "sublarr_media_io_gate_in_use",
    "Heavy media subprocesses currently running (remux, extraction, sync).",
)

media_io_gate_limit = Gauge(
    "sublarr_media_io_gate_limit",
    "Configured cap for concurrent heavy media subprocesses (media_io_max_parallel).",
)

# Subtitle sync (ffsubsync / alass) — counters + duration histogram.
# Wired into ``services.sync_engines.events.write_sync_job_run`` so every
# sync_job_runs audit row also bumps the matching Prometheus series, giving
# the bulk auto-sync workflow first-class observability without an
# additional SQL query path.
sync_jobs_total = Counter(
    "sync_jobs_total",
    "Total subtitle-sync jobs by engine and final status.",
    labelnames=["engine", "status"],
)

sync_jobs_duration_seconds = Histogram(
    "sync_jobs_duration_seconds",
    "Subtitle-sync job execution duration in seconds.",
    labelnames=["engine"],
    buckets=(1, 5, 10, 30, 60, 120, 300, 600, 1200),
)

sync_jobs_offset_ms = Histogram(
    "sync_jobs_offset_ms",
    "Absolute shift detected by ffsubsync, in milliseconds (only OK jobs).",
    labelnames=["engine"],
    buckets=(0, 100, 250, 500, 1000, 2500, 5000, 10000, 30000, 60000, 120000),
)
