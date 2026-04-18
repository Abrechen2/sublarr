"""Prometheus metrics for the Sublarr scheduler.

These metrics are registered on the default ``prometheus_client`` REGISTRY,
so they are automatically scraped by the existing ``/api/v1/metrics`` endpoint
(which calls ``prometheus_client.generate_latest(REGISTRY)``).

Defined separately from ``backend/metrics.py`` to keep scheduler concerns
isolated and to avoid touching the older, broader metrics module.
"""

from prometheus_client import Counter, Histogram

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
