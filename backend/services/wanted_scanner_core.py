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
from datetime import UTC, datetime, timedelta

from config import get_settings
from db.activity import log_activity
from db.models.activity import EVENT_SCAN
from services.scheduler.cancellation import abort_requested
from services.suspect_sidecars import existing_ignoring_suspects
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


def _added_since(added_at, since: datetime) -> bool:
    """Whether a row's ``added_at`` is at or after ``since`` (naive means UTC)."""
    if isinstance(added_at, str):
        try:
            added_at = datetime.fromisoformat(added_at)
        except ValueError:
            return False
    if not isinstance(added_at, datetime):
        return False
    if added_at.tzinfo is None:
        added_at = added_at.replace(tzinfo=UTC)
    return added_at >= since


class WantedScanner(_WantedSchedulerMixin, _WantedScanSourcesMixin):
    """Scans Sonarr/Radarr for episodes/movies missing target language subtitles."""

    #: A stopped full pass older than this starts over instead of resuming.
    RESUME_MAX_AGE = timedelta(days=3)

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
        # The stopped full pass the next full scan continues (#248), and the
        # items the running full pass has finished: {(source, instance, id): paths}.
        self._resume = None
        self._pass_done = None

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
        try:
            result = self._scan_all_locked(incremental)
        except Exception as e:
            logger.exception("Wanted scan failed: %s", e)
            return {"error": str(e)}
        finally:
            self._pass_done = None
            self._scanning = False
            self._progress = {"current": 0, "total": 0, "phase": "", "added": 0, "updated": 0}
            self._scan_lock.release()
            logger.debug("Wanted scan lock released")

        # Reporting runs after the lock is gone: a count that stalls on the
        # database must not keep every later scan out (#248 — a stopped scan
        # held the lock for four hours, refresh answered 409 until a restart).
        try:
            return self._report_scan(result)
        except Exception as e:
            logger.exception("Wanted scan report failed: %s", e)
            return {**result, "error": str(e)}

    def _scan_all_locked(self, incremental: bool) -> dict:
        start = time.time()
        started_at = datetime.now(UTC)
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
            # A stopped full pass goes first: incremental scans in between
            # would let its resume point go stale and restart it from zero.
            and self._resume is None
        )
        scan_type = "incremental" if is_incremental else "full"

        # A full pass that ran out of time continues where it stopped: what it
        # scanned is kept, so a library that needs longer than the job's
        # ceiling still completes over several runs (#248).
        resume = None if is_incremental else self._resume
        if resume and started_at - resume["started_at"] > self.RESUME_MAX_AGE:
            logger.info("Wanted scan: resume point is stale, starting a fresh full pass")
            resume = None
        self._pass_done = None if is_incremental else dict(resume["done"] if resume else {})

        settings = get_settings()
        logger.info(
            "Wanted scan starting (%s, cycle %d/%d%s)",
            scan_type,
            self._scan_count + 1,
            FULL_SCAN_INTERVAL,
            f", resuming after {len(resume['done'])} items" if resume else "",
        )

        since = self._last_scan_timestamp if is_incremental else None
        if not is_incremental:
            # Files quarantined while they were still kept on disk: out of
            # the folder, so the scan below and every job after it sees none.
            from services.suspect_sidecars import trash_quarantined_on_disk

            trash_quarantined_on_disk()

        # A stop is honoured between items. The full-set cleanup below
        # removes every wanted item whose path this pass did not see, so it
        # only runs when every source was walked to the end.
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
            # the wanted queue of every source this pass never reached. The
            # per-row checks (file gone, subtitle already there) do not need
            # the path set; an incremental pass runs the same.
            removed = self._cleanup(set())
            logger.info(
                "Wanted scan stopping as asked: +%d added, ~%d updated, -%d removed "
                "(file gone or subtitle present); %d items done, the next full scan resumes",
                added,
                updated,
                removed,
                len(self._pass_done or {}),
            )
        elif self._scan_had_errors:
            # Same rule for a source that FAILED instead of being skipped:
            # its items are all absent from scanned_paths through no fault
            # of their own.
            logger.warning("Wanted scan: a source errored — skipping cleanup, nothing pruned")
            removed = 0
        elif resume:
            removed = self._cleanup(scanned_paths, protect_since=resume["started_at"])
        else:
            removed = self._cleanup(scanned_paths if not is_incremental else set())

        self._last_scan_at = datetime.now(UTC)
        # The rotation counter is not a watermark. It only decides when the
        # next full rescan falls due, so a scan that ran out of time must
        # still advance it: while it did not, an aborted full scan
        # scheduled another full scan, which also aborted. Prod sat in that
        # loop 2026-09-10..14 — eleven of twelve scans full against a
        # one-in-six cadence, rewriting ~11 800 rows every six hours.
        # A failed source still freezes it: there we do not know what the
        # source held, which is a different thing from running out of time.
        if not self._scan_had_errors:
            self._scan_count += 1
        if not is_incremental:
            if aborted or self._scan_had_errors:
                self._resume = {
                    "started_at": resume["started_at"] if resume else started_at,
                    "done": self._pass_done,
                }
            else:
                self._resume = None
        if not aborted and not self._scan_had_errors:
            # The watermark must not move past sources that were never
            # looked at — whether skipped by a stop request or lost to an
            # error: the next incremental pass would ask them for changes
            # "since" a moment it never covered, and their edits in that
            # window would be lost for good. A pass finished in parts covers
            # changes only from the moment its first part began.
            self._last_scan_timestamp = resume["started_at"] if resume else datetime.now(UTC)

        return {
            "added": added,
            "updated": updated,
            "removed": removed,
            "duration_seconds": round(time.time() - start, 1),
            "scan_type": scan_type,
        }

    def _report_scan(self, result: dict) -> dict:
        from db.wanted import get_wanted_count

        summary = {**result, "total_wanted": get_wanted_count()}
        self._last_summary = summary
        logger.info(
            "Wanted %s scan complete: +%d added, ~%d updated, -%d removed, %d total (%.1fs)",
            summary["scan_type"],
            summary["added"],
            summary["updated"],
            summary["removed"],
            summary["total_wanted"],
            summary["duration_seconds"],
        )
        log_activity(
            EVENT_SCAN,
            status="success",
            details={
                "added": summary["added"],
                "updated": summary["updated"],
                "removed": summary["removed"],
                "total_wanted": summary["total_wanted"],
                "scan_type": summary["scan_type"],
                "duration": summary["duration_seconds"],
            },
        )
        return summary

    def force_full_scan(self) -> dict:
        """Reset incremental state and run a full scan."""
        self._last_scan_timestamp = None
        self._resume = None
        return self.scan_all(incremental=False)

    @staticmethod
    def _standalone_id(item_id: int, arr_configured, lookup) -> int | None:
        """Row id of the standalone title an id names, or None for an arr id.

        Negative ids are standalone (docs/specs/standalone-ids.md); a positive
        id is one only without the arr and when that standalone row exists.
        """
        from services.media_ids import standalone_id_from

        standalone_id = standalone_id_from(item_id)
        if standalone_id is not None:
            return standalone_id
        if arr_configured() or not lookup(item_id):
            return None
        return item_id

    def _scan_standalone_series(self, series_id: int) -> dict | None:
        from db.standalone import get_standalone_series
        from sonarr_client import get_sonarr_client

        standalone_id = self._standalone_id(
            series_id, lambda: get_sonarr_client() is not None, get_standalone_series
        )
        if standalone_id is None:
            return None
        from standalone.scanner import get_scanner as get_standalone_scanner

        return {**get_standalone_scanner().scan_series(standalone_id), "series_id": series_id}

    def _scan_standalone_movie(self, movie_id: int) -> dict | None:
        from db.standalone import get_standalone_movies
        from radarr_client import get_radarr_client
        from services.standalone_library import movie_path_in_watched_folder

        standalone_id = self._standalone_id(
            movie_id, lambda: get_radarr_client() is not None, get_standalone_movies
        )
        if standalone_id is None:
            return None
        movie = get_standalone_movies(standalone_id)
        path = movie_path_in_watched_folder((movie or {}).get("file_path"))
        if not path:
            return {"error": f"movie_{movie_id}_not_found"}
        from standalone.scanner import get_scanner as get_standalone_scanner

        return {**get_standalone_scanner().process_single_file(path), "movie_id": movie_id}

    def scan_series(self, series_id: int) -> dict:
        """Scan a single Sonarr series, or a standalone one (negative id)."""
        if not self._scan_lock.acquire(blocking=False):
            return {"error": "scan_already_running"}

        self._scanning = True
        start = time.time()

        try:
            settings = get_settings()
            from sonarr_client import get_sonarr_client

            standalone = self._scan_standalone_series(series_id)
            if standalone is not None:
                return standalone

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
        """Scan a single Radarr movie, or a standalone one (negative id)."""
        if not self._scan_lock.acquire(blocking=False):
            return {"error": "scan_already_running"}

        self._scanning = True
        start = time.time()

        try:
            settings = get_settings()
            from radarr_client import get_radarr_client

            standalone = self._scan_standalone_movie(movie_id)
            if standalone is not None:
                return standalone

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

    def _cleanup(self, scanned_paths: set, protect_since: datetime | None = None) -> int:
        """Remove wanted items whose files no longer exist or whose subs appeared.

        ``protect_since``: rows added from then on are never removed for
        missing from ``scanned_paths``. A pass finished in parts restores the
        paths of the items it skipped from the earlier part, which cannot
        know an episode added since (#248).

        Fused: never removes more than ``CLEANUP_FUSE_MAX_FRACTION`` of the
        table in one pass once it holds ``CLEANUP_FUSE_MIN_ITEMS`` rows. A
        library does not lose half its files between two scans; a scan that
        saw too little (a source answering empty mid-start, an unmounted
        share) does — and that must never turn into a wipe.
        """
        from db.wanted import get_wanted_items_for_cleanup
        from services.standalone_library import wanted_item_path_refusal

        items = get_wanted_items_for_cleanup()
        to_remove_ids = []

        for item in items:
            if wanted_item_path_refusal(item):
                # Escaped standalone file: not inspected, row kept.
                continue
            path = item["file_path"]
            target_lang = item.get("target_language", "")
            instance_name = item.get("instance_name", "")

            if not os.path.exists(path):
                to_remove_ids.append(item["id"])
                continue

            settings = get_settings()
            if item.get("subtitle_type") == "forced":
                # A [Forced] item waits for the forced file, not the full one:
                # checking the full subtitle removed every [Forced] item of a
                # library that already had subtitles.
                if target_lang and detect_existing_target_for_lang(
                    path, target_lang, subtitle_type="forced"
                ):
                    to_remove_ids.append(item["id"])
                    continue
                existing = None
            elif target_lang:
                existing = detect_existing_target_for_lang(path, target_lang)
                # A quarantined sidecar is not the subtitle the item waits for.
                existing = existing_ignoring_suspects(path, target_lang, existing)
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
                if protect_since and _added_since(item.get("added_at"), protect_since):
                    continue
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
