"""Scheduled cleanup runner for automated deduplication and rule execution.

Follows the same threading.Timer pattern as wanted_scanner scheduler.
Reads cleanup_schedule_interval_hours from config_entries (default: 168 = weekly).
Runs enabled cleanup rules in order: dedup scan then rule execution.
"""

import logging
import threading

logger = logging.getLogger(__name__)

# Default: run weekly (168 hours)
DEFAULT_INTERVAL_HOURS = 168

_scheduler = None
_scheduler_lock = threading.Lock()


def start_cleanup_scheduler(app, socketio):
    """Start the cleanup scheduler if not already running.

    Reads interval from config_entries. Runs enabled rules on schedule.

    Args:
        app: Flask application instance.
        socketio: SocketIO instance for WebSocket progress events.
    """
    global _scheduler
    with _scheduler_lock:
        if _scheduler is not None:
            return  # Already running

        _scheduler = CleanupScheduler(app, socketio)
        _scheduler.start()


def stop_cleanup_scheduler():
    """Stop the cleanup scheduler if running."""
    global _scheduler
    with _scheduler_lock:
        if _scheduler:
            _scheduler.stop()
            _scheduler = None


class CleanupScheduler:
    """Periodic cleanup task runner using threading.Timer."""

    def __init__(self, app, socketio):
        self._app = app
        self._socketio = socketio
        self._timer = None
        self._running = False

    def start(self):
        """Start the scheduler."""
        interval = self._get_interval_hours()
        if interval <= 0:
            logger.info("Cleanup scheduler disabled (interval=0)")
            return

        self._running = True
        self._schedule_next(interval)
        logger.info("Cleanup scheduler started (every %dh)", interval)

    def stop(self):
        """Cancel the scheduled timer."""
        self._running = False
        if self._timer:
            self._timer.cancel()
            self._timer = None
        logger.info("Cleanup scheduler stopped")

    def _get_interval_hours(self) -> int:
        """Read cleanup schedule interval from config."""
        try:
            from db.repositories.config import ConfigRepository
            repo = ConfigRepository()
            value = repo.get_config_entry("cleanup_schedule_interval_hours")
            if value is not None:
                return int(value)
        except Exception as e:
            logger.debug("Could not read cleanup interval from config: %s", e)

        return DEFAULT_INTERVAL_HOURS

    def _schedule_next(self, interval_hours: int):
        """Schedule the next cleanup run."""
        if not self._running:
            return

        self._timer = threading.Timer(
            interval_hours * 3600,
            self._run_scheduled,
            args=(interval_hours,),
        )
        self._timer.daemon = True
        self._timer.start()

    def _run_scheduled(self, interval_hours: int):
        """Execute scheduled cleanup and reschedule."""
        logger.info("Scheduled cleanup starting")

        with self._app.app_context():
            try:
                self._execute_cleanup()
            except Exception as e:
                logger.error("Scheduled cleanup failed: %s", e)

        # Re-read interval (may have been updated via UI)
        new_interval = self._get_interval_hours()
        if new_interval > 0:
            self._schedule_next(new_interval)
        else:
            logger.info("Cleanup scheduler disabled after run (interval set to 0)")
            self._running = False

    def _expire_zombie_jobs(self):
        """Mark jobs stuck in 'running' state for more than 2 hours as failed.

        Handles threads that die mid-job without updating the DB (distinct from
        startup cleanup which only catches jobs interrupted by a restart).
        """
        from datetime import datetime, timedelta, timezone
        from db.jobs import get_jobs, update_job

        cutoff = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        try:
            page = get_jobs(status="running", per_page=500)
            expired = 0
            for job in page.get("data", []):
                created = job.get("created_at", "")
                # Only expire if the job has been running longer than the cutoff
                if created and created < cutoff:
                    update_job(job["id"], "failed", error="Job timed out — running for more than 2 hours")
                    logger.warning("Expired zombie job %s (created_at=%s)", job["id"], created)
                    expired += 1
            if expired:
                logger.info("Zombie job expiry: marked %d stale running jobs as failed", expired)
        except Exception as e:
            logger.warning("Zombie job expiry check failed: %s", e)

    def _execute_cleanup(self):
        """Run all enabled cleanup rules in order."""
        from db.repositories.cleanup import CleanupRepository
        from config import get_settings
        from dedup_engine import scan_for_duplicates, scan_orphaned_subtitles

        # Always run zombie-job expiry regardless of user-configured cleanup rules
        self._expire_zombie_jobs()

        repo = CleanupRepository()
        rules = repo.get_rules()
        settings = get_settings()
        media_path = settings.media_path

        enabled_rules = [r for r in rules if r.get("enabled")]

        if not enabled_rules:
            logger.info("No enabled cleanup rules to execute")
            return

        logger.info("Executing %d enabled cleanup rules", len(enabled_rules))

        for rule in enabled_rules:
            try:
                rule_type = rule["rule_type"]
                rule_id = rule["id"]

                if rule_type == "dedup":
                    result = scan_for_duplicates(media_path, socketio=self._socketio)
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
                    # Scan only, do not auto-delete backups
                    import os
                    bak_count = 0
                    bak_size = 0
                    for root, _dirs, files in os.walk(media_path):
                        for filename in files:
                            if ".bak" in filename:
                                try:
                                    bak_size += os.path.getsize(os.path.join(root, filename))
                                except OSError:
                                    pass
                                bak_count += 1

                    repo.update_rule_last_run(rule_id)
                    repo.log_cleanup(
                        action_type="scheduled_backup_scan",
                        files_processed=bak_count,
                        rule_id=rule_id,
                    )
                    logger.info("Scheduled backup scan: %d .bak files (%d bytes)", bak_count, bak_size)

                else:
                    logger.warning("Unknown rule type: %s", rule_type)

            except Exception as e:
                logger.error("Failed to execute rule %d (%s): %s", rule["id"], rule["name"], e)
