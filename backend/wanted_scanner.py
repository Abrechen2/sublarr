"""Wanted subtitle scanner — detects missing target language subtitles.

Scans Sonarr series and Radarr movies, checks local filesystem for
existing target language subtitles, and populates the wanted_items table.
Includes a threading-based scheduler for periodic rescans.
"""

import os
import time
import logging
import threading
from datetime import datetime

from config import get_settings, map_path
from translator import detect_existing_target
from database import (
    upsert_wanted_item,
    delete_wanted_items,
    get_all_wanted_file_paths,
)

logger = logging.getLogger(__name__)

_scanner = None
_scanner_lock = threading.Lock()


def get_scanner():
    """Get or create the singleton WantedScanner."""
    global _scanner
    if _scanner is not None:
        return _scanner
    with _scanner_lock:
        if _scanner is not None:
            return _scanner
        _scanner = WantedScanner()
        return _scanner


def invalidate_scanner():
    """Reset the scanner singleton (e.g. after config change)."""
    global _scanner
    if _scanner:
        _scanner.stop_scheduler()
    _scanner = None


class WantedScanner:
    """Scans Sonarr/Radarr for episodes/movies missing target language subtitles."""

    def __init__(self):
        self._scan_lock = threading.Lock()
        self._scanning = False
        self._timer = None
        self._last_scan_at = ""
        self._last_summary = {}

    @property
    def is_scanning(self):
        return self._scanning

    @property
    def last_scan_at(self):
        return self._last_scan_at

    @property
    def last_summary(self):
        return self._last_summary

    def scan_all(self) -> dict:
        """Run a full scan of Sonarr series and Radarr movies.

        Returns summary dict: {added, updated, removed, total_wanted, duration_seconds}
        """
        if not self._scan_lock.acquire(blocking=False):
            logger.warning("Wanted scan already running, skipping")
            return {"error": "scan_already_running"}

        self._scanning = True
        start = time.time()
        added = 0
        updated = 0
        scanned_paths = set()

        try:
            settings = get_settings()

            # Scan Sonarr episodes
            try:
                from sonarr_client import get_sonarr_client
                sonarr = get_sonarr_client()
                if sonarr:
                    a, u, paths = self._scan_sonarr(sonarr, settings)
                    added += a
                    updated += u
                    scanned_paths.update(paths)
            except Exception as e:
                logger.error("Wanted scan: Sonarr error: %s", e)

            # Scan Radarr movies
            try:
                from radarr_client import get_radarr_client
                radarr = get_radarr_client()
                if radarr:
                    a, u, paths = self._scan_radarr(radarr, settings)
                    added += a
                    updated += u
                    scanned_paths.update(paths)
            except Exception as e:
                logger.error("Wanted scan: Radarr error: %s", e)

            # Cleanup: remove items whose files no longer exist or subs appeared
            removed = self._cleanup(scanned_paths)

            duration = round(time.time() - start, 1)
            from database import get_wanted_count
            total_wanted = get_wanted_count()

            summary = {
                "added": added,
                "updated": updated,
                "removed": removed,
                "total_wanted": total_wanted,
                "duration_seconds": duration,
            }

            self._last_scan_at = datetime.utcnow().isoformat()
            self._last_summary = summary

            logger.info(
                "Wanted scan complete: +%d added, ~%d updated, -%d removed, %d total (%.1fs)",
                added, updated, removed, total_wanted, duration,
            )
            return summary

        except Exception as e:
            logger.exception("Wanted scan failed: %s", e)
            return {"error": str(e)}
        finally:
            self._scanning = False
            self._scan_lock.release()

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

            added, updated, _ = self._scan_sonarr_series(sonarr, series_id, settings)
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

    def _scan_sonarr(self, sonarr, settings):
        """Scan all Sonarr series. Returns (added, updated, scanned_paths)."""
        if settings.wanted_anime_only:
            series_list = sonarr.get_anime_series()
        else:
            series_list = sonarr.get_series()

        total_added = 0
        total_updated = 0
        all_paths = set()

        for series in series_list:
            series_id = series.get("id")
            if not series_id:
                continue
            a, u, paths = self._scan_sonarr_series(sonarr, series_id, settings, series)
            total_added += a
            total_updated += u
            all_paths.update(paths)

        return total_added, total_updated, all_paths

    def _scan_sonarr_series(self, sonarr, series_id, settings, series_info=None):
        """Scan a single series. Returns (added, updated, scanned_paths)."""
        if not series_info:
            series_info = sonarr.get_series_by_id(series_id) or {}

        series_title = series_info.get("title", f"Series {series_id}")
        episodes = sonarr.get_episodes(series_id)
        if not episodes:
            return 0, 0, set()

        added = 0
        updated = 0
        scanned_paths = set()

        for ep in episodes:
            if not ep.get("hasFile"):
                continue

            episode_id = ep.get("id")
            file_path = None

            # Try to get path from episode data directly
            ep_file = ep.get("episodeFile")
            if ep_file and ep_file.get("path"):
                file_path = ep_file["path"]
            else:
                file_path = sonarr.get_episode_file_path(episode_id)

            if not file_path:
                continue

            mapped_path = map_path(file_path)
            if not os.path.exists(mapped_path):
                continue

            scanned_paths.add(mapped_path)

            # Check existing target subs (no ffprobe — fast external-only check)
            existing = detect_existing_target(mapped_path)
            if existing == "ass":
                continue  # Goal achieved

            season_num = ep.get("seasonNumber", 0)
            episode_num = ep.get("episodeNumber", 0)
            season_episode = f"S{season_num:02d}E{episode_num:02d}"
            title = f"{series_title} — {season_episode}"
            existing_sub = existing or ""

            row_id = upsert_wanted_item(
                item_type="episode",
                file_path=mapped_path,
                title=title,
                season_episode=season_episode,
                existing_sub=existing_sub,
                missing_languages=[settings.target_language],
                sonarr_series_id=series_id,
                sonarr_episode_id=episode_id,
            )

            if row_id:
                # Simple heuristic: if we did an INSERT vs UPDATE
                # The upsert always returns an id, so we count both
                added += 1

        return added, updated, scanned_paths

    def _scan_radarr(self, radarr, settings):
        """Scan all Radarr movies. Returns (added, updated, scanned_paths)."""
        if settings.wanted_anime_only:
            movies = radarr.get_anime_movies()
        else:
            movies = radarr.get_movies()

        added = 0
        updated = 0
        scanned_paths = set()

        for movie in movies:
            if not movie.get("hasFile"):
                continue

            movie_id = movie.get("id")
            movie_title = movie.get("title", f"Movie {movie_id}")

            # Get file path
            file_path = None
            movie_file = movie.get("movieFile")
            if movie_file and movie_file.get("path"):
                file_path = movie_file["path"]
            else:
                # Fallback: get movie file separately
                file_id = movie.get("movieFileId")
                if file_id and file_id != 0:
                    file_info = radarr.get_movie_file(file_id)
                    if file_info:
                        file_path = file_info.get("path")

            if not file_path:
                continue

            mapped_path = map_path(file_path)
            if not os.path.exists(mapped_path):
                continue

            scanned_paths.add(mapped_path)

            existing = detect_existing_target(mapped_path)
            if existing == "ass":
                continue

            existing_sub = existing or ""
            row_id = upsert_wanted_item(
                item_type="movie",
                file_path=mapped_path,
                title=movie_title,
                existing_sub=existing_sub,
                missing_languages=[settings.target_language],
                radarr_movie_id=movie_id,
            )

            if row_id:
                added += 1

        return added, updated, scanned_paths

    def _cleanup(self, scanned_paths: set) -> int:
        """Remove wanted items whose files no longer exist or whose subs appeared."""
        existing_paths = get_all_wanted_file_paths()
        to_remove = []

        for path in existing_paths:
            # File no longer exists on disk
            if not os.path.exists(path):
                to_remove.append(path)
                continue

            # Target ASS appeared since last scan
            existing = detect_existing_target(path)
            if existing == "ass":
                to_remove.append(path)
                continue

            # Path wasn't in this scan (series/movie removed from arr?)
            # Only remove if scanned_paths is non-empty (a scan actually ran)
            if scanned_paths and path not in scanned_paths:
                to_remove.append(path)

        if to_remove:
            delete_wanted_items(to_remove)
            logger.info("Wanted cleanup: removed %d items", len(to_remove))

        return len(to_remove)

    # ─── Scheduler ──────────────────────────────────────────────────────────

    def start_scheduler(self):
        """Start the periodic scan scheduler."""
        settings = get_settings()
        interval = settings.wanted_scan_interval_hours

        if interval <= 0:
            logger.info("Wanted scheduler disabled (interval=0)")
            return

        if settings.wanted_scan_on_startup:
            # Run initial scan in background thread
            thread = threading.Thread(target=self.scan_all, daemon=True)
            thread.start()

        self._schedule_next(interval)
        logger.info("Wanted scheduler started (every %dh)", interval)

    def stop_scheduler(self):
        """Cancel the scheduled timer."""
        if self._timer:
            self._timer.cancel()
            self._timer = None
            logger.info("Wanted scheduler stopped")

    def _schedule_next(self, interval_hours):
        """Schedule the next scan."""
        self._timer = threading.Timer(
            interval_hours * 3600,
            self._scheduled_scan,
            args=(interval_hours,),
        )
        self._timer.daemon = True
        self._timer.start()

    def _scheduled_scan(self, interval_hours):
        """Execute a scheduled scan and reschedule."""
        logger.info("Wanted scheduled scan starting")
        self.scan_all()
        self._schedule_next(interval_hours)
