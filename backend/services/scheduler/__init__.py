"""Sublarr scheduler service — APScheduler facade + JobSpec registry.

Package root. Re-exports the tick infrastructure (``ticks``), the facade
(``core``) and domain exceptions (``errors``) so the historical import
surface ``services.scheduler.<symbol>`` is preserved — including the
textual dispatcher refs ``services.scheduler:_scheduled_tick`` /
``services.scheduler:_scheduled_oneshot_tick`` that the SQLAlchemyJobStore
persists and reimports across restarts.

The canonical JobSpec registry (``_build_default_jobs`` / ``bootstrap_scheduler``)
lives here.
"""

from __future__ import annotations

import logging
import os

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from flask import Flask

from services.scheduler.core import SublarrScheduler, reconcile_stale_runs
from services.scheduler.errors import JobNotRegisteredError, OneshotAlreadyPendingError
from services.scheduler.ticks import (
    _MAX_ERROR_MSG_BYTES,
    JobSpec,
    _get_job_run_lock,
    _get_tick_executor,
    _oneshot_registry,
    _run_now_lock,
    _scheduled_oneshot_tick,
    _scheduled_tick,
    _tick_registry,
    _tick_wrapper,
    _write_job_run,
    compute_default_misfire_grace_time,
)

logger = logging.getLogger(__name__)

__all__ = [
    "JobSpec",
    "JobNotRegisteredError",
    "OneshotAlreadyPendingError",
    "SublarrScheduler",
    "compute_default_misfire_grace_time",
    "reconcile_stale_runs",
    "bootstrap_scheduler",
    "_build_default_jobs",
    "_tick_wrapper",
    "_get_job_run_lock",
    "_get_tick_executor",
    "_scheduled_tick",
    "_scheduled_oneshot_tick",
    "_tick_registry",
    "_oneshot_registry",
    "_run_now_lock",
    "_write_job_run",
    "_MAX_ERROR_MSG_BYTES",
    "SCHEDULED_JOBS",
]

_VALID_ROLES = {"primary", "disabled"}

# Phase-1 placeholder. In later phases, each retiring Timer site will
# register its own JobSpec here. scheduler_history_cleanup is the only
# real job this phase registers.
SCHEDULED_JOBS: list[JobSpec] = []


def _build_default_jobs() -> list[JobSpec]:
    """Build the canonical JobSpec list. Imports are lazy to avoid
    import-time cycles against modules that themselves import scheduler.

    Phase 5 / P4: also registers the four migrated sites (5 JobSpecs) that
    used to be driven by threading.Timer chains. Default intervals are read
    lazily from config so subsequent settings-save calls can adjust them
    via the per-site adapter (``start_cleanup_scheduler``, etc.).
    """
    from anidb_sync import anidb_sync_tick
    from cleanup_scheduler import cleanup_tick
    from services.subtitle_automation_runner import subtitle_automation_tick
    from services.wanted_scanner_scheduler import (
        wanted_scanner_tick,
        wanted_search_tick,
    )
    from standalone import standalone_scan_tick
    from upgrade_scheduler import upgrade_tick
    from utils.scheduler_retention import delete_old_job_runs
    from utils.scheduler_retention_translation import delete_old_translation_events

    # Read wanted scan/search intervals at build time, falling back to
    # conservative defaults. _build_default_jobs runs once per process so
    # later settings saves flow through the adapter's modify_trigger path.
    scan_interval_hours = 6
    search_interval_hours = 24
    upgrade_interval_hours = 168  # trigger floor; adapter pauses when 0
    standalone_interval_hours = 6  # trigger floor; adapter pauses when 0
    automation_drain_minutes = 2
    try:
        from config import get_settings

        settings = get_settings()
        scan_interval_hours = max(1, int(settings.wanted_scan_interval_hours or 6))
        search_interval_hours = max(1, int(settings.wanted_search_interval_hours or 24))
        upgrade_cfg = int(getattr(settings, "upgrade_scan_interval_hours", 0) or 0)
        if upgrade_cfg > 0:
            upgrade_interval_hours = upgrade_cfg
        standalone_cfg = int(getattr(settings, "standalone_scan_interval_hours", 0) or 0)
        if standalone_cfg > 0:
            standalone_interval_hours = standalone_cfg
        automation_drain_minutes = max(
            1, int(getattr(settings, "subtitle_automation_drain_interval_minutes", 2) or 2)
        )
    except Exception:
        logger.debug("scheduler: settings unavailable during _build_default_jobs", exc_info=True)

    return [
        JobSpec(
            id="scheduler_history_cleanup",
            func=delete_old_job_runs,
            default_trigger=CronTrigger(hour=3, minute=15),
            timeout_s=60,
            owner_module="services.scheduler",
            description="Delete old scheduler_job_runs rows per retention policy.",
        ),
        JobSpec(
            id="translation_events_cleanup",
            func=delete_old_translation_events,
            default_trigger=CronTrigger(hour=3, minute=30),
            timeout_s=120,
            owner_module="utils.scheduler_retention_translation",
            description="Delete old translation_events rows per retention policy.",
        ),
        JobSpec(
            # Fixed daily wall-clock fire (03:45), NOT an interval. A weekly
            # IntervalTrigger never fired reliably on this frequently-redeployed
            # container — every restart left the long next-fire untouched and it
            # kept slipping, so trash backups were never auto-pruned. A daily
            # CronTrigger with coalesce fires at a deterministic time and
            # survives restarts (matches scheduler_history_cleanup /
            # translation_events_cleanup). The per-rule retention (old_backups =
            # 7 days) bounds the footprint; running daily just enforces it.
            id="cleanup",
            func=cleanup_tick,
            default_trigger=CronTrigger(hour=3, minute=45),
            timeout_s=3600,
            owner_module="cleanup_scheduler",
            description=("Run enabled cleanup rules (dedup, orphan files, format upgrade, ...)."),
        ),
        JobSpec(
            id="upgrade_scan",
            func=upgrade_tick,
            default_trigger=IntervalTrigger(hours=max(1, upgrade_interval_hours)),
            timeout_s=3600,
            owner_module="upgrade_scheduler",
            description="Scan subtitle_downloads for re-queue eligible upgrade candidates.",
        ),
        JobSpec(
            id="anidb_sync",
            func=anidb_sync_tick,
            default_trigger=IntervalTrigger(hours=168),
            timeout_s=1800,
            owner_module="anidb_sync",
            description="Weekly sync of AniDB absolute-episode mappings.",
        ),
        JobSpec(
            id="wanted_scanner",
            func=wanted_scanner_tick,
            default_trigger=IntervalTrigger(hours=scan_interval_hours),
            # Full-scan can exceed 10 min on large libraries (2979 items → 37 min observed
            # on prod 2026-04-24). Raised to 1 h to avoid false-positive timeout alarms.
            timeout_s=3600,
            owner_module="services.wanted_scanner",
            description="Scan Sonarr/Radarr/standalone for episodes missing subtitles.",
        ),
        JobSpec(
            id="wanted_search",
            func=wanted_search_tick,
            default_trigger=IntervalTrigger(hours=search_interval_hours),
            # Searching ~2k+ wanted items across rate-limited providers can
            # legitimately run long on high-latency days (one slow provider
            # × many items). 900 s clipped real runs; 1800 s leaves headroom.
            # Per-request HTTP timeouts (RetryingSession default 15 s) keep a
            # single hung provider from blocking the whole sweep.
            timeout_s=1800,
            owner_module="services.wanted_scanner",
            description="Search providers for all wanted items.",
        ),
        JobSpec(
            id="subtitle_automation",
            func=subtitle_automation_tick,
            default_trigger=IntervalTrigger(minutes=automation_drain_minutes),
            timeout_s=600,
            owner_module="services.subtitle_automation_runner",
            description=(
                "Drain the subtitle_automation_queue: extract pending embedded "
                "subtitles into sidecars. No-op when the master toggle "
                "(subtitle_automation_enabled) is off."
            ),
        ),
        JobSpec(
            id="standalone_scan",
            func=standalone_scan_tick,
            default_trigger=IntervalTrigger(hours=max(1, standalone_interval_hours)),
            timeout_s=3600,
            owner_module="standalone",
            description=(
                "Scan all watched folders in standalone mode. Paused when "
                "standalone_scan_interval_hours=0; otherwise drives independent "
                "filesystem rediscovery cadence (the wanted_scanner still covers "
                "standalone when this job is paused, for backwards compat)."
            ),
        ),
    ]


def bootstrap_scheduler(app: Flask) -> SublarrScheduler | None:
    """Full startup: honour SUBLARR_SCHEDULER_ROLE env, reconcile,
    register jobs, start.

    Returns the scheduler instance or None if this replica is disabled.
    """
    role = os.environ.get("SUBLARR_SCHEDULER_ROLE", "primary").strip().lower()
    if role not in _VALID_ROLES:
        raise ValueError(
            f"SUBLARR_SCHEDULER_ROLE={role!r} is invalid; expected one of {sorted(_VALID_ROLES)}"
        )
    if role == "disabled":
        logger.info("SUBLARR_SCHEDULER_ROLE=disabled — skipping scheduler on this replica")
        return None

    db_url = app.config["SQLALCHEMY_DATABASE_URI"]
    s = SublarrScheduler(db_url=db_url, autostart=False)
    s.attach_app(app)

    with app.app_context():
        reconcile_stale_runs(grace_minutes=10)

    global SCHEDULED_JOBS
    if not SCHEDULED_JOBS:
        SCHEDULED_JOBS = _build_default_jobs()
    for spec in SCHEDULED_JOBS:
        s.register_job(spec)

    s.start_registered_jobs()
    # Self-heal trigger-class redesigns (e.g. cleanup: interval → cron). An
    # existing JobStore row is preserved by start_registered_jobs, so a
    # code-level trigger-type change would otherwise never apply.
    s.reconcile_trigger_classes()
    s.purge_orphans()
    s.attach_listeners()
    s.start()
    app.extensions["scheduler"] = s
    return s
