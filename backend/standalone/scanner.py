"""Standalone directory scanner -- scans watched folders for media files.

Walks configured directories, parses filenames, resolves metadata,
creates standalone_series/standalone_movies entries, and populates
wanted_items for files missing target language subtitles.
"""

import logging
import os
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)


class StandaloneScanner:
    """Scans watched folders for video files, resolves metadata, and populates wanted_items.

    Groups episode files by series title (one metadata lookup per unique title),
    creates standalone_series/standalone_movies entries, and checks for missing
    target language subtitles using the default language profile.
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
                        folder.get("path", "unknown"), e,
                    )

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
                "Standalone scan complete: %d folders, %d series, %d movies, "
                "%d wanted (%.1fs)",
                folders_scanned, total_series, total_movies,
                total_wanted, duration,
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
        from standalone.parser import is_video_file, parse_media_file, group_files_by_series

        folder_path = folder["path"]
        if not os.path.isdir(folder_path):
            logger.warning("Watched folder does not exist: %s", folder_path)
            return (0, 0, 0)

        # Collect all video files
        video_files = []
        for root, _dirs, files in os.walk(folder_path):
            for filename in files:
                full_path = os.path.join(root, filename)
                if is_video_file(full_path):
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

    def _process_series_group(self, title: str, files: list[dict],
                              folder: dict) -> int:
        """Process a group of episode files belonging to one series.

        Resolves metadata once for the series, upserts standalone_series,
        then checks each episode for missing target language subtitles.

        Args:
            title: Normalized series title (lowercase).
            files: List of parsed file dicts (each with file_path key).
            folder: The watched folder dict.

        Returns:
            Number of wanted items added.
        """
        from db.standalone import upsert_standalone_series
        from db.wanted import upsert_wanted_item

        # Use the first file's original title for display
        display_title = files[0].get("title", title)
        is_anime = any(f.get("is_anime", False) for f in files)
        year = None
        for f in files:
            if f.get("year"):
                year = f["year"]
                break

        # Resolve metadata (one lookup per unique series)
        resolver = self._get_resolver()
        meta = resolver.resolve_series(display_title, year=year, is_anime=is_anime)

        # Determine series folder path (common parent)
        series_folder = self._find_common_parent(
            [f["file_path"] for f in files]
        )

        # Upsert standalone series
        series_id = upsert_standalone_series(
            title=meta.get("title", display_title),
            folder_path=series_folder,
            year=meta.get("year"),
            tmdb_id=meta.get("tmdb_id"),
            tvdb_id=meta.get("tvdb_id"),
            anilist_id=meta.get("anilist_id"),
            imdb_id=meta.get("imdb_id", ""),
            poster_url=meta.get("poster_url", ""),
            is_anime=meta.get("is_anime", is_anime),
            episode_count=len(files),
            season_count=meta.get("season_count") or 0,
            metadata_source=meta.get("metadata_source", "filename"),
        )

        # Check each episode for missing target subtitles
        wanted_added = 0
        target_languages = self._get_target_languages()

        for f in files:
            file_path = f["file_path"]
            season = f.get("season")
            episode = f.get("episode")

            season_episode = ""
            if season is not None and episode is not None:
                season_episode = f"S{season:02d}E{episode:02d}"
            elif episode is not None:
                season_episode = f"E{episode:02d}"

            for target_lang in target_languages:
                existing = self._check_existing_subtitle(file_path, target_lang)
                if existing == "ass":
                    continue  # Goal achieved

                ep_title = f"{meta.get('title', display_title)}"
                if season_episode:
                    ep_title = f"{ep_title} -- {season_episode}"

                existing_sub = existing or ""

                upsert_wanted_item(
                    item_type="episode",
                    file_path=file_path,
                    title=ep_title,
                    season_episode=season_episode,
                    existing_sub=existing_sub,
                    missing_languages=[target_lang],
                    target_language=target_lang,
                    instance_name="standalone",
                    standalone_series_id=series_id,
                )
                wanted_added += 1

        return wanted_added

    def _process_movie(self, parsed: dict, file_path: str,
                       folder: dict) -> int:
        """Process a single movie file.

        Resolves metadata, upserts standalone_movie, checks for missing
        target language subtitles.

        Args:
            parsed: Parsed file metadata dict.
            file_path: Absolute path to the movie file.
            folder: The watched folder dict.

        Returns:
            1 if a wanted item was added, 0 otherwise.
        """
        from db.standalone import upsert_standalone_movie
        from db.wanted import upsert_wanted_item

        title = parsed.get("title", "Unknown")
        year = parsed.get("year")

        # Resolve metadata
        resolver = self._get_resolver()
        meta = resolver.resolve_movie(title, year=year)

        # Upsert standalone movie
        movie_id = upsert_standalone_movie(
            title=meta.get("title", title),
            file_path=file_path,
            year=meta.get("year"),
            tmdb_id=meta.get("tmdb_id"),
            imdb_id=meta.get("imdb_id", ""),
            poster_url=meta.get("poster_url", ""),
            metadata_source=meta.get("metadata_source", "filename"),
        )

        # Check for missing target subtitles
        wanted_added = 0
        target_languages = self._get_target_languages()

        for target_lang in target_languages:
            existing = self._check_existing_subtitle(file_path, target_lang)
            if existing == "ass":
                continue

            existing_sub = existing or ""

            upsert_wanted_item(
                item_type="movie",
                file_path=file_path,
                title=meta.get("title", title),
                existing_sub=existing_sub,
                missing_languages=[target_lang],
                target_language=target_lang,
                instance_name="standalone",
                standalone_movie_id=movie_id,
            )
            wanted_added += 1

        return wanted_added

    def process_single_file(self, file_path: str) -> dict:
        """Process a single newly detected file.

        Parses the file, resolves metadata, creates/updates standalone
        entry, and creates wanted item if subtitles are missing.

        This is the callback target for the watcher's on_new_file.

        Args:
            file_path: Absolute path to the media file.

        Returns:
            Dict with type, title, wanted (bool).
        """
        from standalone.parser import parse_media_file

        try:
            parsed = parse_media_file(file_path)

            if parsed["type"] == "movie":
                wanted = self._process_movie(
                    parsed, file_path, {"path": os.path.dirname(file_path)}
                )
                return {
                    "type": "movie",
                    "title": parsed.get("title", "Unknown"),
                    "wanted": wanted > 0,
                }
            else:
                # For a single episode file, create a minimal series group
                from db.standalone import upsert_standalone_series
                from db.wanted import upsert_wanted_item

                title = parsed.get("title", "Unknown")
                is_anime = parsed.get("is_anime", False)
                year = parsed.get("year")

                resolver = self._get_resolver()
                meta = resolver.resolve_series(title, year=year, is_anime=is_anime)

                series_folder = os.path.dirname(file_path)
                series_id = upsert_standalone_series(
                    title=meta.get("title", title),
                    folder_path=series_folder,
                    year=meta.get("year"),
                    tmdb_id=meta.get("tmdb_id"),
                    tvdb_id=meta.get("tvdb_id"),
                    anilist_id=meta.get("anilist_id"),
                    imdb_id=meta.get("imdb_id", ""),
                    poster_url=meta.get("poster_url", ""),
                    is_anime=meta.get("is_anime", is_anime),
                    metadata_source=meta.get("metadata_source", "filename"),
                )

                # Check for missing subtitles
                wanted = False
                target_languages = self._get_target_languages()
                season = parsed.get("season")
                episode = parsed.get("episode")

                season_episode = ""
                if season is not None and episode is not None:
                    season_episode = f"S{season:02d}E{episode:02d}"
                elif episode is not None:
                    season_episode = f"E{episode:02d}"

                for target_lang in target_languages:
                    existing = self._check_existing_subtitle(file_path, target_lang)
                    if existing == "ass":
                        continue

                    ep_title = meta.get("title", title)
                    if season_episode:
                        ep_title = f"{ep_title} -- {season_episode}"

                    upsert_wanted_item(
                        item_type="episode",
                        file_path=file_path,
                        title=ep_title,
                        season_episode=season_episode,
                        existing_sub=existing or "",
                        missing_languages=[target_lang],
                        target_language=target_lang,
                        instance_name="standalone",
                        standalone_series_id=series_id,
                    )
                    wanted = True

                return {
                    "type": "episode",
                    "title": meta.get("title", title),
                    "wanted": wanted,
                }

        except Exception as e:
            logger.error("Error processing single file %s: %s", file_path, e)
            return {"type": "unknown", "title": "", "wanted": False, "error": str(e)}

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

    def _check_existing_subtitle(self, file_path: str,
                                 target_lang: str) -> Optional[str]:
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
            logger.debug(
                "Could not check existing subs for %s: %s", file_path, e
            )
            return None

    def _find_common_parent(self, paths: list[str]) -> str:
        """Find the common parent directory of a list of file paths.

        Args:
            paths: List of absolute file paths.

        Returns:
            The deepest common parent directory.
        """
        if not paths:
            return ""
        if len(paths) == 1:
            return os.path.dirname(paths[0])

        common = os.path.commonpath(paths)
        # If commonpath returns a file (all same file), use its parent
        if os.path.isfile(common):
            common = os.path.dirname(common)
        return common

    def _cleanup_stale_wanted(self) -> int:
        """Remove standalone wanted items whose files no longer exist on disk.

        Returns:
            Number of items removed.
        """
        try:
            from db import get_db, _db_lock

            db = get_db()
            with _db_lock:
                rows = db.execute(
                    "SELECT id, file_path FROM wanted_items "
                    "WHERE instance_name='standalone'"
                ).fetchall()

            to_remove = []
            for row in rows:
                if not os.path.exists(row[1]):
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
