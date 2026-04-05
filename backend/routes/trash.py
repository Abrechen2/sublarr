"""Unified trash overview endpoint.

GET /api/v1/trash
    Returns both sidecar batches (soft-deleted subtitle files) and MKV backups
    (remux backups) in a single response with retention config and totals.

Response shape:
{
  "sidecar_batches": [...],   # from /library/trash
  "mkv_backups": [...],       # from /remux/backups
  "total_size_bytes": int,
  "retention": {
    "subtitle_trash_days": int,
    "mkv_backup_days": int,
  }
}
"""

import logging

from flask import Blueprint, jsonify

from config import get_settings

bp = Blueprint("trash", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)


@bp.route("/trash", methods=["GET"])
def get_trash_overview():
    """Return sidecar batches + MKV backups with retention config and totals."""
    settings = get_settings()
    subtitle_days = getattr(settings, "subtitle_trash_retention_days", 30)
    mkv_days = getattr(settings, "remux_backup_retention_days", 7)
    media_path = getattr(settings, "media_path", "/media")

    # ── Sidecar batches ────────────────────────────────────────────────────────
    sidecar_batches = _get_sidecar_batches(media_path, subtitle_days)

    # ── MKV backups ────────────────────────────────────────────────────────────
    mkv_backups = _get_mkv_backups(mkv_days)

    total_sidecar = sum(b.get("size_bytes", 0) for b in sidecar_batches)
    total_mkv = sum(b.get("size_bytes", 0) for b in mkv_backups)

    return jsonify(
        {
            "sidecar_batches": sidecar_batches,
            "mkv_backups": mkv_backups,
            "total_size_bytes": total_sidecar + total_mkv,
            "retention": {
                "subtitle_trash_days": subtitle_days,
                "mkv_backup_days": mkv_days,
            },
        }
    ), 200


# ── Private helpers ────────────────────────────────────────────────────────────


def _get_sidecar_batches(media_path: str, retention_days: int) -> list[dict]:
    """Collect sidecar trash batches (mirrors list_trash logic without auto-purge)."""
    import os
    from datetime import datetime, timedelta

    try:
        from routes.subtitles import _get_trash_root, _read_manifest
    except ImportError:
        logger.warning("Could not import sidecar trash helpers")
        return []

    trash_root = _get_trash_root(media_path)
    if not os.path.isdir(trash_root):
        return []

    batches = []
    for entry in os.scandir(trash_root):
        if not entry.is_dir():
            continue
        manifest = _read_manifest(entry.path)
        if manifest is None:
            continue

        files = manifest.get("files", [])
        total_bytes = 0
        for f in files:
            try:
                total_bytes += os.path.getsize(f["trashed"])
            except OSError:
                pass

        created_at = manifest.get("created_at")
        expires_at = None
        if created_at and retention_days > 0:
            try:
                expires_dt = datetime.fromisoformat(created_at) + timedelta(days=retention_days)
                expires_at = expires_dt.isoformat()
            except (ValueError, TypeError):
                pass

        batches.append(
            {
                "batch_id": manifest["batch_id"],
                "created_at": created_at,
                "expires_at": expires_at,
                "file_count": len(files),
                "size_bytes": total_bytes,
                "series_name": manifest.get("series_name", ""),
                "language": manifest.get("language", ""),
                "files": [f.get("original", "") for f in files],
            }
        )

    batches.sort(key=lambda b: b.get("created_at") or "", reverse=True)
    return batches


def _get_mkv_backups(retention_days: int) -> list[dict]:
    """Collect MKV backup entries from remux trash directories."""
    try:
        from remux.backup_cleanup import list_backups
        from routes.remux import _trash_paths
    except ImportError:
        logger.warning("Could not import MKV backup helpers")
        return []

    try:
        return list_backups(_trash_paths(), retention_days=retention_days)
    except Exception as exc:
        logger.warning("Failed to list MKV backups: %s", exc)
        return []
