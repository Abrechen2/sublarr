"""Standalone directory scanner -- scans watched folders for media files.

Walks configured directories, parses filenames, resolves metadata,
creates standalone_series/standalone_movies entries, and populates
wanted_items for files missing target language subtitles.
"""

import logging
import os
import re
import threading
import time

from sqlalchemy import text

from standalone.scanner_process import _StandaloneProcessMixin  # noqa: F401 — re-exported

logger = logging.getLogger(__name__)

# Filename stems and suffixes that mark non-episode extras (Jellyfin/Kodi convention).
# Files matching these are excluded from subtitle discovery.
_EXTRA_STEMS = frozenset({"tvshow", "movie", "trailer", "sample"})
_EXTRA_SUFFIXES = (
    "-trailer",
    "-featurette",
    "-behindthescenes",
    "-deleted",
    "-interview",
    "-scene",
    "-short",
    "-sample",
    "-theme",
)


def _is_extra_file(path: str) -> bool:
    """Return True if *path* is a media extra (trailer, featurette, …) that should
    be excluded from subtitle discovery."""
    stem = os.path.splitext(os.path.basename(path))[0].lower()
    return stem in _EXTRA_STEMS or any(stem.endswith(s) for s in _EXTRA_SUFFIXES)


class StandaloneScanner(_StandaloneProcessMixin):
    """Scans watched folders for video files, resolves metadata, and populates wanted_items.

    Groups episode files by series title (one metadata lookup per unique title),
    creates standalone_series/standalone_movies entries, and checks for missing
    target language subtitles using the default language profile.

    Per-item processing (``_process_series_group`` / ``_process_movie`` /
    ``process_single_file``) lives in the sibling ``scanner_process.py``
    module as ``_StandaloneProcessMixin`` — composed via multiple
    inheritance to keep this file focused on discovery + cleanup.
    """

    def __init__(self, metadata_resolver=None):
        """Initialize the scanner.

        Args:
            metadata_resolver: Optional MetadataResolver instance.
                Created lazily from config if None.
        """
        self._resolver = metadata_resolver
        self._scan_lock = threading.Lock()
        self._scanning = False

    @property
    def is_scanning(self) -> bool:
        """Whether a scan is currently in progress."""
        return self._scanning

    def _get_resolver(self):
        """Get or create the MetadataResolver from config settings.

        Returns:
            MetadataResolver instance (may have limited functionality if
            API keys are not configured).
        """
        if self._resolver is None:
            try:
                from config import get_settings
                from metadata import MetadataResolver

                settings = get_settings()
                self._resolver = MetadataResolver(
                    tmdb_key=getattr(settings, "tmdb_api_key", ""),
                    tvdb_key=getattr(settings, "tvdb_api_key", ""),
                    tvdb_pin=getattr(settings, "tvdb_pin", ""),
                )
            except Exception as e:
                logger.error("Failed to create MetadataResolver: %s", e)
                # Return a minimal resolver that only does filename fallback
                from metadata import MetadataResolver

                self._resolver = MetadataResolver()
        return self._resolver

    def scan_all_folders(self) -> dict:
        """Scan all enabled watched folders for media files.

        Non-blocking: skips if a scan is already in progress.

        Returns:
            Summary dict with keys: folders_scanned, series_found,
            movies_found, wanted_added, duration_seconds.
            Returns {"error": "scan_already_running"} if skipped.
        """
        if not self._scan_lock.acquire(blocking=False):
            logger.warning("Standalone scan already running, skipping")
            return {"error": "scan_already_running"}

        self._scanning = True
        start = time.time()
        total_series = 0
        total_movies = 0
        total_wanted = 0
        folders_scanned = 0

        try:
            from db.standalone import get_watched_folders

            folders = get_watched_folders(enabled_only=True)
            if not folders:
                logger.info("No enabled watched folders configured")
                return {
                    "folders_scanned": 0,
                    "series_found": 0,
                    "movies_found": 0,
                    "wanted_added": 0,
                    "duration_seconds": 0,
                }

            for folder in folders:
                try:
                    s, m, w = self._scan_folder(folder)
                    total_series += s
                    total_movies += m
                    total_wanted += w
                    folders_scanned += 1
                except Exception as e:
                    logger.error(
                        "Error scanning folder %s: %s",
                        folder.get("path", "unknown"),
                        e,
                    )

            # Cleanup: remove stale series entries (season subfolders / missing dirs)
            self._cleanup_stale_series()
            # Cleanup: remove wanted items whose files no longer exist
            self._cleanup_stale_wanted()

            duration = round(time.time() - start, 1)
            summary = {
                "folders_scanned": folders_scanned,
                "series_found": total_series,
                "movies_found": total_movies,
                "wanted_added": total_wanted,
                "duration_seconds": duration,
            }

            logger.info(
                "Standalone scan complete: %d folders, %d series, %d movies, %d wanted (%.1fs)",
                folders_scanned,
                total_series,
                total_movies,
                total_wanted,
                duration,
            )
            return summary

        except Exception as e:
            logger.exception("Standalone scan failed: %s", e)
            return {"error": str(e)}
        finally:
            self._scanning = False
            self._scan_lock.release()

    def _scan_folder(self, folder: dict) -> tuple:
        """Scan a single watched folder.

        Args:
            folder: Dict from DB with path, label, media_type, etc.

        Returns:
            Tuple of (series_count, movie_count, wanted_count).
        """
        from config import get_settings
        from standalone.parser import group_files_by_series, is_video_file, parse_media_file

        folder_path = folder["path"]
        if not os.path.isdir(folder_path):
            logger.warning("Watched folder does not exist: %s", folder_path)
            return (0, 0, 0)

        skip_extras = getattr(get_settings(), "standalone_skip_extras", True)

        # Collect all video files
        video_files = []
        for root, _dirs, files in os.walk(folder_path, followlinks=True):
            for filename in files:
                full_path = os.path.join(root, filename)
                if is_video_file(full_path) and (not skip_extras or not _is_extra_file(full_path)):
                    video_files.append(full_path)

        if not video_files:
            logger.debug("No video files in %s", folder_path)
            return (0, 0, 0)

        logger.info("Found %d video files in %s", len(video_files), folder_path)

        series_count = 0
        movie_count = 0
        wanted_count = 0

        # Group episode files by series title
        series_groups = group_files_by_series(video_files)

        # Collect movie files (not grouped into series)
        movie_files = []
        grouped_paths = set()
        for files_list in series_groups.values():
            for f in files_list:
                grouped_paths.add(f["file_path"])

        for vf in video_files:
            if vf not in grouped_paths:
                try:
                    parsed = parse_media_file(vf)
                    if parsed["type"] == "movie":
                        movie_files.append((vf, parsed))
                except Exception as e:
                    logger.warning("Failed to parse %s: %s", vf, e)

        # Process series groups
        for title, files in series_groups.items():
            try:
                w = self._process_series_group(title, files, folder)
                series_count += 1
                wanted_count += w
            except Exception as e:
                logger.error("Error processing series '%s': %s", title, e)

        # Process movies
        for file_path, parsed in movie_files:
            try:
                w = self._process_movie(parsed, file_path, folder)
                movie_count += 1
                wanted_count += w
            except Exception as e:
                logger.error("Error processing movie '%s': %s", file_path, e)

        return (series_count, movie_count, wanted_count)

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _get_target_languages(self) -> list[str]:
        """Get target languages from the default language profile.

        Falls back to the global target_language setting.

        Returns:
            List of target language codes.
        """
        try:
            from db.profiles import get_default_profile

            profile = get_default_profile()
            if profile:
                langs = profile.get("target_languages", [])
                if langs:
                    return langs
        except Exception:
            pass

        # Fallback to global config
        try:
            from config import get_settings

            settings = get_settings()
            return [settings.target_language]
        except Exception:
            return ["de"]  # Ultimate fallback

    def _check_existing_subtitle(self, file_path: str, target_lang: str) -> str | None:
        """Check if a target language subtitle already exists for a file.

        Args:
            file_path: Path to the video file.
            target_lang: Target language code.

        Returns:
            "ass" if ASS found, "srt" if SRT found, None if nothing found.
        """
        try:
            from translator import detect_existing_target_for_lang

            return detect_existing_target_for_lang(file_path, target_lang)
        except Exception as e:
            logger.debug("Could not check existing subs for %s: %s", file_path, e)
            return None

    # Matches typical season subfolder names: Season 1, Staffel 2, Saison 3, S01, etc.
    _SEASON_FOLDER_RE = re.compile(
        r"^(season|staffel|saison|serie|stagione|temporada|s\d+)\b",
        re.IGNORECASE,
    )

    def _find_common_parent(self, paths: list[str]) -> str:
        """Find the common parent directory of a list of file paths.

        Always returns the series root — never a season subfolder.  When all
        files live under a single season directory (e.g. Season 1/), the parent
        of that directory is returned so that subsequent scans covering more
        seasons don't create duplicate standalone_series entries.

        Args:
            paths: List of absolute file paths.

        Returns:
            The deepest common parent directory, normalized to series root.
        """
        if not paths:
            return ""
        if len(paths) == 1:
            common = os.path.dirname(paths[0])
        else:
            common = os.path.commonpath(paths)
            if os.path.isfile(common):
                common = os.path.dirname(common)

        # If the result is itself a season subfolder, go up one level so that
        # the key stored in standalone_series always points to the series root.
        basename = os.path.basename(common)
        if self._SEASON_FOLDER_RE.match(basename):
            common = os.path.dirname(common)

        return common

    def _cleanup_stale_series(self) -> int:
        """Remove standalone_series entries whose folder no longer exists or is
        a season subfolder (artefact of earlier scans before series-root
        normalization was enforced).

        Returns:
            Number of series rows removed.
        """
        try:
            from db.standalone import delete_standalone_series, get_standalone_series

            all_series = get_standalone_series()
            if not all_series:
                return 0

            to_remove = []
            for s in all_series:
                folder = s.get("folder_path", "")
                basename = os.path.basename(folder)
                if not os.path.isdir(folder) or self._SEASON_FOLDER_RE.match(basename):
                    to_remove.append(s["id"])

            for sid in to_remove:
                delete_standalone_series(sid)

            if to_remove:
                logger.info(
                    "Standalone cleanup: removed %d stale/season-subfolder series entries",
                    len(to_remove),
                )

            return len(to_remove)

        except Exception as e:
            logger.error("Standalone series cleanup failed: %s", e)
            return 0

    def _cleanup_stale_wanted(self) -> int:
        """Remove standalone wanted items whose files no longer exist on disk.

        Returns:
            Number of items removed.
        """
        try:
            from config import get_settings
            from db import get_db

            skip_extras = getattr(get_settings(), "standalone_skip_extras", True)
            db = get_db()
            rows = db.execute(
                text("SELECT id, file_path FROM wanted_items WHERE instance_name='standalone'")
            ).fetchall()

            to_remove = []
            for row in rows:
                if not os.path.exists(row[1]) or (skip_extras and _is_extra_file(row[1])):
                    to_remove.append(row[0])

            if to_remove:
                from db.wanted import delete_wanted_items_by_ids

                delete_wanted_items_by_ids(to_remove)
                logger.info(
                    "Standalone cleanup: removed %d stale wanted items",
                    len(to_remove),
                )

            return len(to_remove)

        except Exception as e:
            logger.error("Standalone cleanup failed: %s", e)
            return 0
