"""Scheduled cleanup runner for automated deduplication and rule execution.

Migrated from threading.Timer to APScheduler SublarrScheduler in Phase 5 / P4.
The actual cleanup body lives in ``cleanup_tick()`` which is invoked via
a JobSpec registered by ``services.scheduler._build_default_jobs``.

``start_cleanup_scheduler`` is retained as an adapter that updates the
APScheduler interval in response to settings-save calls from the config
routes. ``stop_cleanup_scheduler`` is now a no-op because APScheduler owns
lifecycle.
"""

import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

# Default: run weekly (168 hours)
DEFAULT_INTERVAL_HOURS = 168


# Lightweight state tracked purely for the /api/v1/system/tasks snapshot.
# APScheduler owns scheduling; this only keeps last_run / is_executing flags
# so the existing System Tasks UI continues to render.
_state = {
    "executing": False,
    "last_run_at": None,
    "interval_hours": DEFAULT_INTERVAL_HOURS,
}


def get_cleanup_scheduler():
    """Return a thin adapter for routes/system/tasks.py.

    Legacy callers expected an object with ``_running`` / ``is_executing`` /
    ``last_run_at`` / ``next_run_at``. APScheduler owns scheduling now;
    this returns a small adapter that exposes those fields from the
    APScheduler job state + local execution flag.
    """
    return _CleanupSchedulerProxy()


class _CleanupSchedulerProxy:
    """Backwards-compatible shim exposing the attributes routes read."""

    @property
    def _running(self) -> bool:
        return _get_interval_hours() > 0

    @property
    def is_executing(self) -> bool:
        return _state["executing"]

    @property
    def last_run_at(self):
        return _state["last_run_at"]

    @property
    def next_run_at(self):
        last = _state["last_run_at"]
        interval = _state["interval_hours"]
        if not last or not interval:
            return None
        try:
            from datetime import timedelta

            return (last + timedelta(hours=interval)).isoformat()
        except Exception:
            return None

    def _execute_cleanup(self):
        """Legacy hook used by /api/v1/system/tasks/cleanup/trigger."""
        _execute_cleanup()


def start_cleanup_scheduler(app, socketio=None):
    """Display-only adapter — no longer reschedules the cleanup job.

    The ``cleanup`` JobSpec now owns a fixed daily CronTrigger (03:45) as
    its default; rescheduling it to an IntervalTrigger here would clobber
    that cron on every boot, reintroducing the weekly-interval job that
    never fired reliably on a redeployed container. Trigger changes now go
    exclusively through the Scheduler admin UI (modify_trigger /
    reset_default).

    Kept as a thin shim so ``app_schedulers._start_schedulers`` and the
    legacy System-Tasks snapshot still resolve ``interval_hours``.
    """
    _state["interval_hours"] = _get_interval_hours()
    logger.debug("cleanup_scheduler: cron-owned, adapter is display-only")


def stop_cleanup_scheduler():
    """No-op — APScheduler handles shutdown via SublarrScheduler.shutdown()."""
    return None


def _get_interval_hours() -> int:
    """Read cleanup schedule interval from config (config_entries table)."""
    try:
        from db.repositories.config import ConfigRepository

        repo = ConfigRepository()
        value = repo.get_config_entry("cleanup_schedule_interval_hours")
        if value is not None:
            return int(value)
    except Exception as e:
        logger.debug("Could not read cleanup interval from config: %s", e)
    return DEFAULT_INTERVAL_HOURS


def cleanup_tick() -> None:
    """Module-level tick function invoked by APScheduler.

    Wraps ``_execute_cleanup`` with tracking flags so the tasks-list UI
    can show the ``running`` / ``last_run_at`` state.
    """
    _execute_cleanup()


def _expire_zombie_jobs():
    """Mark jobs stuck in 'running' state for more than 2 hours as failed."""
    from datetime import datetime, timedelta

    from db.jobs import get_jobs, update_job

    cutoff = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    try:
        page = get_jobs(status="running", per_page=500)
        expired = 0
        for job in page.get("data", []):
            created = job.get("created_at", "")
            if created and created < cutoff:
                update_job(
                    job["id"], "failed", error="Job timed out — running for more than 2 hours"
                )
                logger.warning("Expired zombie job %s (created_at=%s)", job["id"], created)
                expired += 1
        if expired:
            logger.info("Zombie job expiry: marked %d stale running jobs as failed", expired)
    except Exception as e:
        logger.warning("Zombie job expiry check failed: %s", e)


def _execute_cleanup():
    """Run all enabled scheduled cleanup rules in order."""
    from config import get_settings
    from db.repositories.cleanup import CleanupRepository
    from dedup_engine import scan_for_duplicates, scan_orphaned_subtitles
    from services.cleanup_executors import (
        execute_foreign_tracks,
        execute_format_upgrade,
        execute_language_filter,
        execute_orphan_db,
        execute_orphan_files,
    )

    _state["executing"] = True
    try:
        # Always run zombie-job expiry regardless of user-configured cleanup rules
        _expire_zombie_jobs()

        repo = CleanupRepository()
        rules = repo.get_rules()
        settings = get_settings()
        media_path = settings.media_path

        scheduled_rules = [
            r
            for r in rules
            if r.get("enabled") and r.get("schedule") in ("daily", "weekly", "after_scan")
        ]

        if not scheduled_rules:
            logger.info("No scheduled cleanup rules to execute")
            return

        logger.info("Executing %d scheduled cleanup rules", len(scheduled_rules))

        for rule in scheduled_rules:
            try:
                rule_type = rule["rule_type"]
                rule_id = rule["id"]
                config = rule.get("config_json", {})

                if rule_type == "language_filter":
                    result = execute_language_filter(media_path, config, dry_run=False)
                    repo.update_rule_last_run(rule_id)
                    repo.log_cleanup(
                        action_type="scheduled_language_filter",
                        files_deleted=result.get("deleted", 0),
                        bytes_freed=result.get("bytes_freed", 0),
                        rule_id=rule_id,
                    )
                    logger.info(
                        "Scheduled language_filter: %d deleted, %d bytes freed",
                        result.get("deleted", 0),
                        result.get("bytes_freed", 0),
                    )

                elif rule_type == "format_upgrade":
                    result = execute_format_upgrade(media_path, config, dry_run=False)
                    repo.update_rule_last_run(rule_id)
                    repo.log_cleanup(
                        action_type="scheduled_format_upgrade",
                        files_deleted=result.get("deleted", 0),
                        bytes_freed=result.get("bytes_freed", 0),
                        rule_id=rule_id,
                    )
                    logger.info(
                        "Scheduled format_upgrade: %d deleted, %d bytes freed",
                        result.get("deleted", 0),
                        result.get("bytes_freed", 0),
                    )

                elif rule_type == "orphan_files":
                    result = execute_orphan_files(media_path, config, dry_run=False)
                    repo.update_rule_last_run(rule_id)
                    repo.log_cleanup(
                        action_type="scheduled_orphan_files",
                        files_deleted=result.get("deleted", 0),
                        bytes_freed=result.get("bytes_freed", 0),
                        rule_id=rule_id,
                    )
                    logger.info(
                        "Scheduled orphan_files: %d deleted, %d bytes freed",
                        result.get("deleted", 0),
                        result.get("bytes_freed", 0),
                    )

                elif rule_type == "orphan_db":
                    result = execute_orphan_db(config, dry_run=False)
                    repo.update_rule_last_run(rule_id)
                    repo.log_cleanup(
                        action_type="scheduled_orphan_db",
                        files_deleted=result.get("deleted", 0),
                        rule_id=rule_id,
                    )
                    logger.info(
                        "Scheduled orphan_db: %d DB entries removed",
                        result.get("deleted", 0),
                    )

                elif rule_type == "foreign_tracks":
                    result = execute_foreign_tracks(media_path, config, dry_run=False)
                    repo.update_rule_last_run(rule_id)
                    repo.log_cleanup(
                        action_type="scheduled_foreign_tracks",
                        files_deleted=result.get("stripped_files", 0),
                        bytes_freed=result.get("bytes_freed", 0),
                        rule_id=rule_id,
                    )
                    logger.info(
                        "Scheduled foreign_tracks: %d files stripped, %d tracks removed, "
                        "%d bytes freed",
                        result.get("stripped_files", 0),
                        result.get("tracks_removed", 0),
                        result.get("bytes_freed", 0),
                    )

                elif rule_type == "dedup":
                    result = scan_for_duplicates(media_path, socketio=None)
                    repo.update_rule_last_run(rule_id)
                    repo.log_cleanup(
                        action_type="scheduled_dedup",
                        files_processed=result.get("total_scanned", 0),
                        rule_id=rule_id,
                    )
                    logger.info(
                        "Scheduled dedup scan: %d files, %d duplicates",
                        result.get("total_scanned", 0),
                        result.get("duplicates_found", 0),
                    )

                elif rule_type == "orphaned":
                    result = scan_orphaned_subtitles(media_path)
                    repo.update_rule_last_run(rule_id)
                    repo.log_cleanup(
                        action_type="scheduled_orphan_scan",
                        files_processed=len(result),
                        rule_id=rule_id,
                    )
                    logger.info("Scheduled orphan scan: %d orphaned files found", len(result))

                elif rule_type == "old_backups":
                    from flask import current_app

                    from remux.backup_cleanup import cleanup_old_backups
                    from routes.remux import _trash_paths

                    retention_days = getattr(settings, "remux_backup_retention_days", 7)
                    app = current_app._get_current_object()
                    with app.app_context():
                        trash_dirs = _trash_paths()
                    result = cleanup_old_backups(trash_dirs, retention_days)
                    deleted_count = len(result.get("deleted", []))

                    repo.update_rule_last_run(rule_id)
                    repo.log_cleanup(
                        action_type="scheduled_backup_cleanup",
                        files_deleted=deleted_count,
                        rule_id=rule_id,
                    )
                    logger.info(
                        "Scheduled backup cleanup: %d .bak files deleted (retention=%dd)",
                        deleted_count,
                        retention_days,
                    )

                elif rule_type == "old_sidecar_trash":
                    from routes.subtitles import _auto_purge_old_trash

                    retention_days = getattr(settings, "subtitle_trash_retention_days", 30)
                    purged = _auto_purge_old_trash(media_path, retention_days)

                    repo.update_rule_last_run(rule_id)
                    repo.log_cleanup(
                        action_type="scheduled_sidecar_trash_purge",
                        files_deleted=purged,
                        rule_id=rule_id,
                    )
                    logger.info(
                        "Scheduled sidecar trash purge: %d batches removed (retention=%dd)",
                        purged,
                        retention_days,
                    )

                elif rule_type == "old_subtitle_baks":
                    # Auto-purge subtitle .bak files from
                    # subtitle_processor.apply_mods. Two-pronged: orphans
                    # (no parent video AND no active sub) go immediately
                    # regardless of age; non-orphans go after retention.
                    # See services.subtitle_backups for the policy
                    # rationale.
                    from services.subtitle_backups import cleanup_subtitle_baks

                    media_roots: list[str] = []
                    if getattr(settings, "media_path", ""):
                        media_roots.append(settings.media_path)
                    extra = getattr(settings, "extra_media_paths", "")
                    if extra:
                        media_roots.extend(p.strip() for p in extra.split(",") if p.strip())

                    retention_days = int(getattr(settings, "subtitle_bak_retention_days", 30) or 0)
                    result = cleanup_subtitle_baks(
                        media_roots,
                        older_than_days=retention_days,
                        orphans_only=False,
                    )
                    deleted_count = len(result.get("deleted", []))
                    orphan_count = result.get("orphans_purged", 0)

                    repo.update_rule_last_run(rule_id)
                    repo.log_cleanup(
                        action_type="scheduled_subtitle_bak_cleanup",
                        files_deleted=deleted_count,
                        rule_id=rule_id,
                    )
                    logger.info(
                        "Scheduled subtitle .bak cleanup: %d deleted (%d orphans, retention=%dd)",
                        deleted_count,
                        orphan_count,
                        retention_days,
                    )

                else:
                    logger.warning("Unknown rule type in scheduler: %s", rule_type)

            except Exception as e:
                logger.error("Failed to execute rule %d (%s): %s", rule["id"], rule["name"], e)
    finally:
        _state["executing"] = False
        _state["last_run_at"] = datetime.now(UTC)
