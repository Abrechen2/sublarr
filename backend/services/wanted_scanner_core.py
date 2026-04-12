"""WantedScanner class implementation — imported by wanted_scanner.py facade.

Scans Sonarr series and Radarr movies, checks local filesystem for
existing target language subtitles, and populates the wanted_items table.
Includes a threading-based scheduler for periodic rescans.

Supports incremental scan mode: after an initial full scan, subsequent scans
only process items modified since the last scan timestamp. Every Nth scan
(FULL_SCAN_INTERVAL) forces a full rescan as safety fallback.

Item-level scanning logic lives in wanted_item_scanner.py.
Search orchestration lives in wanted_search_runner.py.
"""

import logging
import os
import threading
import time
from datetime import UTC, datetime

from config import get_settings
from db.activity import log_activity
from db.models.activity import EVENT_SCAN
from db.wanted import batch_upsert_context
from services.wanted_item_scanner import scan_radarr_movie, scan_sonarr_series
from services.wanted_search_runner import run_wanted_search
from translator import detect_existing_target_for_lang

logger = logging.getLogger(__name__)

# Every Nth scan cycle forces a full scan regardless of incremental mode
FULL_SCAN_INTERVAL = 6


class WantedScanner:
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

            # Scan all Sonarr instances
            a, u, paths = self._scan_all_sonarr(settings, since)
            added += a
            updated += u
            scanned_paths.update(paths)

            # Scan all Radarr instances
            a, u, paths = self._scan_all_radarr(settings, since)
            added += a
            updated += u
            scanned_paths.update(paths)

            # Scan standalone items
            a, u, paths = self._scan_all_standalone()
            added += a
            updated += u
            scanned_paths.update(paths)

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

    # ─── Scan Helpers ────────────────────────────────────────────────────

    def _scan_all_sonarr(self, settings, since=None):
        """Scan all Sonarr instances. Returns (added, updated, paths)."""
        total_added = 0
        total_updated = 0
        all_paths = set()

        try:
            from config import get_sonarr_instances
            from sonarr_client import get_sonarr_client

            instances = get_sonarr_instances()
            for inst in instances:
                instance_name = inst.get("name", "Default")
                sonarr = get_sonarr_client(instance_name=instance_name)
                if sonarr:
                    a, u, paths = self._scan_sonarr_instance(sonarr, settings, instance_name, since)
                    total_added += a
                    total_updated += u
                    all_paths.update(paths)
        except Exception as e:
            logger.error("Wanted scan: Sonarr error: %s", e)

        return total_added, total_updated, all_paths

    def _scan_sonarr_instance(self, sonarr, settings, instance_name, since=None):
        """Scan a single Sonarr instance."""
        if settings.wanted_anime_only:
            series_list = sonarr.get_anime_series()
        else:
            series_list = sonarr.get_series()

        if since:
            since_iso = since.isoformat() + "Z"
            series_list = [
                s
                for s in series_list
                if (s.get("lastInfoSync") or s.get("added") or "") >= since_iso
            ]
            logger.debug(
                "Incremental Sonarr scan: %d series modified since %s",
                len(series_list),
                since_iso,
            )

        total_added = 0
        total_updated = 0
        all_paths = set()

        self._progress = {
            "current": 0,
            "total": len(series_list),
            "phase": f"Sonarr ({instance_name})",
            "added": 0,
            "updated": 0,
        }
        if self._socketio:
            self._socketio.emit("wanted_scan_progress", dict(self._progress))

        yield_ms = getattr(settings, "scan_yield_ms", 0)
        for idx, series in enumerate(series_list, 1):
            series_id = series.get("id")
            if not series_id:
                continue
            with batch_upsert_context():
                a, u, paths = scan_sonarr_series(
                    sonarr,
                    series_id,
                    settings,
                    series,
                    instance_name,
                    auto_extract_fn=self._maybe_auto_extract,
                )
            total_added += a
            total_updated += u
            all_paths.update(paths)
            self._progress.update({"current": idx, "added": total_added, "updated": total_updated})
            if self._socketio:
                self._socketio.emit("wanted_scan_progress", dict(self._progress))
            if yield_ms > 0:
                time.sleep(yield_ms / 1000.0)

        return total_added, total_updated, all_paths

    def _scan_all_radarr(self, settings, since=None):
        """Scan all Radarr instances. Returns (added, updated, paths)."""
        total_added = 0
        total_updated = 0
        all_paths = set()

        try:
            from config import get_radarr_instances
            from radarr_client import get_radarr_client

            instances = get_radarr_instances()
            for inst in instances:
                instance_name = inst.get("name", "Default")
                radarr = get_radarr_client(instance_name=instance_name)
                if radarr:
                    a, u, paths = self._scan_radarr_instance(radarr, settings, instance_name, since)
                    total_added += a
                    total_updated += u
                    all_paths.update(paths)
        except Exception as e:
            logger.error("Wanted scan: Radarr error: %s", e)

        return total_added, total_updated, all_paths

    def _scan_radarr_instance(self, radarr, settings, instance_name, since=None):
        """Scan a single Radarr instance."""
        if settings.wanted_anime_movies_only:
            movies = radarr.get_anime_movies()
        else:
            movies = radarr.get_movies()

        if since:
            since_iso = since.isoformat() + "Z"
            movies = [
                m
                for m in movies
                if ((m.get("movieFile") or {}).get("dateAdded") or m.get("added") or "")
                >= since_iso
            ]
            logger.debug(
                "Incremental Radarr scan: %d movies modified since %s",
                len(movies),
                since_iso,
            )

        total_added = 0
        total_updated = 0
        all_paths = set()

        self._progress = {
            "current": 0,
            "total": len(movies),
            "phase": f"Radarr ({instance_name})",
            "added": 0,
            "updated": 0,
        }
        if self._socketio:
            self._socketio.emit("wanted_scan_progress", dict(self._progress))

        yield_ms = getattr(settings, "scan_yield_ms", 0)
        for idx, movie in enumerate(movies, 1):
            with batch_upsert_context():
                a, u, paths = scan_radarr_movie(
                    radarr,
                    movie,
                    settings,
                    instance_name,
                    auto_extract_fn=self._maybe_auto_extract,
                )
            total_added += a
            total_updated += u
            all_paths.update(paths)
            self._progress.update({"current": idx, "added": total_added, "updated": total_updated})
            if self._socketio:
                self._socketio.emit("wanted_scan_progress", dict(self._progress))
            if yield_ms > 0:
                time.sleep(yield_ms / 1000.0)

        return total_added, total_updated, all_paths

    def _scan_all_standalone(self):
        """Scan standalone folders. Returns (added, updated, paths)."""
        try:
            from config import is_standalone_mode

            if not is_standalone_mode():
                return 0, 0, set()
        except Exception as e:
            logger.error("Wanted scan: Standalone error: %s", e)
            return 0, 0, set()

        try:
            from standalone.scanner import StandaloneScanner

            if not hasattr(self, "_standalone_scanner"):
                self._standalone_scanner = StandaloneScanner()

            summary = self._standalone_scanner.scan_all_folders()
            added = summary.get("wanted_added", 0)

            scanned_paths = set()
            try:
                from db import get_db

                db = get_db()
                rows = db.execute(
                    "SELECT file_path FROM wanted_items WHERE instance_name='standalone'"
                ).fetchall()
                scanned_paths = {row[0] for row in rows}
            except Exception as e:
                logger.debug("Could not collect standalone scanned paths: %s", e)

            return added, 0, scanned_paths
        except Exception as e:
            logger.error("Wanted scan: Standalone error: %s", e)
            return 0, 0, set()

    def _maybe_auto_extract(self, item_id: int, file_path: str) -> None:
        """Trigger embedded subtitle extraction if wanted_auto_extract is enabled."""
        if item_id is None:
            logger.warning("[Auto-Extract] Skipped — item_id is None for %s", file_path)
            return
        try:
            settings = get_settings()
            if not getattr(settings, "wanted_auto_extract", False):
                return
            from routes.wanted import _extract_embedded_sub

            auto_translate = getattr(settings, "wanted_auto_translate", False)
            logger.info("[Auto-Extract] item %d -> %s", item_id, file_path)
            _extract_embedded_sub(item_id, file_path, auto_translate=auto_translate)
        except Exception as exc:
            logger.warning("[Auto-Extract] Failed for item %d: %s", item_id, exc)

    def _cleanup(self, scanned_paths: set) -> int:
        """Remove wanted items whose files no longer exist or whose subs appeared."""
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

    def start_scheduler(self, socketio=None, app=None):
        """Start the periodic scan and search schedulers."""
        self._socketio = socketio
        self._app = app
        self._scheduler_started_at = datetime.now(UTC)
        settings = get_settings()

        scan_interval = settings.wanted_scan_interval_hours
        if scan_interval > 0:
            if settings.wanted_scan_on_startup:
                thread = threading.Thread(target=self._run_scan_with_context, daemon=True)
                thread.start()
            self._schedule_next_scan(scan_interval)
            logger.info("Wanted scan scheduler started (every %dh)", scan_interval)
        else:
            logger.info("Wanted scan scheduler disabled (interval=0)")

        search_interval = settings.wanted_search_interval_hours
        if search_interval > 0:
            if settings.wanted_search_on_startup:
                thread = threading.Thread(
                    target=self._run_search_with_context,
                    args=(socketio,),
                    daemon=True,
                )
                thread.start()
            self._schedule_next_search(search_interval)
            logger.info("Wanted search scheduler started (every %dh)", search_interval)
        else:
            logger.info("Wanted search scheduler disabled (interval=0)")

    def stop_scheduler(self):
        """Cancel all scheduled timers."""
        if self._timer:
            self._timer.cancel()
            self._timer = None
        if self._search_timer:
            self._search_timer.cancel()
            self._search_timer = None
        logger.info("Wanted schedulers stopped")

    def _schedule_next_scan(self, interval_hours):
        self._timer = threading.Timer(
            interval_hours * 3600,
            self._scheduled_scan,
            args=(interval_hours,),
        )
        self._timer.daemon = True
        self._timer.start()

    def _run_scan_with_context(self):
        if self._app is not None:
            with self._app.app_context():
                self.scan_all()
        else:
            self.scan_all()

    def _run_search_with_context(self, socketio=None, include_upgrades: bool | None = None):
        if self._app is not None:
            with self._app.app_context():
                self.search_all(socketio, include_upgrades=include_upgrades)
        else:
            self.search_all(socketio, include_upgrades=include_upgrades)

    def _scheduled_scan(self, interval_hours):
        logger.info("Wanted scheduled scan starting")
        self._run_scan_with_context()
        self._schedule_next_scan(interval_hours)

    def _schedule_next_search(self, interval_hours):
        self._search_timer = threading.Timer(
            interval_hours * 3600,
            self._scheduled_search,
            args=(interval_hours,),
        )
        self._search_timer.daemon = True
        self._search_timer.start()

    def _scheduled_search(self, interval_hours):
        logger.info("Wanted scheduled search starting")
        self._run_search_with_context(self._socketio)
        self._schedule_next_search(interval_hours)
