"""WantedScanner class implementation — imported by wanted_scanner.py facade.

Scans Sonarr series and Radarr movies, checks local filesystem for
existing target language subtitles, and populates the wanted_items table.
Includes a threading-based scheduler for periodic rescans.

Supports incremental scan mode: after an initial full scan, subsequent scans
only process items modified since the last scan timestamp. Every Nth scan
(FULL_SCAN_INTERVAL) forces a full rescan as safety fallback.

Item-level scanning logic lives in wanted_item_scanner.py.
Search orchestration lives in wanted_search_runner.py.
Periodic scheduler lives in wanted_scanner_scheduler.py.
"""

import logging
import os
import threading
import time
from datetime import UTC, datetime

from config import get_settings
from db.activity import log_activity
from db.models.activity import EVENT_SCAN
from services.scheduler.cancellation import abort_requested
from services.wanted_item_scanner import scan_radarr_movie, scan_sonarr_series
from services.wanted_scanner_scheduler import (  # noqa: F401 — re-exported for back-compat
    _WantedSchedulerMixin,
)
from services.wanted_scanner_sources import (  # noqa: F401 — re-exported for back-compat
    _WantedScanSourcesMixin,
)
from services.wanted_search_runner import run_wanted_search
from translator import detect_existing_target_for_lang

logger = logging.getLogger(__name__)

#: Cleanup fuse — see ``WantedScanner._cleanup``. Half the table in one pass
#: is a wipe, not housekeeping; below the minimum the ratio means nothing.
CLEANUP_FUSE_MAX_FRACTION = 0.5
CLEANUP_FUSE_MIN_ITEMS = 20

# Every Nth scan cycle forces a full scan regardless of incremental mode
FULL_SCAN_INTERVAL = 6


class WantedScanner(_WantedSchedulerMixin, _WantedScanSourcesMixin):
    """Scans Sonarr/Radarr for episodes/movies missing target language subtitles."""

    def __init__(self):
        self._scan_lock = threading.Lock()
        self._search_lock = threading.Lock()
        self._scanning = False
        self._searching = False
        self._timer = None
        self._search_timer = None
        self._socketio = None
        self._app = None
        self._progress = {"current": 0, "total": 0, "phase": "", "added": 0, "updated": 0}
        self._last_scan_at = None
        self._last_search_at = None
        self._scheduler_started_at = None
        self._last_summary = {}
        self._last_scan_timestamp = None
        self._scan_count = 0
        self._scan_had_errors = False
        self._cancel_event = threading.Event()

    # ─── Properties ──────────────────────────────────────────────────────

    @property
    def is_scanning(self):
        return self._scanning

    @property
    def scan_progress(self):
        return dict(self._progress)

    @property
    def is_searching(self):
        return self._searching

    @property
    def last_scan_at(self):
        return self._last_scan_at.isoformat() if self._last_scan_at else None

    @property
    def last_search_at(self):
        return self._last_search_at.isoformat() if self._last_search_at else None

    @property
    def scheduler_started_at(self):
        return self._scheduler_started_at.isoformat() if self._scheduler_started_at else None

    @property
    def last_summary(self):
        return self._last_summary

    # ─── Scan ────────────────────────────────────────────────────────────

    def scan_all(self, incremental=True) -> dict:
        """Run a scan of Sonarr series and Radarr movies.

        Returns summary dict: {added, updated, removed, total_wanted, duration_seconds, scan_type}
        """
        if not self._scan_lock.acquire(blocking=False):
            logger.warning("Wanted scan already running, skipping")
            return {"error": "scan_already_running"}

        self._scanning = True
        start = time.time()
        added = 0
        updated = 0
        scanned_paths = set()
        # Set by the source mixins when a Sonarr/Radarr sweep raises. A failed
        # source contributes no paths, so pruning this pass would delete that
        # source's entire wanted queue (prod 2026-08-30, boot scan vs. an
        # unready Postgres: 9 369 → 154 items).
        self._scan_had_errors = False

        is_incremental = (
            incremental
            and self._last_scan_timestamp is not None
            and self._scan_count % FULL_SCAN_INTERVAL != 0
        )
        scan_type = "incremental" if is_incremental else "full"

        try:
            settings = get_settings()
            logger.info(
                "Wanted scan starting (%s, cycle %d/%d)",
                scan_type,
                self._scan_count + 1,
                FULL_SCAN_INTERVAL,
            )

            since = self._last_scan_timestamp if is_incremental else None

            # One source is the unit of work. A stop between sources is safe;
            # a stop *within* one is not, because the cleanup below removes
            # every wanted item whose path this pass did not see, and the
            # sources that were skipped account for all of theirs.
            aborted = False

            # Scan all Sonarr instances
            a, u, paths = self._scan_all_sonarr(settings, since)
            added += a
            updated += u
            scanned_paths.update(paths)

            if abort_requested():
                aborted = True
            else:
                # Scan all Radarr instances
                a, u, paths = self._scan_all_radarr(settings, since)
                added += a
                updated += u
                scanned_paths.update(paths)

            if not aborted and abort_requested():
                aborted = True
            elif not aborted:
                # Scan standalone items
                a, u, paths = self._scan_all_standalone()
                added += a
                updated += u
                scanned_paths.update(paths)

            if aborted:
                # Never prune against an incomplete path set — that would delete
                # the wanted queue of every source this pass never reached.
                logger.info(
                    "Wanted scan stopping as asked: +%d added, ~%d updated, nothing pruned",
                    added,
                    updated,
                )
                removed = 0
            elif self._scan_had_errors:
                # Same rule for a source that FAILED instead of being skipped:
                # its items are all absent from scanned_paths through no fault
                # of their own.
                logger.warning("Wanted scan: a source errored — skipping cleanup, nothing pruned")
                removed = 0
            else:
                removed = self._cleanup(scanned_paths if not is_incremental else set())

            duration = round(time.time() - start, 1)
            from db.wanted import get_wanted_count

            total_wanted = get_wanted_count()

            summary = {
                "added": added,
                "updated": updated,
                "removed": removed,
                "total_wanted": total_wanted,
                "duration_seconds": duration,
                "scan_type": scan_type,
            }

            self._last_scan_at = datetime.now(UTC)
            if not aborted and not self._scan_had_errors:
                # The watermark must not move past sources that were never
                # looked at — whether skipped by a stop request or lost to an
                # error: the next incremental pass would ask them for changes
                # "since" a moment it never covered, and their edits in that
                # window would be lost for good.
                self._last_scan_timestamp = datetime.now(UTC)
                self._scan_count += 1
            self._last_summary = summary

            logger.info(
                "Wanted %s scan complete: +%d added, ~%d updated, -%d removed, %d total (%.1fs)",
                scan_type,
                added,
                updated,
                removed,
                total_wanted,
                duration,
            )

            log_activity(
                EVENT_SCAN,
                status="success",
                details={
                    "added": added,
                    "updated": updated,
                    "removed": removed,
                    "total_wanted": total_wanted,
                    "scan_type": scan_type,
                    "duration": duration,
                },
            )

            return summary

        except Exception as e:
            logger.exception("Wanted scan failed: %s", e)
            return {"error": str(e)}
        finally:
            self._scanning = False
            self._progress = {"current": 0, "total": 0, "phase": "", "added": 0, "updated": 0}
            self._scan_lock.release()

    def force_full_scan(self) -> dict:
        """Reset incremental state and run a full scan."""
        self._last_scan_timestamp = None
        return self.scan_all(incremental=False)

    def scan_series(self, series_id: int) -> dict:
        """Scan a single Sonarr series."""
        if not self._scan_lock.acquire(blocking=False):
            return {"error": "scan_already_running"}

        self._scanning = True
        start = time.time()

        try:
            settings = get_settings()
            from sonarr_client import get_sonarr_client

            sonarr = get_sonarr_client()
            if not sonarr:
                return {"error": "sonarr_not_configured"}

            added, updated, _ = scan_sonarr_series(
                sonarr, series_id, settings, auto_extract_fn=self._maybe_auto_extract
            )
            duration = round(time.time() - start, 1)

            return {
                "added": added,
                "updated": updated,
                "series_id": series_id,
                "duration_seconds": duration,
            }
        except Exception as e:
            logger.exception("Wanted scan for series %d failed: %s", series_id, e)
            return {"error": str(e)}
        finally:
            self._scanning = False
            self._scan_lock.release()

    def scan_movie(self, movie_id: int) -> dict:
        """Scan a single Radarr movie."""
        if not self._scan_lock.acquire(blocking=False):
            return {"error": "scan_already_running"}

        self._scanning = True
        start = time.time()

        try:
            settings = get_settings()
            from radarr_client import get_radarr_client

            radarr = get_radarr_client()
            if not radarr:
                return {"error": "radarr_not_configured"}

            movie = radarr.get_movie_by_id(movie_id)
            if not movie:
                return {"error": f"movie_{movie_id}_not_found"}

            added, updated, _ = scan_radarr_movie(
                radarr, movie, settings, auto_extract_fn=self._maybe_auto_extract
            )
            duration = round(time.time() - start, 1)

            return {
                "added": added,
                "updated": updated,
                "movie_id": movie_id,
                "duration_seconds": duration,
            }
        except Exception as e:
            logger.exception("Wanted scan for movie %d failed: %s", movie_id, e)
            return {"error": str(e)}
        finally:
            self._scanning = False
            self._scan_lock.release()

    # Per-source scan helpers (_scan_all_sonarr, _scan_sonarr_instance,
    # _scan_all_radarr, _scan_radarr_instance, _scan_all_standalone,
    # _maybe_auto_extract) live on _WantedScanSourcesMixin — see
    # services/wanted_scanner_sources.py.

    def _cleanup(self, scanned_paths: set) -> int:
        """Remove wanted items whose files no longer exist or whose subs appeared.

        Fused: never removes more than ``CLEANUP_FUSE_MAX_FRACTION`` of the
        table in one pass once it holds ``CLEANUP_FUSE_MIN_ITEMS`` rows. A
        library does not lose half its files between two scans; a scan that
        saw too little (a source answering empty mid-start, an unmounted
        share) does — and that must never turn into a wipe.
        """
        from db.wanted import get_wanted_items_for_cleanup

        items = get_wanted_items_for_cleanup()
        to_remove_ids = []

        for item in items:
            path = item["file_path"]
            target_lang = item.get("target_language", "")
            instance_name = item.get("instance_name", "")

            if not os.path.exists(path):
                to_remove_ids.append(item["id"])
                continue

            settings = get_settings()
            if target_lang:
                existing = detect_existing_target_for_lang(path, target_lang)
            else:
                from translator import detect_existing_target

                existing = detect_existing_target(path)
            if existing == "ass":
                to_remove_ids.append(item["id"])
                continue
            if existing == "srt" and not settings.upgrade_enabled:
                to_remove_ids.append(item["id"])
                continue

            if instance_name == "standalone":
                continue
            if scanned_paths and path not in scanned_paths:
                to_remove_ids.append(item["id"])

        if len(items) >= CLEANUP_FUSE_MIN_ITEMS and len(
            to_remove_ids
        ) > CLEANUP_FUSE_MAX_FRACTION * len(items):
            logger.error(
                "Wanted cleanup fuse: refusing to remove %d of %d items in one pass "
                "(limit %d%%) — a drop this size is a scan that saw too little, "
                "not a library that shrank; nothing removed",
                len(to_remove_ids),
                len(items),
                int(CLEANUP_FUSE_MAX_FRACTION * 100),
            )
            return 0

        if to_remove_ids:
            from db.wanted import delete_wanted_items_by_ids

            delete_wanted_items_by_ids(to_remove_ids)
            logger.info("Wanted cleanup: removed %d items", len(to_remove_ids))

        return len(to_remove_ids)

    # ─── Search ─────────────────────────────────────���────────────────────

    def search_all(self, socketio=None, include_upgrades: bool | None = None) -> dict:
        """Search providers for all wanted items."""
        if not self._search_lock.acquire(blocking=False):
            logger.warning("Wanted search already running, skipping")
            return {"error": "search_already_running"}

        self._searching = True
        self._cancel_event.clear()

        try:
            summary = run_wanted_search(
                app=self._app,
                socketio=socketio,
                cancel_event=self._cancel_event,
                include_upgrades=include_upgrades,
            )
            self._last_search_at = datetime.now(UTC)
            return summary
        except Exception as e:
            logger.exception("Wanted search failed: %s", e)
            return {"error": str(e)}
        finally:
            self._searching = False
            self._cancel_event.clear()
            self._search_lock.release()

    def cancel_search(self):
        """Signal the running search to stop after current item completions."""
        self._cancel_event.set()

    # ─── Scheduler ───────────────────────────────────────────────────────
