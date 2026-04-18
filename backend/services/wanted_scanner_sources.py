"""Per-source scan mixin for WantedScanner.

Extracted from services/wanted_scanner_core.py. Owns the three
by-source scan entry points (Sonarr instances, Radarr instances,
standalone folders) plus the shared auto-extract trigger and the
incremental ``since`` filter semantics.

Every method uses ``self._progress``, ``self._socketio`` and the core
repositories/clients via module-level imports — nothing Flask-specific,
so the mixin composes cleanly into :class:`WantedScanner`.
"""

import logging
import time

from config import get_settings
from db.wanted import batch_upsert_context
from services.wanted_item_scanner import scan_radarr_movie, scan_sonarr_series

logger = logging.getLogger(__name__)


class _WantedScanSourcesMixin:
    """Sonarr/Radarr/standalone scan loops composed into WantedScanner."""

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
