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
    from services.dubtitle.sweep import dubtitle_scan_tick
    from services.mt_reseek import mt_reseek_tick
    from services.repair.resume import repair_resume_tick
    from services.stats_rollup import stats_rollup_tick
    from services.subtitle_automation_runner import subtitle_automation_tick
    from services.subtitle_health.sweep import subtitle_health_sweep_tick
    from services.usage_stats import usage_stats_tick
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
            id="usage_stats_ping",
            func=usage_stats_tick,
            # Once daily with up to 1h jitter so installs don't all hit the
            # endpoint at the same wall-clock minute. Inert unless the user
            # opted in (usage_stats_tick short-circuits on consent).
            default_trigger=IntervalTrigger(hours=24, jitter=3600),
            timeout_s=30,
            owner_module="services.usage_stats",
            description="Send opt-in anonymous usage statistics ping.",
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
            id="stats_rollup",
            func=stats_rollup_tick,
            default_trigger=CronTrigger(hour=4, minute=0),
            timeout_s=300,
            owner_module="services.stats_rollup",
            description="Roll up daily statistics (downloads/translations/syncs) for trend charts.",
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
            id="mt_reseek",
            func=mt_reseek_tick,
            # Daily original-only re-search of provisional machine-translations
            # (feature #8b). Inert unless a profile opted into keep-seeking, so
            # a fixed 24h interval is cheap; the per-item backoff floor (24h)
            # matches this cadence. Search-heavy like wanted_search → same
            # 1800s headroom so a slow provider day never trips the timeout.
            default_trigger=IntervalTrigger(hours=24),
            timeout_s=1800,
            owner_module="services.mt_reseek",
            description=(
                "Re-search provisional machine-translations for a genuine "
                "provider/embedded original (original-only, no re-translate)."
            ),
        ),
        JobSpec(
            id="repair_resume",
            func=repair_resume_tick,
            # A sharp repair run spans several provider-quota days; this tick
            # restarts it once the daily allowance is back. No-op unless a
            # quota-interrupted run left a pending resume, so a 10-minute
            # cadence costs one KV read. The tick only *starts* the background
            # pass (job.start returns immediately) — 60 s is ample.
            default_trigger=IntervalTrigger(minutes=10),
            timeout_s=60,
            owner_module="services.repair.resume",
            description=(
                "Resume a quota-interrupted subtitle repair run once the "
                "provider's daily allowance resets. No-op when nothing is pending."
            ),
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
            id="dubtitle_scan",
            func=dubtitle_scan_tick,
            # Daily, after the nightly cleanup/upgrade window. No-op unless
            # dubtitle_detection is enabled; bounded + cached so it stays cheap.
            default_trigger=CronTrigger(hour=4, minute=15),
            timeout_s=3600,
            owner_module="services.dubtitle.sweep",
            description=(
                "Detect + flag the dubtitle on library files with multiple "
                "embedded English subtitle tracks. No-op when dubtitle_detection "
                "is off; never modifies files (flag only)."
            ),
        ),
        JobSpec(
            id="subtitle_health_sweep",
            func=subtitle_health_sweep_tick,
            default_trigger=CronTrigger(hour=4, minute=30),
            timeout_s=3600,
            owner_module="services.subtitle_health.sweep",
            description="Scan the library for subtitle content defects (report-only unless auto-fix enabled).",
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
