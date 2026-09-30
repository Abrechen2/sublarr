"""Subtitle-sidecar + trash helpers used across the subtitles package.

These helpers are also public: several other modules (routes.tracks,
routes.video_sync, routes.subtitle_processor, routes.remux, routes.trash,
cleanup_scheduler) import `scan_subtitle_sidecars`, `_auto_purge_old_trash`,
`_get_trash_root`, or `_read_manifest` from `routes.subtitles`.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import UTC, datetime

from services.sidecar_scan import scan_subtitle_sidecars  # noqa: F401 — re-export
from services.sidecar_trash import (
    derive_language,
    derive_series_name,
    get_batch_dir,
    get_trash_root,
    trash_sidecar,
    write_manifest,
)
from subtitle_filename import SUBTITLE_EXTS

logger = logging.getLogger(__name__)

# Backwards-compat alias — older code in this module imported the local set
_SUBTITLE_EXTS = SUBTITLE_EXTS

# scan_subtitle_sidecars moved to services.sidecar_scan (layering: services must
# not import routes). Re-exported here so the many existing importers
# (routes.tracks, routes.video_sync, cleanup_scheduler, tests, …) keep working.


# ─── Trash helpers ─────────────────────────────────────────────────────────────


def _get_trash_root(media_path: str) -> str:
    """Compat shim — implementation moved to
    :func:`services.sidecar_trash.get_trash_root`."""
    return get_trash_root(media_path)


def _get_batch_dir(media_path: str, batch_id: str) -> str:
    """Compat shim — implementation moved to
    :func:`services.sidecar_trash.get_batch_dir`."""
    return get_batch_dir(media_path, batch_id)


def _derive_series_name(path: str) -> str:
    """Compat shim — implementation moved to
    :func:`services.sidecar_trash.derive_series_name`."""
    return derive_series_name(path)


def _derive_language(files: list[dict]) -> str:
    """Compat shim — implementation moved to
    :func:`services.sidecar_trash.derive_language`."""
    return derive_language(files)


def _write_manifest(
    batch_dir: str,
    batch_id: str,
    files: list[dict],
    series_name: str = "",
    language: str = "",
) -> None:
    """Compat shim — implementation moved to
    :func:`services.sidecar_trash.write_manifest`."""
    write_manifest(batch_dir, batch_id, files, series_name, language)


def _read_manifest(batch_dir: str) -> dict | None:
    manifest_path = os.path.join(batch_dir, "manifest.json")
    try:
        with open(manifest_path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def _auto_purge_old_trash(media_path: str, retention_days: int) -> int:
    """Permanently remove trash batches older than retention_days. 0 = keep forever."""
    if retention_days <= 0:
        return 0
    trash_root = _get_trash_root(media_path)
    if not os.path.isdir(trash_root):
        return 0

    cutoff = datetime.now(UTC).timestamp() - retention_days * 86400
    purged = 0
    for entry in os.scandir(trash_root):
        if not entry.is_dir():
            continue
        manifest = _read_manifest(entry.path)
        if manifest is None:
            continue
        created_at_str = manifest.get("created_at", "")
        try:
            created_ts = datetime.fromisoformat(created_at_str).timestamp()
        except (ValueError, TypeError):
            continue
        if created_ts < cutoff:
            try:
                shutil.rmtree(entry.path)
                purged += 1
                logger.info(
                    "auto-purge: removed trash batch %s (age > %dd)",
                    manifest["batch_id"],
                    retention_days,
                )
            except OSError as exc:
                logger.warning("auto-purge: could not remove %s: %s", entry.path, exc)
    return purged


def _trash_sidecar(path: str, media_path: str, batch_dir: str) -> tuple[str, str | None]:
    """Compat shim — implementation moved to
    :func:`services.sidecar_trash.trash_sidecar`.

    Returns (trashed_path_or_original, error_or_None).
    """
    return trash_sidecar(path, media_path, batch_dir)
