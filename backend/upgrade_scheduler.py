"""Subtitle upgrade scheduler.

Periodically scans subtitle_downloads for entries that are eligible for a
quality upgrade check and re-queues the corresponding wanted items.

Upgrade eligibility criteria:
- The subtitle was downloaded more than `upgrade_window_days` ago
  (so the "fresh download 2× delta" protection has expired)
- The download score is below `upgrade_score_threshold` (default 500)
  OR the format is not ASS (SRT subs are always worth re-checking)
- The wanted_item has not been searched within the last scan interval

When eligible, the wanted_item is reset to status="wanted" with
upgrade_candidate=1 and current_score set. The existing
process_wanted_item() flow handles the actual provider search + comparison.

Follows the threading.Timer + singleton pattern of cleanup_scheduler.py.
"""

import logging
import threading
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_HOURS = 0  # Disabled by default; user must opt in

#: Subtitles with a score below this value are candidates regardless of format.
UPGRADE_SCORE_THRESHOLD = 500

_scheduler = None
_scheduler_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_upgrade_scheduler():
    """Return the current UpgradeScheduler singleton, or None if not started."""
    return _scheduler


def start_upgrade_scheduler(app):
    """Start the upgrade scheduler if not already running."""
    global _scheduler
    with _scheduler_lock:
        if _scheduler is not None:
            return
        _scheduler = UpgradeScheduler(app)
        _scheduler.start()


def stop_upgrade_scheduler():
    """Stop the upgrade scheduler."""
    global _scheduler
    with _scheduler_lock:
        if _scheduler:
            _scheduler.stop()
            _scheduler = None


# ---------------------------------------------------------------------------
# Scheduler class
# ---------------------------------------------------------------------------


class UpgradeScheduler:
    """Periodic subtitle upgrade candidate scanner."""

    def __init__(self, app):
        self._app = app
        self._timer = None
        self._running = False
        self._executing = False
        self._last_run_at = None
        self._interval_hours = DEFAULT_INTERVAL_HOURS

    @property
    def is_executing(self) -> bool:
        return self._executing

    @property
    def last_run_at(self):
        return self._last_run_at

    @property
    def next_run_at(self):
        if not self._last_run_at or not self._interval_hours:
            return None
        try:
            last_dt = datetime.fromisoformat(self._last_run_at)
            return (last_dt + timedelta(hours=self._interval_hours)).isoformat()
        except Exception:
            return None

    def start(self):
        interval = self._get_interval_hours()
        if interval <= 0:
            logger.info("Upgrade scheduler disabled (interval=0)")
            return
        self._running = True
        self._interval_hours = interval
        self._schedule_next(interval)
        logger.info("Upgrade scheduler started (every %dh)", interval)

    def stop(self):
        self._running = False
        if self._timer:
            self._timer.cancel()
            self._timer = None
        logger.info("Upgrade scheduler stopped")

    def run_now(self) -> dict:
        """Run an upgrade scan immediately (bypasses timer, thread-safe)."""
        with self._app.app_context():
            return self._execute_scan()

    # ------------------------------------------------------------------ private

    def _get_interval_hours(self) -> int:
        try:
            from config import get_settings

            return get_settings().upgrade_scan_interval_hours
        except Exception as e:
            logger.debug("Could not read upgrade scan interval: %s", e)
        return DEFAULT_INTERVAL_HOURS

    def _schedule_next(self, interval_hours: int):
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
        logger.info("Scheduled upgrade scan starting")
        with self._app.app_context():
            try:
                result = self._execute_scan()
                logger.info(
                    "Upgrade scan complete: %d queued, %d skipped",
                    result["queued"],
                    result["skipped"],
                )
            except Exception as e:
                logger.error("Scheduled upgrade scan failed: %s", e)

        new_interval = self._get_interval_hours()
        self._interval_hours = new_interval
        if new_interval > 0:
            self._schedule_next(new_interval)
        else:
            logger.info("Upgrade scheduler disabled after run (interval=0)")
            self._running = False

    def _execute_scan(self) -> dict:
        """Core scan logic: find eligible downloads and re-queue wanted items."""
        from sqlalchemy import select
        from sqlalchemy import update as sa_update

        from config import get_settings
        from db import get_db
        from db.models.core import WantedItem
        from db.models.providers import SubtitleDownload
        from db.repositories.wanted import WantedRepository

        self._executing = True
        queued = 0
        skipped = 0

        try:
            settings = get_settings()
            window_days = settings.upgrade_window_days
            interval_h = settings.upgrade_scan_interval_hours

            # Only consider downloads old enough that the 2× delta protection has expired
            cutoff_download = datetime.now(UTC) - timedelta(days=window_days)

            # Don't re-queue items that were already searched recently
            cutoff_search = datetime.now(UTC) - timedelta(hours=max(interval_h, 24))

            with get_db() as db:
                wanted_repo = WantedRepository(db)

                # Find subtitle_downloads older than window_days
                stmt = select(SubtitleDownload).where(
                    SubtitleDownload.downloaded_at < cutoff_download.isoformat()
                )
                downloads = db.execute(stmt).scalars().all()

                for dl in downloads:
                    # Only consider low-score downloads or non-ASS formats
                    is_low_score = (dl.score or 0) < UPGRADE_SCORE_THRESHOLD
                    is_not_ass = (dl.format or "").lower() not in ("ass", "ssa")
                    if not (is_low_score or is_not_ass):
                        skipped += 1
                        continue

                    # Find corresponding wanted item by file_path
                    item = wanted_repo.get_wanted_by_file_path(dl.file_path)
                    if not item:
                        skipped += 1
                        continue

                    # Skip if already in "wanted" / "searching" state
                    if item.get("status") in ("wanted", "searching"):
                        skipped += 1
                        continue

                    # Skip if searched too recently
                    last_search = item.get("last_search_at")
                    if last_search:
                        try:
                            last_dt = datetime.fromisoformat(last_search)
                            if last_dt.tzinfo is None:
                                last_dt = last_dt.replace(tzinfo=UTC)
                            if last_dt > cutoff_search:
                                skipped += 1
                                continue
                        except Exception:
                            pass

                    # Re-queue as upgrade candidate
                    db.execute(
                        sa_update(WantedItem)
                        .where(WantedItem.id == item["id"])
                        .values(
                            status="wanted",
                            upgrade_candidate=1,
                            current_score=dl.score or 0,
                            updated_at=datetime.now(UTC).isoformat(),
                        )
                    )
                    db.commit()
                    logger.debug(
                        "Upgrade candidate queued: wanted_id=%d file=%s score=%d format=%s",
                        item["id"],
                        dl.file_path,
                        dl.score or 0,
                        dl.format or "?",
                    )
                    queued += 1

        finally:
            self._executing = False
            self._last_run_at = datetime.now(UTC).isoformat()

        return {"queued": queued, "skipped": skipped}
