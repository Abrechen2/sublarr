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
from translator import detect_existing_target_for_lang, get_output_path_for_lang
from upgrade_scorer import score_existing_subtitle
from ass_utils import run_ffprobe, has_target_language_stream
from db.wanted import upsert_wanted_item, delete_wanted_items, get_all_wanted_file_paths
from db.profiles import get_series_profile, get_movie_profile, get_default_profile

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
        self._search_lock = threading.Lock()
        self._scanning = False
        self._searching = False
        self._timer = None
        self._search_timer = None
        self._socketio = None
        self._last_scan_at = ""
        self._last_search_at = ""
        self._last_summary = {}

    @property
    def is_scanning(self):
        return self._scanning

    @property
    def is_searching(self):
        return self._searching

    @property
    def last_scan_at(self):
        return self._last_scan_at

    @property
    def last_search_at(self):
        return self._last_search_at

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

            # Scan all Sonarr instances
            try:
                from sonarr_client import get_sonarr_client
                from config import get_sonarr_instances
                instances = get_sonarr_instances()
                for inst in instances:
                    instance_name = inst.get("name", "Default")
                    sonarr = get_sonarr_client(instance_name=instance_name)
                    if sonarr:
                        a, u, paths = self._scan_sonarr(sonarr, settings, instance_name)
                        added += a
                        updated += u
                        scanned_paths.update(paths)
            except Exception as e:
                logger.error("Wanted scan: Sonarr error: %s", e)

            # Scan all Radarr instances
            try:
                from radarr_client import get_radarr_client
                from config import get_radarr_instances
                instances = get_radarr_instances()
                for inst in instances:
                    instance_name = inst.get("name", "Default")
                    radarr = get_radarr_client(instance_name=instance_name)
                    if radarr:
                        a, u, paths = self._scan_radarr(radarr, settings, instance_name)
                        added += a
                        updated += u
                        scanned_paths.update(paths)
            except Exception as e:
                logger.error("Wanted scan: Radarr error: %s", e)

            # Cleanup: remove items whose files no longer exist or subs appeared
            removed = self._cleanup(scanned_paths)

            duration = round(time.time() - start, 1)
            from db.wanted import get_wanted_count
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

            added, updated, _ = self._scan_radarr_movie(radarr, movie, settings)
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

    def _scan_radarr_movie(self, radarr, movie, settings, instance_name=None):
        """Scan a single Radarr movie. Returns (added, updated, scanned_paths)."""
        added = 0
        updated = 0
        scanned_paths = set()

        if not movie.get("hasFile"):
            return added, updated, scanned_paths

        movie_id = movie.get("id")
        movie_title = movie.get("title", f"Movie {movie_id}")

        # Get file path
        file_path = None
        movie_file = movie.get("movieFile")
        if movie_file and movie_file.get("path"):
            file_path = movie_file["path"]
        else:
            file_id = movie.get("movieFileId")
            if file_id and file_id != 0:
                file_info = radarr.get_movie_file(file_id)
                if file_info:
                    file_path = file_info.get("path")

        if not file_path:
            return added, updated, scanned_paths

        mapped_path = map_path(file_path)
        if not os.path.exists(mapped_path):
            return added, updated, scanned_paths

        scanned_paths.add(mapped_path)

        profile = get_movie_profile(movie_id)
        target_languages = profile.get("target_languages", [settings.target_language])
        target_language_names = profile.get("target_language_names", [settings.target_language_name])

        probe_data = None
        if settings.use_embedded_subs and mapped_path.lower().endswith(('.mkv', '.mp4', '.m4v')):
            try:
                probe_data = run_ffprobe(mapped_path, use_cache=True)
            except Exception as e:
                logger.debug("ffprobe failed for %s: %s", mapped_path, e)

        for target_lang, target_name in zip(target_languages, target_language_names):
            existing = detect_existing_target_for_lang(mapped_path, target_lang, probe_data)
            if existing == "ass":
                continue

            embedded_sub = None
            if probe_data:
                embedded_sub = has_target_language_stream(probe_data, target_lang)
                if embedded_sub == "ass":
                    existing = "embedded_ass"
                elif embedded_sub == "srt":
                    existing = "embedded_srt"

            title = movie_title
            if len(target_languages) > 1:
                title = f"{title} [{target_lang.upper()}]"
            existing_sub = existing or ""

            is_upgrade = False
            cur_score = 0
            if existing_sub == "srt" and settings.upgrade_enabled:
                srt_path = get_output_path_for_lang(mapped_path, "srt", target_lang)
                if os.path.exists(srt_path):
                    _, cur_score = score_existing_subtitle(srt_path)
                    is_upgrade = True

            row_id = upsert_wanted_item(
                item_type="movie",
                file_path=mapped_path,
                title=title,
                existing_sub=existing_sub,
                missing_languages=[target_lang],
                radarr_movie_id=movie_id,
                upgrade_candidate=is_upgrade,
                current_score=cur_score,
                target_language=target_lang,
                instance_name=instance_name or "",
            )

            if row_id:
                added += 1

        return added, updated, scanned_paths

    def _scan_sonarr(self, sonarr, settings, instance_name=None):
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
            a, u, paths = self._scan_sonarr_series(sonarr, series_id, settings, series, instance_name)
            total_added += a
            total_updated += u
            all_paths.update(paths)

        return total_added, total_updated, all_paths

    def _scan_sonarr_series(self, sonarr, series_id, settings, series_info=None, instance_name=None):
        """Scan a single series. Returns (added, updated, scanned_paths)."""
        if not series_info:
            series_info = sonarr.get_series_by_id(series_id) or {}

        series_title = series_info.get("title", f"Series {series_id}")
        episodes = sonarr.get_episodes(series_id)
        if not episodes:
            return 0, 0, set()

        # Load language profile for this series
        profile = get_series_profile(series_id)
        target_languages = profile.get("target_languages", [settings.target_language])
        target_language_names = profile.get("target_language_names", [settings.target_language_name])

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

            season_num = ep.get("seasonNumber", 0)
            episode_num = ep.get("episodeNumber", 0)
            season_episode = f"S{season_num:02d}E{episode_num:02d}"

            # Check embedded subtitles if enabled
            probe_data = None
            if settings.use_embedded_subs and mapped_path.lower().endswith(('.mkv', '.mp4', '.m4v')):
                try:
                    probe_data = run_ffprobe(mapped_path, use_cache=True)
                except Exception as e:
                    logger.debug("ffprobe failed for %s: %s", mapped_path, e)

            # Check each target language from the profile
            for target_lang, target_name in zip(target_languages, target_language_names):
                existing = detect_existing_target_for_lang(mapped_path, target_lang, probe_data)
                if existing == "ass":
                    continue  # Goal achieved for this language

                # Check embedded streams if probe_data available
                embedded_sub = None
                if probe_data:
                    embedded_sub = has_target_language_stream(probe_data, target_lang)
                    if embedded_sub == "ass":
                        existing = "embedded_ass"
                    elif embedded_sub == "srt":
                        existing = "embedded_srt"

                title = f"{series_title} — {season_episode}"
                if len(target_languages) > 1:
                    title = f"{title} [{target_lang.upper()}]"
                existing_sub = existing or ""

                # Score existing subtitle for upgrade detection
                is_upgrade = False
                cur_score = 0
                if existing_sub == "srt" and settings.upgrade_enabled:
                    srt_path = get_output_path_for_lang(mapped_path, "srt", target_lang)
                    if os.path.exists(srt_path):
                        _, cur_score = score_existing_subtitle(srt_path)
                        is_upgrade = True

                row_id = upsert_wanted_item(
                    item_type="episode",
                    file_path=mapped_path,
                    title=title,
                    season_episode=season_episode,
                    existing_sub=existing_sub,
                    missing_languages=[target_lang],
                    sonarr_series_id=series_id,
                    sonarr_episode_id=episode_id,
                    upgrade_candidate=is_upgrade,
                    current_score=cur_score,
                    target_language=target_lang,
                    instance_name=instance_name or "",
                )

                if row_id:
                    added += 1

        return added, updated, scanned_paths

    def _scan_radarr(self, radarr, settings, instance_name=None):
        """Scan all Radarr movies. Returns (added, updated, scanned_paths)."""
        if settings.wanted_anime_movies_only:
            movies = radarr.get_anime_movies()
        else:
            movies = radarr.get_movies()

        total_added = 0
        total_updated = 0
        all_paths = set()

        for movie in movies:
            added, updated, paths = self._scan_radarr_movie(radarr, movie, settings, instance_name)
            total_added += added
            total_updated += updated
            all_paths.update(paths)

        return total_added, total_updated, all_paths

    def _cleanup(self, scanned_paths: set) -> int:
        """Remove wanted items whose files no longer exist or whose subs appeared.

        Language-aware: checks per target_language from each wanted item.
        """
        from db.wanted import get_wanted_items_for_cleanup

        items = get_wanted_items_for_cleanup()
        to_remove_ids = []

        for item in items:
            path = item["file_path"]
            target_lang = item.get("target_language", "")

            # File no longer exists on disk
            if not os.path.exists(path):
                to_remove_ids.append(item["id"])
                continue

            # Target ASS appeared since last scan (language-aware)
            if target_lang:
                existing = detect_existing_target_for_lang(path, target_lang)
            else:
                from translator import detect_existing_target
                existing = detect_existing_target(path)
            if existing == "ass":
                to_remove_ids.append(item["id"])
                continue

            # Path wasn't in this scan (series/movie removed from arr?)
            if scanned_paths and path not in scanned_paths:
                to_remove_ids.append(item["id"])

        if to_remove_ids:
            from db.wanted import delete_wanted_items_by_ids
            delete_wanted_items_by_ids(to_remove_ids)
            logger.info("Wanted cleanup: removed %d items", len(to_remove_ids))

        return len(to_remove_ids)

    # ─── Search All ────────────────────────────────────────────────────────

    def search_all(self, socketio=None) -> dict:
        """Search providers for all wanted items (respects max_items_per_run).

        Returns summary dict: {total, processed, found, failed, skipped}
        """
        if not self._search_lock.acquire(blocking=False):
            logger.warning("Wanted search already running, skipping")
            return {"error": "search_already_running"}

        self._searching = True
        start = time.time()

        try:
            settings = get_settings()
            max_items = settings.wanted_search_max_items_per_run

            from db.wanted import get_wanted_items
            result = get_wanted_items(page=1, per_page=max_items, status="wanted")
            items = result.get("data", [])

            # Filter out items searched too recently (within last hour)
            now_ts = time.time()
            eligible = []
            for item in items:
                if item.get("last_search_at"):
                    try:
                        from datetime import datetime
                        last_search = datetime.fromisoformat(item["last_search_at"])
                        age_hours = (datetime.utcnow() - last_search).total_seconds() / 3600
                        if age_hours < 1:
                            continue
                    except (ValueError, TypeError):
                        pass
                if item["search_count"] < settings.wanted_max_search_attempts:
                    eligible.append(item)

            if not eligible:
                self._last_search_at = datetime.utcnow().isoformat()
                return {"total": 0, "processed": 0, "found": 0, "failed": 0, "skipped": 0}

            from wanted_search import process_wanted_item

            total = len(eligible)
            processed = 0
            found = 0
            failed = 0
            skipped = 0

            for item in eligible:
                try:
                    res = process_wanted_item(item["id"])
                    processed += 1
                    if res.get("status") == "found":
                        found += 1
                    elif res.get("status") == "failed":
                        failed += 1
                    else:
                        skipped += 1

                    if socketio:
                        socketio.emit("wanted_search_progress", {
                            "processed": processed,
                            "total": total,
                            "found": found,
                            "failed": failed,
                            "current_item": item.get("title", str(item["id"])),
                        })
                except Exception as e:
                    processed += 1
                    failed += 1
                    logger.warning("Search-all: error on item %d: %s", item["id"], e)

                # Rate limit between items
                if processed < total:
                    time.sleep(0.5)

            duration = round(time.time() - start, 1)
            self._last_search_at = datetime.utcnow().isoformat()

            summary = {
                "total": total,
                "processed": processed,
                "found": found,
                "failed": failed,
                "skipped": skipped,
                "duration_seconds": duration,
            }

            logger.info(
                "Wanted search complete: %d/%d processed, %d found, %d failed (%.1fs)",
                processed, total, found, failed, duration,
            )

            if socketio:
                socketio.emit("wanted_search_completed", summary)

            return summary

        except Exception as e:
            logger.exception("Wanted search failed: %s", e)
            return {"error": str(e)}
        finally:
            self._searching = False
            self._search_lock.release()

    # ─── Scheduler ──────────────────────────────────────────────────────────

    def start_scheduler(self, socketio=None):
        """Start the periodic scan and search schedulers."""
        self._socketio = socketio
        settings = get_settings()

        # Scan scheduler
        scan_interval = settings.wanted_scan_interval_hours
        if scan_interval > 0:
            if settings.wanted_scan_on_startup:
                thread = threading.Thread(target=self.scan_all, daemon=True)
                thread.start()
            self._schedule_next_scan(scan_interval)
            logger.info("Wanted scan scheduler started (every %dh)", scan_interval)
        else:
            logger.info("Wanted scan scheduler disabled (interval=0)")

        # Search scheduler
        search_interval = settings.wanted_search_interval_hours
        if search_interval > 0:
            if settings.wanted_search_on_startup:
                thread = threading.Thread(
                    target=self.search_all, args=(socketio,), daemon=True,
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
        self._schedule_next_scan(interval_hours)

    def _schedule_next_search(self, interval_hours):
        """Schedule the next search."""
        self._search_timer = threading.Timer(
            interval_hours * 3600,
            self._scheduled_search,
            args=(interval_hours,),
        )
        self._search_timer.daemon = True
        self._search_timer.start()

    def _scheduled_search(self, interval_hours):
        """Execute a scheduled search and reschedule."""
        logger.info("Wanted scheduled search starting")
        self.search_all(self._socketio)
        self._schedule_next_search(interval_hours)
