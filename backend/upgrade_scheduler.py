"""Subtitle upgrade scheduler.

Migrated from threading.Timer to APScheduler SublarrScheduler in Phase 5 / P4.
The actual scan body lives in ``upgrade_tick()`` which is invoked via a
JobSpec registered by ``services.scheduler._build_default_jobs``.

Legacy adapter API:
  - ``start_upgrade_scheduler(app)`` updates the APScheduler interval based
    on the current config value. Called by settings-save paths and from
    app_schedulers._start_schedulers.
  - ``stop_upgrade_scheduler()`` is a no-op.
  - ``get_upgrade_scheduler()`` returns a small proxy used by
    routes/system/tasks for UI state only.
"""

import logging
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_HOURS = 0  # Disabled by default; user must opt in

#: Subtitles with a score below this value are candidates regardless of format.
UPGRADE_SCORE_THRESHOLD = 500


_state = {
    "executing": False,
    "last_run_at": None,
    "interval_hours": DEFAULT_INTERVAL_HOURS,
}


# ---------------------------------------------------------------------------
# Public adapter API
# ---------------------------------------------------------------------------


def get_upgrade_scheduler():
    """Return a thin adapter for routes/system/tasks.py state rendering."""
    return _UpgradeSchedulerProxy()


class _UpgradeSchedulerProxy:
    """Backwards-compatible shim exposing fields the tasks UI reads."""

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
            return (last + timedelta(hours=interval)).isoformat()
        except Exception:
            return None

    def _execute_scan(self) -> dict:
        return _execute_scan()


def start_upgrade_scheduler(app):
    """Adapter that updates the APScheduler upgrade job's interval.

    Reads ``upgrade_scan_interval_hours`` from config. If the interval is
    0 (disabled), the job is paused via ``scheduler.pause_job`` so that
    the underlying JobSpec row stays in the store but never fires.
    """
    from apscheduler.triggers.interval import IntervalTrigger

    scheduler = app.extensions.get("scheduler") if app is not None else None
    interval = _get_interval_hours()
    _state["interval_hours"] = interval

    if scheduler is None:
        logger.debug("upgrade_scheduler: SublarrScheduler not available yet")
        return

    try:
        if interval <= 0:
            try:
                scheduler.pause_job("upgrade_scan")
                logger.info("upgrade: paused (interval=0)")
            except Exception:
                logger.debug("upgrade: pause_job failed (job may not exist yet)", exc_info=True)
            return
        scheduler.modify_trigger("upgrade_scan", IntervalTrigger(hours=max(1, interval)))
        try:
            scheduler.resume_job("upgrade_scan")
        except Exception:
            pass
        logger.info("upgrade: interval set to %dh via adapter", interval)
    except Exception:
        logger.error("upgrade: adapter failed", exc_info=True)


def stop_upgrade_scheduler():
    """No-op — APScheduler handles shutdown via SublarrScheduler.shutdown()."""
    return None


# ---------------------------------------------------------------------------
# Tick + execution
# ---------------------------------------------------------------------------


def upgrade_tick() -> None:
    """Module-level tick function invoked by APScheduler."""
    result = _execute_scan()
    logger.info(
        "Upgrade scan complete: %d queued, %d skipped",
        result.get("queued", 0),
        result.get("skipped", 0),
    )


def _get_interval_hours() -> int:
    try:
        from config import get_settings

        return get_settings().upgrade_scan_interval_hours
    except Exception as e:
        logger.debug("Could not read upgrade scan interval: %s", e)
    return DEFAULT_INTERVAL_HOURS


def _execute_scan() -> dict:
    """Core scan logic: find eligible downloads and re-queue wanted items."""
    from sqlalchemy import select
    from sqlalchemy import update as sa_update

    from config import get_settings
    from db import get_db
    from db.models.core import WantedItem
    from db.models.providers import SubtitleDownload
    from db.repositories.wanted import WantedRepository

    _state["executing"] = True
    queued = 0
    skipped = 0

    try:
        settings = get_settings()
        if not getattr(settings, "upgrade_enabled", True):
            logger.info("upgrade_scan: upgrade_enabled=False — skipping scan")
            return {"queued": 0, "skipped": 0}
        window_days = settings.upgrade_window_days
        interval_h = settings.upgrade_scan_interval_hours

        # Only consider downloads old enough that the 2× delta protection has expired
        cutoff_download = datetime.now(UTC) - timedelta(days=window_days)

        # Don't re-queue items that were already searched recently
        cutoff_search = datetime.now(UTC) - timedelta(hours=max(interval_h, 24))

        with get_db() as db:
            wanted_repo = WantedRepository(db)

            # Find subtitle_downloads older than window_days
            stmt = select(SubtitleDownload).where(SubtitleDownload.downloaded_at < cutoff_download)
            downloads = db.execute(stmt).scalars().all()

            for dl in downloads:
                # Phase-1 provisional-MT guard (feature #8): do not let the
                # generic upgrade scan reactivate machine-translated rows. A
                # provisional MT item's wanted status is neither "wanted" nor
                # "searching", so without this guard the scan would flip it back
                # to "wanted" and the normal scanner would re-translate it in a
                # loop. The original-only re-seek of these rows is feature #8b.
                if (dl.source or "") == "machine_translation":
                    skipped += 1
                    continue

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
                        updated_at=datetime.now(UTC),
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
        _state["executing"] = False
        _state["last_run_at"] = datetime.now(UTC)

    return {"queued": queued, "skipped": skipped}


# ---------------------------------------------------------------------------
# Legacy class retained only for tests that instantiate it directly.
# New code should use the adapter functions / ``upgrade_tick()`` above.
# ---------------------------------------------------------------------------


class UpgradeScheduler:
    """Backwards-compatible shim around the module-level tick functions.

    Retained so existing unit tests (``tests/test_upgrade_scheduler.py``)
    that exercise ``_execute_scan`` / ``_get_interval_hours`` semantics
    continue to work without rewrites.
    """

    def __init__(self, app):
        self._app = app
        self._timer = None
        self._running = False

    @property
    def is_executing(self) -> bool:
        return _state["executing"]

    @property
    def last_run_at(self):
        return _state["last_run_at"]

    def start(self):
        interval = self._get_interval_hours()
        if interval <= 0:
            logger.info("Upgrade scheduler disabled (interval=0)")
            self._running = False
            self._timer = None
            return
        # Legacy tests assert ``_timer is not None`` after start().
        self._running = True
        self._timer = object()

    def stop(self):
        self._running = False
        self._timer = None

    def run_now(self) -> dict:
        with self._app.app_context():
            return _execute_scan()

    def _get_interval_hours(self) -> int:
        return _get_interval_hours()

    def _execute_scan(self) -> dict:
        return _execute_scan()
