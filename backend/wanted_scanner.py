"""Wanted subtitle scanner — detects missing target language subtitles.

Scans Sonarr series and Radarr movies, checks local filesystem for
existing target language subtitles, and populates the wanted_items table.
Includes a threading-based scheduler for periodic rescans.

Supports incremental scan mode: after an initial full scan, subsequent scans
only process items modified since the last scan timestamp. Every Nth scan
(FULL_SCAN_INTERVAL) forces a full rescan as safety fallback.
"""

import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime

from ass_utils import get_media_streams, has_target_language_audio, has_target_language_stream
from config import get_settings, map_path
from db.profiles import get_movie_profile, get_series_profile
from db.wanted import upsert_wanted_item
from translator import detect_existing_target_for_lang, get_output_path_for_lang
from upgrade_scorer import score_existing_subtitle

logger = logging.getLogger(__name__)

# Every Nth scan cycle forces a full scan regardless of incremental mode
FULL_SCAN_INTERVAL = 6


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
        self._app = None  # Flask app reference for background thread context
        self._progress = {"current": 0, "total": 0, "phase": "", "added": 0, "updated": 0}
        self._last_scan_at = ""
        self._last_search_at = ""
        self._last_summary = {}
        # Incremental scan state
        self._last_scan_timestamp = None  # datetime of last successful scan
        self._scan_count = 0  # counter for forcing full scan every N cycles
        self._cancel_event = threading.Event()  # signal to stop parallel search

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
        return self._last_scan_at

    @property
    def last_search_at(self):
        return self._last_search_at

    @property
    def last_summary(self):
        return self._last_summary

    def scan_all(self, incremental=True) -> dict:
        """Run a scan of Sonarr series and Radarr movies.

        Supports incremental mode: if incremental=True and a previous scan
        timestamp exists, only processes items modified since then. Every
        FULL_SCAN_INTERVAL cycles forces a full scan as safety fallback.

        Args:
            incremental: Whether to use incremental scanning (default True).

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

        # Determine if this should be a full or incremental scan
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

            # Scan all Sonarr instances
            try:
                from config import get_sonarr_instances
                from sonarr_client import get_sonarr_client

                instances = get_sonarr_instances()
                for inst in instances:
                    instance_name = inst.get("name", "Default")
                    sonarr = get_sonarr_client(instance_name=instance_name)
                    if sonarr:
                        a, u, paths = self._scan_sonarr(
                            sonarr,
                            settings,
                            instance_name,
                            since=self._last_scan_timestamp if is_incremental else None,
                        )
                        added += a
                        updated += u
                        scanned_paths.update(paths)
            except Exception as e:
                logger.error("Wanted scan: Sonarr error: %s", e)

            # Scan all Radarr instances
            try:
                from config import get_radarr_instances
                from radarr_client import get_radarr_client

                instances = get_radarr_instances()
                for inst in instances:
                    instance_name = inst.get("name", "Default")
                    radarr = get_radarr_client(instance_name=instance_name)
                    if radarr:
                        a, u, paths = self._scan_radarr(
                            radarr,
                            settings,
                            instance_name,
                            since=self._last_scan_timestamp if is_incremental else None,
                        )
                        added += a
                        updated += u
                        scanned_paths.update(paths)
            except Exception as e:
                logger.error("Wanted scan: Radarr error: %s", e)

            # Scan standalone items (if standalone mode enabled)
            try:
                from config import get_settings as _get_standalone_settings

                if getattr(_get_standalone_settings(), "standalone_enabled", False):
                    sa, su, sp = self._scan_standalone()
                    added += sa
                    updated += su
                    scanned_paths.update(sp)
            except Exception as e:
                logger.error("Wanted scan: Standalone error: %s", e)

            # Cleanup: remove items whose files no longer exist or subs appeared
            # Only run full cleanup on full scans; incremental skips path-based removal
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

            self._last_scan_at = datetime.now(UTC).isoformat()
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
            return summary

        except Exception as e:
            logger.exception("Wanted scan failed: %s", e)
            return {"error": str(e)}
        finally:
            self._scanning = False
            self._progress = {"current": 0, "total": 0, "phase": "", "added": 0, "updated": 0}
            self._scan_lock.release()

    def force_full_scan(self) -> dict:
        """Reset incremental state and run a full scan.

        Useful for manual triggers from the UI or API when
        a complete rescan is desired regardless of cycle position.
        """
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
        target_language_names = profile.get(
            "target_language_names", [settings.target_language_name]
        )

        probe_data = None
        if settings.use_embedded_subs and mapped_path.lower().endswith((".mkv", ".mp4", ".m4v")):
            try:
                probe_data = get_media_streams(mapped_path, use_cache=True)
            except Exception as e:
                logger.debug("ffprobe failed for %s: %s", mapped_path, e)

        for target_lang, target_name in zip(target_languages, target_language_names):
            existing = detect_existing_target_for_lang(mapped_path, target_lang, probe_data)
            if existing == "ass":
                continue

            embedded_sub = None
            if probe_data:
                # Skip if target language audio track exists (dub available)
                if has_target_language_audio(probe_data, target_lang):
                    continue
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

            item_id, was_updated = upsert_wanted_item(
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
                subtitle_type="full",
            )
            if was_updated:
                updated += 1
            else:
                added += 1
                # Newly inserted item — trigger auto-extract if embedded sub detected
                if existing_sub in ("embedded_ass", "embedded_srt"):
                    self._maybe_auto_extract(item_id, mapped_path)

            # Forced subtitle handling based on profile preference
            forced_preference = profile.get("forced_preference", "disabled")
            if forced_preference == "separate":
                existing_forced = detect_existing_target_for_lang(
                    mapped_path, target_lang, probe_data, subtitle_type="forced"
                )
                if existing_forced is None:
                    forced_title = f"{title} [Forced]"
                    _, forced_was_updated = upsert_wanted_item(
                        item_type="movie",
                        file_path=mapped_path,
                        title=forced_title,
                        existing_sub="",
                        missing_languages=[target_lang],
                        radarr_movie_id=movie_id,
                        upgrade_candidate=False,
                        current_score=0,
                        target_language=target_lang,
                        instance_name=instance_name or "",
                        subtitle_type="forced",
                    )
                    if forced_was_updated:
                        updated += 1
                    else:
                        added += 1
            # "auto" and "disabled" do not create dedicated forced wanted items

        return added, updated, scanned_paths

    def _scan_sonarr(self, sonarr, settings, instance_name=None, since=None):
        """Scan all Sonarr series. Returns (added, updated, scanned_paths).

        Args:
            sonarr: Sonarr API client instance.
            settings: Application settings.
            instance_name: Name of the Sonarr instance.
            since: If set (datetime), only scan series updated after this time (incremental).
        """
        if settings.wanted_anime_only:
            series_list = sonarr.get_anime_series()
        else:
            series_list = sonarr.get_series()

        # Incremental filter: only process series modified since last scan
        if since:
            since_iso = since.isoformat() + "Z"
            filtered = []
            for s in series_list:
                # Sonarr series have 'lastInfoSync' or 'added' timestamps
                updated = s.get("lastInfoSync") or s.get("added") or ""
                if updated >= since_iso:
                    filtered.append(s)
            logger.debug(
                "Incremental Sonarr scan: %d/%d series modified since %s",
                len(filtered),
                len(series_list),
                since_iso,
            )
            series_list = filtered

        total_added = 0
        total_updated = 0
        all_paths = set()
        total = len(series_list)

        self._progress = {
            "current": 0,
            "total": total,
            "phase": f"Sonarr ({instance_name})",
            "added": 0,
            "updated": 0,
        }
        if self._socketio:
            self._socketio.emit("wanted_scan_progress", dict(self._progress))

        for idx, series in enumerate(series_list, 1):
            series_id = series.get("id")
            if not series_id:
                continue
            a, u, paths = self._scan_sonarr_series(
                sonarr, series_id, settings, series, instance_name
            )
            total_added += a
            total_updated += u
            all_paths.update(paths)
            self._progress.update({"current": idx, "added": total_added, "updated": total_updated})
            if self._socketio:
                self._socketio.emit("wanted_scan_progress", dict(self._progress))

        return total_added, total_updated, all_paths

    def _batch_probe(self, paths):
        """Run metadata probing on multiple paths in parallel using ThreadPoolExecutor.

        Uses the configured scan_metadata_engine (via get_media_streams) and
        scan_metadata_max_workers from settings.

        Args:
            paths: List of file paths to probe.

        Returns:
            Dict mapping path -> probe_data (or None on error).
        """
        from config import get_settings

        max_workers = getattr(get_settings(), "scan_metadata_max_workers", 4)
        results = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_path = {executor.submit(get_media_streams, p, True): p for p in paths}
            for future in as_completed(future_to_path):
                path = future_to_path[future]
                try:
                    results[path] = future.result()
                except Exception as e:
                    logger.debug("probe failed for %s: %s", path, e)
                    results[path] = None
        return results

    def _maybe_auto_extract(self, item_id: int, file_path: str) -> None:
        """Trigger embedded subtitle extraction if wanted_auto_extract is enabled.

        Only called for newly-inserted wanted items whose existing_sub is
        "embedded_ass" or "embedded_srt". Errors are caught so the scanner
        never aborts due to a failed extraction.
        """
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

    def _scan_sonarr_series(
        self, sonarr, series_id, settings, series_info=None, instance_name=None
    ):
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
        target_language_names = profile.get(
            "target_language_names", [settings.target_language_name]
        )

        added = 0
        updated = 0
        scanned_paths = set()

        # Collect episode file paths first for batch ffprobe
        episode_data = []
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

            episode_data.append((ep, mapped_path))

        # Batch ffprobe for all eligible episode files
        probe_results = {}
        if settings.use_embedded_subs and episode_data:
            probeable = [
                mp for _, mp in episode_data if mp.lower().endswith((".mkv", ".mp4", ".m4v"))
            ]
            if probeable:
                probe_results = self._batch_probe(probeable)

        for ep, mapped_path in episode_data:
            scanned_paths.add(mapped_path)

            episode_id = ep.get("id")
            season_num = ep.get("seasonNumber", 0)
            episode_num = ep.get("episodeNumber", 0)
            season_episode = f"S{season_num:02d}E{episode_num:02d}"

            # Use pre-fetched probe data
            probe_data = probe_results.get(mapped_path)

            # Check each target language from the profile
            for target_lang, target_name in zip(target_languages, target_language_names):
                existing = detect_existing_target_for_lang(mapped_path, target_lang, probe_data)
                if existing == "ass":
                    continue  # Goal achieved for this language

                # Check embedded streams and audio tracks if probe_data available
                embedded_sub = None
                if probe_data:
                    # Skip if target language audio track exists (dub available)
                    if has_target_language_audio(probe_data, target_lang):
                        continue
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

                item_id, was_updated = upsert_wanted_item(
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
                    subtitle_type="full",
                )
                if was_updated:
                    updated += 1
                else:
                    added += 1
                    # Newly inserted item — trigger auto-extract if embedded sub detected
                    if existing_sub in ("embedded_ass", "embedded_srt"):
                        self._maybe_auto_extract(item_id, mapped_path)

                # Forced subtitle handling based on profile preference
                forced_preference = profile.get("forced_preference", "disabled")
                if forced_preference == "separate":
                    existing_forced = detect_existing_target_for_lang(
                        mapped_path, target_lang, probe_data, subtitle_type="forced"
                    )
                    if existing_forced is None:
                        forced_title = f"{title} [Forced]"
                        _, forced_was_updated = upsert_wanted_item(
                            item_type="episode",
                            file_path=mapped_path,
                            title=forced_title,
                            season_episode=season_episode,
                            existing_sub="",
                            missing_languages=[target_lang],
                            sonarr_series_id=series_id,
                            sonarr_episode_id=episode_id,
                            upgrade_candidate=False,
                            current_score=0,
                            target_language=target_lang,
                            instance_name=instance_name or "",
                            subtitle_type="forced",
                        )
                        if forced_was_updated:
                            updated += 1
                        else:
                            added += 1
                # "auto" and "disabled" do not create dedicated forced wanted items

        return added, updated, scanned_paths

    def _scan_radarr(self, radarr, settings, instance_name=None, since=None):
        """Scan all Radarr movies. Returns (added, updated, scanned_paths).

        Args:
            radarr: Radarr API client instance.
            settings: Application settings.
            instance_name: Name of the Radarr instance.
            since: If set (datetime), only scan movies modified after this time (incremental).
        """
        if settings.wanted_anime_movies_only:
            movies = radarr.get_anime_movies()
        else:
            movies = radarr.get_movies()

        # Incremental filter: only process movies modified since last scan
        if since:
            since_iso = since.isoformat() + "Z"
            filtered = []
            for m in movies:
                # Radarr movies have movieFile.dateAdded or added timestamps
                movie_file = m.get("movieFile") or {}
                date_added = movie_file.get("dateAdded") or m.get("added") or ""
                if date_added >= since_iso:
                    filtered.append(m)
            logger.debug(
                "Incremental Radarr scan: %d/%d movies modified since %s",
                len(filtered),
                len(movies),
                since_iso,
            )
            movies = filtered

        total_added = 0
        total_updated = 0
        all_paths = set()
        total = len(movies)

        self._progress = {
            "current": 0,
            "total": total,
            "phase": f"Radarr ({instance_name})",
            "added": 0,
            "updated": 0,
        }
        if self._socketio:
            self._socketio.emit("wanted_scan_progress", dict(self._progress))

        for idx, movie in enumerate(movies, 1):
            added, updated, paths = self._scan_radarr_movie(radarr, movie, settings, instance_name)
            total_added += added
            total_updated += updated
            all_paths.update(paths)
            self._progress.update({"current": idx, "added": total_added, "updated": total_updated})
            if self._socketio:
                self._socketio.emit("wanted_scan_progress", dict(self._progress))

        return total_added, total_updated, all_paths

    def _scan_standalone(self) -> tuple:
        """Scan standalone watched folders for wanted items.

        Creates a StandaloneScanner, runs a full scan, and collects
        scanned file paths from standalone entries in the DB.

        Returns:
            Tuple of (added, updated, scanned_paths).
        """
        from standalone.scanner import StandaloneScanner

        if not hasattr(self, "_standalone_scanner"):
            self._standalone_scanner = StandaloneScanner()

        summary = self._standalone_scanner.scan_all_folders()
        added = summary.get("wanted_added", 0)
        updated = 0

        # Collect all file paths from standalone wanted items
        scanned_paths = set()
        try:
            from db import _db_lock, get_db

            db = get_db()
            with _db_lock:
                rows = db.execute(
                    "SELECT file_path FROM wanted_items WHERE instance_name='standalone'"
                ).fetchall()
            scanned_paths = {row[0] for row in rows}
        except Exception as e:
            logger.debug("Could not collect standalone scanned paths: %s", e)

        return (added, updated, scanned_paths)

    def _cleanup(self, scanned_paths: set) -> int:
        """Remove wanted items whose files no longer exist or whose subs appeared.

        Language-aware: checks per target_language from each wanted item.
        Standalone items are only removed if their file no longer exists or
        target ASS appeared -- NOT if they are absent from Sonarr/Radarr scan paths.
        """
        from db.wanted import get_wanted_items_for_cleanup

        items = get_wanted_items_for_cleanup()
        to_remove_ids = []

        for item in items:
            path = item["file_path"]
            target_lang = item.get("target_language", "")
            instance_name = item.get("instance_name", "")

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
            # Skip this check for standalone items -- they manage their own cleanup
            if instance_name == "standalone":
                continue
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

        Uses ThreadPoolExecutor for parallel item processing instead of
        sequential processing with sleep delays. Provider-level rate limiting
        and circuit breakers handle concurrency safety.

        Returns summary dict: {total, processed, found, failed, skipped}
        """
        if not self._search_lock.acquire(blocking=False):
            logger.warning("Wanted search already running, skipping")
            return {"error": "search_already_running"}

        self._searching = True
        self._cancel_event.clear()
        start = time.time()

        try:
            settings = get_settings()
            max_items = settings.wanted_search_max_items_per_run

            from db.wanted import get_wanted_items

            result = get_wanted_items(page=1, per_page=max_items, status="wanted")
            items = result.get("data", [])

            # Filter: adaptive backoff (or fixed 1h fallback when disabled)
            eligible = []
            now = datetime.now(UTC)
            adaptive_enabled = getattr(settings, "wanted_adaptive_backoff_enabled", True)

            for item in items:
                if adaptive_enabled:
                    # Respect retry_after timestamp (exponential backoff)
                    retry_after_str = item.get("retry_after")
                    if retry_after_str:
                        try:
                            retry_at = datetime.fromisoformat(retry_after_str)
                            # Ensure both datetimes are comparable (add UTC if naive)
                            if retry_at.tzinfo is None:
                                retry_at = retry_at.replace(tzinfo=UTC)
                            if now < retry_at:
                                continue
                        except (ValueError, TypeError):
                            pass
                else:
                    # Fallback: fixed 1h cooldown when backoff disabled
                    last_str = item.get("last_search_at")
                    if last_str:
                        try:
                            last = datetime.fromisoformat(last_str)
                            if last.tzinfo is None:
                                last = last.replace(tzinfo=UTC)
                            if (now - last).total_seconds() < 3600:
                                continue
                        except (ValueError, TypeError):
                            pass

                if item["search_count"] < settings.wanted_max_search_attempts:
                    eligible.append(item)

            if not eligible:
                self._last_search_at = datetime.now(UTC).isoformat()
                return {"total": 0, "processed": 0, "found": 0, "failed": 0, "skipped": 0}

            from wanted_search import process_wanted_item

            total = len(eligible)
            processed = 0
            found = 0
            failed = 0
            skipped = 0

            # Parallel processing with bounded ThreadPoolExecutor
            max_workers = min(4, total)
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_item = {
                    executor.submit(process_wanted_item, item["id"]): item for item in eligible
                }

                for future in as_completed(future_to_item):
                    # Check cancel flag between completions
                    if self._cancel_event.is_set():
                        logger.info("Wanted search cancelled after %d/%d items", processed, total)
                        # Cancel remaining futures
                        for f in future_to_item:
                            f.cancel()
                        break

                    item = future_to_item[future]
                    try:
                        res = future.result()
                        processed += 1
                        if res.get("status") == "found":
                            found += 1
                        elif res.get("status") == "failed":
                            failed += 1
                        else:
                            skipped += 1
                    except Exception as e:
                        processed += 1
                        failed += 1
                        logger.warning("Search-all: error on item %d: %s", item["id"], e)

                    if socketio:
                        socketio.emit(
                            "wanted_search_progress",
                            {
                                "processed": processed,
                                "total": total,
                                "found": found,
                                "failed": failed,
                                "current_item": item.get("title", str(item["id"])),
                            },
                        )

            duration = round(time.time() - start, 1)
            self._last_search_at = datetime.now(UTC).isoformat()

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
                processed,
                total,
                found,
                failed,
                duration,
            )

            from events import emit_event

            emit_event("wanted_scan_complete", summary)

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

    # ─── Scheduler ──────────────────────────────────────────────────────────

    def start_scheduler(self, socketio=None, app=None):
        """Start the periodic scan and search schedulers."""
        self._socketio = socketio
        self._app = app
        settings = get_settings()

        # Scan scheduler
        scan_interval = settings.wanted_scan_interval_hours
        if scan_interval > 0:
            if settings.wanted_scan_on_startup:
                thread = threading.Thread(target=self._run_scan_with_context, daemon=True)
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
        """Schedule the next scan."""
        self._timer = threading.Timer(
            interval_hours * 3600,
            self._scheduled_scan,
            args=(interval_hours,),
        )
        self._timer.daemon = True
        self._timer.start()

    def _run_scan_with_context(self):
        """Run scan_all inside Flask app context (for background threads)."""
        if self._app is not None:
            with self._app.app_context():
                self.scan_all()
        else:
            self.scan_all()

    def _run_search_with_context(self, socketio=None):
        """Run search_all inside Flask app context (for background threads)."""
        if self._app is not None:
            with self._app.app_context():
                self.search_all(socketio)
        else:
            self.search_all(socketio)

    def _scheduled_scan(self, interval_hours):
        """Execute a scheduled scan and reschedule."""
        logger.info("Wanted scheduled scan starting")
        self._run_scan_with_context()
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
        self._run_search_with_context(self._socketio)
        self._schedule_next_search(interval_hours)
