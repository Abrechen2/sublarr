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

from services.scheduler.cancellation import abort_requested
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


# ---------------------------------------------------------------------------
# Module-level scanner singleton
# ---------------------------------------------------------------------------
#
# Multiple call paths (POST /scan, POST /scan/<id>, POST /series/<id>/scan,
# scheduled `standalone_scan` job) used to instantiate a fresh
# ``StandaloneScanner()`` each time. Because the per-instance ``_scan_lock``
# only protects against re-entry on the *same* object, parallel requests
# created independent scanners with independent locks and trampled each
# other at the upsert layer. The singleton below funnels every code path
# through the same instance so the lock actually serializes scans.

_scanner_singleton: "StandaloneScanner | None" = None
_scanner_singleton_lock = threading.Lock()


def get_scanner() -> "StandaloneScanner":
    """Return the process-wide ``StandaloneScanner`` instance, creating it lazily.

    Module-level singleton intentionally — see comment above. Never
    instantiate ``StandaloneScanner`` directly outside this module.
    """
    global _scanner_singleton
    if _scanner_singleton is None:
        with _scanner_singleton_lock:
            if _scanner_singleton is None:
                _scanner_singleton = StandaloneScanner()
    return _scanner_singleton


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
                # One watched folder is the unit: _scan_folder walks a whole
                # tree and cannot be interrupted part-way, so a stop takes
                # effect between folders and the counts below stay truthful
                # about what was actually scanned.
                if abort_requested():
                    logger.info(
                        "Standalone scan stopping as asked after %d folder(s)", folders_scanned
                    )
                    break
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

    def scan_series(self, series_id: int) -> dict:
        """Re-scan a single standalone series folder.

        Walks the series' ``folder_path`` (recursive), runs the parser, and
        re-creates wanted_items for any episodes missing target-language
        subtitles. Idempotent — uses the same upsert path as the full scan.

        Returns:
            Summary dict with keys: series_id, files_found, wanted_added, error.
        """
        try:
            from db.standalone import get_standalone_series
        except Exception as e:
            return {"error": f"db unavailable: {e}", "series_id": series_id}

        series = get_standalone_series(series_id)
        if not series:
            return {"error": "series_not_found", "series_id": series_id}

        folder_path = series.get("folder_path", "")
        if not folder_path or not os.path.isdir(folder_path):
            return {
                "error": "folder_missing",
                "series_id": series_id,
                "folder_path": folder_path,
            }

        synthetic_folder = {
            "path": folder_path,
            "label": series.get("title", ""),
            "media_type": "tv",
            "enabled": True,
        }
        try:
            s_count, m_count, w_count = self.scan_folder(synthetic_folder)
            return {
                "series_id": series_id,
                "series_found": s_count,
                "movies_found": m_count,
                "wanted_added": w_count,
            }
        except Exception as e:
            logger.error("scan_series(%d) failed: %s", series_id, e, exc_info=True)
            return {"error": str(e), "series_id": series_id}

    def _recover_session(self) -> None:
        """Roll back the shared session after a per-item processing error.

        Standalone scans share the request-scoped ``db.session``. A failure
        mid-item — e.g. a ``StaleDataError`` from a row deleted by a concurrent
        scan/cleanup, or any DB error during flush — leaves that session
        needing a rollback. Without recovering it here, the NEXT series/movie
        immediately fails with 'transaction has been rolled back due to a
        previous exception', which cascades so a single early error empties the
        whole scan (episode list stayed empty until a manual rescan).
        """
        try:
            from db import get_db

            get_db().rollback()
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("Session rollback after scan error failed: %s", exc)

    def scan_folder(self, folder) -> tuple:
        """Scan a single watched folder.

        Accepts either a folder dict (from DB) or a folder-path string.
        The string form is the public path used by ``launch_folder_scan``;
        it builds a minimal synthetic dict so internal helpers always see
        the same shape.

        Args:
            folder: Either a dict from DB (``path``, ``label``, ``media_type``,
                ``id``…) or an absolute folder-path string.

        Returns:
            Tuple of (series_count, movie_count, wanted_count).
        """
        if isinstance(folder, str):
            folder = {
                "path": folder,
                "label": "",
                "media_type": "auto",
                "enabled": True,
            }
        return self._scan_folder(folder)

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
        folder_id = folder.get("id")

        def _stamp() -> None:
            """Update last_scan_at if the folder is real (has an id)."""
            if not folder_id:
                return
            try:
                from db.standalone import update_watched_folder_last_scan

                update_watched_folder_last_scan(int(folder_id))
            except Exception as e:
                logger.debug("Failed to update last_scan_at for folder %s: %s", folder_id, e)

        if not os.path.isdir(folder_path):
            logger.warning("Watched folder does not exist: %s", folder_path)
            return (0, 0, 0)

        skip_extras = getattr(get_settings(), "standalone_skip_extras", True)

        # Collect all video files. ``followlinks=True`` is intentional —
        # homelab media trees frequently use symlinks to flatten library
        # layouts — but Python's os.walk does NOT detect cycles when
        # following links, so a kreis-symlink (``/media/x → /media/``)
        # would walk forever. We track every directory by its
        # ``(st_dev, st_ino)`` tuple and prune subdirectories we've
        # already entered. Short-circuits at first repeat so total
        # traversal stays linear.
        video_files = []
        seen_dirs: set[tuple[int, int]] = set()
        for root, dirs, files in os.walk(folder_path, followlinks=True):
            try:
                root_stat = os.stat(root)
            except OSError as e:
                logger.warning("Skipping unreachable directory %s: %s", root, e)
                dirs[:] = []
                continue
            root_key = (root_stat.st_dev, root_stat.st_ino)
            if root_key in seen_dirs:
                # Cycle detected — pruning prevents infinite descent.
                logger.warning(
                    "Symlink cycle detected at %s; pruning to avoid infinite walk",
                    root,
                )
                dirs[:] = []
                continue
            seen_dirs.add(root_key)

            # Filter children: drop any subdir whose inode we've already
            # visited so we never descend into a cycle (the os.walk above
            # would happily re-enter without this).
            pruned: list[str] = []
            for d in dirs:
                child = os.path.join(root, d)
                try:
                    cstat = os.stat(child)
                except OSError:
                    continue
                if (cstat.st_dev, cstat.st_ino) in seen_dirs:
                    logger.debug("Pruning already-visited subdir: %s", child)
                    continue
                pruned.append(d)
            dirs[:] = pruned

            for filename in files:
                full_path = os.path.join(root, filename)
                if is_video_file(full_path) and (not skip_extras or not _is_extra_file(full_path)):
                    video_files.append(full_path)

        if not video_files:
            logger.debug("No video files in %s", folder_path)
            _stamp()
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
                self._recover_session()

        # Process movies
        for file_path, parsed in movie_files:
            try:
                w = self._process_movie(parsed, file_path, folder)
                movie_count += 1
                wanted_count += w
            except Exception as e:
                logger.error("Error processing movie '%s': %s", file_path, e)
                self._recover_session()

        _stamp()
        return (series_count, movie_count, wanted_count)

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _get_target_languages(self) -> list[str]:
        """Get target languages from the default language profile.

        Falls back to the global target_language setting when the default
        profile has no target_languages configured. Logs a warning in that
        case so users can spot a misconfigured profile (the standalone
        scanner has no per-file profile binding — it always uses the
        default).

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
                logger.warning(
                    "Standalone: default profile %r has no target_languages — "
                    "falling back to settings.target_language. Configure the "
                    "default profile to silence this warning.",
                    profile.get("name", "?"),
                )
        except Exception:
            logger.debug("Standalone: failed to read default profile", exc_info=True)

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

    @staticmethod
    def _watched_roots_reachable() -> bool:
        """Probe every enabled watched folder before destructive cleanup.

        If ANY watched folder fails ``os.stat`` we treat the entire cleanup
        pass as unsafe and abort. This catches the NFS-disconnect /
        Unraid-share-reload class of failure where ``os.path.isdir`` /
        ``os.path.exists`` would return False for files that are merely
        temporarily unreachable, leading to mass-delete of correct rows.

        Returns:
            True if every enabled watched folder responds to ``os.stat``;
            False (and logs a warning) if any one of them is unreachable
            or no watched folders are configured. Empty-folder-list also
            returns False because cleanup against an empty list would
            wipe every standalone row in the DB.
        """
        try:
            from db.standalone import get_watched_folders

            folders = get_watched_folders(enabled_only=True)
        except Exception as e:
            logger.warning(
                "Standalone cleanup probe: could not list watched folders (%s); "
                "skipping to avoid mass-delete",
                e,
            )
            return False

        if not folders:
            logger.debug(
                "Standalone cleanup probe: no enabled watched folders — "
                "skipping cleanup (would otherwise wipe every standalone row)",
            )
            return False

        for f in folders:
            path = f.get("path", "")
            if not path:
                continue
            try:
                os.stat(path)
            except OSError as e:
                logger.warning(
                    "Standalone cleanup probe: watched folder %s unreachable (%s); "
                    "aborting cleanup pass to prevent mass-delete on transient "
                    "mount issue",
                    path,
                    e,
                )
                return False
        return True

    def _cleanup_stale_series(self) -> int:
        """Remove standalone_series entries whose folder no longer exists or is
        a season subfolder (artefact of earlier scans before series-root
        normalization was enforced).

        Cascades to ``wanted_items`` so that no orphan rows reference the
        deleted series. Aborts (returns 0) when any watched root is
        unreachable — see ``_watched_roots_reachable``.

        Returns:
            Number of series rows removed.
        """
        if not self._watched_roots_reachable():
            return 0

        try:
            from db.standalone import get_standalone_series
            from services.standalone_manager import delete_series_cascade

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
                # Cascade through services layer so wanted_items pointing to
                # this series get removed in the same transaction. Without
                # the cascade those rows would survive as orphans
                # (standalone_series_id → non-existent row), which the UI
                # rendered as "blank series" entries.
                delete_series_cascade(sid)

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

        Aborts (returns 0) when any watched root is unreachable — see
        ``_watched_roots_reachable``.

        Returns:
            Number of items removed.
        """
        if not self._watched_roots_reachable():
            return 0

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
