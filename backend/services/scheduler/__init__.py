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
    from services.foreign_tracks.sweep import foreign_track_sweep_tick
    from services.mt_reseek import mt_reseek_tick
    from services.provider_degradation import provider_degradation_tick
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
    from utils.scheduler_retention import internal_history_cleanup
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
            func=internal_history_cleanup,
            default_trigger=CronTrigger(hour=3, minute=15),
            timeout_s=60,
            owner_module="services.scheduler",
            description=(
                "Delete old scheduler_job_runs rows and finished "
                "subtitle_automation_queue rows per retention policy."
            ),
        ),
        JobSpec(
            id="provider_degradation_check",
            func=provider_degradation_tick,
            # Hourly. The conditions are measured in hours, and the alert is
            # deduplicated to one per provider per condition per day, so a
            # tighter cadence buys nothing and a looser one delays the first
            # ping past the point of being useful.
            default_trigger=IntervalTrigger(hours=1),
            timeout_s=60,
            owner_module="services.provider_degradation",
            description="Notice a provider that stopped working without failing loudly.",
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
            # 2h, not 1h. This tick walks the whole media library, so its
            # runtime tracks library size and filesystem latency rather than
            # anything Sublarr controls. Measured over 31 consecutive runs on a
            # ~750-season library (prod, 2026-07/08): median ~18 min, slowest
            # successful run 51.5 min, two runs over 60 min. At 3600s those two
            # were recorded as "timeout" even though the work ran to completion
            # — _tick_wrapper's future.result(timeout=...) stops *waiting*, it
            # cannot cancel a thread that already started. So a too-tight
            # ceiling produced false alarms, not protection. 7200s still traps a
            # genuine hang while leaving the observed tail room to finish.
            timeout_s=7200,
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
            # The grace has to fit ONE unit of work, because that is the
            # granularity this cancellation design promises (see
            # scheduler/cancellation.py): the item loop stops promptly — 71s
            # in the last measurement, logged as "cancelled after 109/2100
            # items" — and the phase then waits on the items already in
            # flight to finish their chain.
            #
            # One unit here is a whole item: provider searches with retries,
            # a download and a remux. Prod 2026-08-15 measured four wind-downs
            # across three builds: 31s, 175s, 197s, ~300s.
            #
            # 300s was tried first and still read `timeout_abandoned`. The
            # number is not the lesson: until 126a703f the tail was
            # *unbounded*, because a stop request never reached the worker
            # threads and auto-sync kept starting new runs — four of them
            # seven minutes past a cancel. No grace can be correct against
            # that, and raising it was treating the symptom. With the tail
            # bounded to one item, a value that fits one item is defensible;
            # 900s matches subtitle_automation for the same reason.
            #
            # This comment used to count "a sync that had already started
            # (6-143s on its own)" as part of the unit, and that was the flaw
            # the number inherited: `sync_with_ffsubsync` caps a single run at
            # 600s, so the real unit was four times what was budgeted for it
            # and three consecutive sweeps ended `timeout_abandoned`
            # (2026-08-15/16). Rather than grow the grace to fit, auto-sync
            # moved to the subtitle_automation queue, which restores the unit
            # this value was chosen for. Anything added back into the per-item
            # chain has to be measured against 900s before it goes in.
            cancel_grace_s=900,
            owner_module="services.wanted_scanner",
            description="Search providers for all wanted items.",
        ),
        JobSpec(
            id="subtitle_automation",
            func=subtitle_automation_tick,
            default_trigger=IntervalTrigger(minutes=automation_drain_minutes),
            # Prod, 7 days to 2026-08-14: 4536 ok runs with a max of 582s —
            # right up against the old 600s budget — plus 41 `timeout` and 11
            # `timeout_abandoned` rows clustered at 610-668s. Those were runs
            # doing exactly the work they were asked to do, recorded as
            # failures, which made the history useless for spotting a job that
            # is genuinely stuck. The job now also drains sidecar
            # translations, one of which measured ~870s, so 600s could not fit
            # a single unit of its new work either.
            #
            # A timeout does not cancel; it stops waiting and sets the abort
            # event, which drain() checks between items. So this bounds how
            # long a tick may keep claiming new work, not how long one item
            # may take.
            #
            # Unlike the trigger, this value is not persisted: the JobStore
            # keeps trigger and next_run_time, while _tick_wrapper reads
            # timeout_s off the code-built JobSpec at fire time. Changing it
            # here therefore takes effect for every install on upgrade, with
            # no "Reset to default" needed.
            timeout_s=2400,
            # The comment above already says it: the abort event is checked
            # *between* items, so the wind-down is however long the item in
            # flight still needs. Prod 2026-08-15 measured that directly —
            # cancel at 10:07:51, `stopping as asked after 2 item(s)` at
            # 10:11:08, i.e. 197s — and it was recorded as
            # `timeout_abandoned` anyway, against a 60s grace. The job
            # announced its own cooperation in the same log the history
            # accused it of skipping.
            #
            # 900s rather than the measured 197s because one unit of this
            # job's work is a whole translation, and the queue's timings show
            # those running up to ~16 minutes. The grace has to fit the unit,
            # not the average.
            #
            # Auto-sync joined this queue in 1.12.1, which adds a unit capped
            # at 600s — inside the ~16 minutes already budgeted for, so the
            # number does not move. Note that 900s does NOT fit the 16-minute
            # translation it was sized against: prod 2026-08-15/16 recorded 5
            # `timeout_abandoned` against 7 `timeout` over twelve runs. That
            # gap is this job's own, older problem and is not addressed here.
            cancel_grace_s=900,
            owner_module="services.subtitle_automation_runner",
            description=(
                "Drain the subtitle_automation_queue: extract pending embedded "
                "subtitles into sidecars, translate local source sidecars, and "
                "time freshly downloaded sidecars against their video. Each kind "
                "of work follows its own setting — subtitle_automation_enabled "
                "for the first two, auto_sync_after_download for the last — so "
                "the job is only a full no-op when both are off."
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
        JobSpec(
            id="foreign_track_sweep",
            func=foreign_track_sweep_tick,
            default_trigger=IntervalTrigger(hours=6),
            # 3600s = twice the default 1800s budget. The budget is checked
            # after each completed file, so a single large remux can overshoot;
            # a ceiling at the budget itself would log false timeouts the way
            # the cleanup job's 3600s did, without ever cancelling anything.
            timeout_s=3600,
            owner_module="services.foreign_tracks.sweep",
            description=(
                "Strip embedded foreign-language subtitle tracks in bounded, resumable slices."
            ),
        ),
    ]


def _reclaim_orphaned_automation_queue() -> None:
    """Release drain-queue claims held by workers that died with the process.

    The counterpart to `reconcile_stale_runs()` for the job-run table.
    Without it, whatever item the drain worker held at shutdown stays
    `running` forever — no retry, no error, silently out of the queue.
    Best-effort: a failure here must not stop the scheduler from starting.
    """
    from db.repositories.subtitle_automation_queue import (
        SubtitleAutomationQueueRepository,
    )

    try:
        reclaimed = SubtitleAutomationQueueRepository().reclaim_orphaned()
    except Exception:
        logger.exception("Could not reclaim orphaned automation-queue rows")
        return
    if reclaimed:
        logger.info(
            "Automation queue: requeued %d row(s) orphaned by the last shutdown",
            reclaimed,
        )


def _reclaim_stranded_searching_items() -> None:
    """Return wanted rows stuck in 'searching' to the pool at startup.

    The scheduled selector only picks status='wanted', so a row left in
    'searching' — by a process kill mid-search, or by the 1.12.1-rc.8/rc.9
    deferred-fallback exit — is invisible to every future run. At bootstrap
    no search can be running, so every such row is an orphan. Best-effort:
    a failure here must not stop the scheduler from starting.
    """
    from db.repositories.wanted import WantedRepository

    try:
        reclaimed = WantedRepository().reclaim_stranded_searching()
    except Exception:
        logger.exception("Could not reclaim stranded 'searching' wanted rows")
        return
    if reclaimed:
        logger.info(
            "Wanted pool: returned %d row(s) stranded in 'searching' to the pool",
            reclaimed,
        )


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
        _reclaim_orphaned_automation_queue()
        _reclaim_stranded_searching_items()

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
