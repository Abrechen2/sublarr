"""Series ZIP export + single-subtitle download endpoints."""

from __future__ import annotations

import io
import logging
import os
import zipfile

from flask import jsonify, request, send_file

from config import get_settings, map_path
from routes.subtitles import bp
from security_utils import is_safe_path

logger = logging.getLogger(__name__)

_SUBTITLE_DOWNLOAD_EXTS = {".ass", ".srt", ".vtt", ".ssa", ".sub"}
_ZIP_SIZE_LIMIT = 50 * 1024 * 1024  # 50 MB


def _get_series_path(series_id: int) -> str | None:
    """Resolve series filesystem path via Sonarr or standalone DB, applying path mapping."""
    from sonarr_client import get_sonarr_client

    try:
        client = get_sonarr_client()
        series = client.get_series_by_id(series_id)
        if series:
            raw_path = series.get("path", "")
            return map_path(raw_path) if raw_path else None
    except Exception as exc:
        logger.warning("Failed to resolve series path via Sonarr for id=%s: %s", series_id, exc)

    # Fallback: standalone series
    try:
        from db.standalone import get_standalone_series

        standalone = get_standalone_series(series_id)
        if standalone:
            raw_path = standalone.get("folder_path", "")
            return map_path(raw_path) if raw_path else None
    except Exception as exc:
        logger.warning("Failed to resolve standalone series path for id=%s: %s", series_id, exc)

    return None


def _scan_series_subtitles(series_path: str, warnings: list) -> list[dict]:
    """Return subtitle file dicts within series_path."""
    from export_manager import _scan_subtitle_files

    return _scan_subtitle_files(series_path, warnings)


@bp.route("/series/<int:series_id>/subtitles/export", methods=["GET"])
def export_series_subtitles(series_id: int):
    """Export all subtitle sidecar files for a series as a ZIP download.

    Query params:
        lang: optional language code filter (e.g. 'de' keeps only *.de.* files)
    """
    settings = get_settings()
    lang_filter = request.args.get("lang", "").strip().lower()
    media_path = getattr(settings, "media_path", "/media")

    series_path = _get_series_path(series_id)
    if not series_path:
        return jsonify({"error": "Series not found"}), 404

    if not is_safe_path(series_path, media_path):
        return jsonify({"error": "Access denied"}), 403

    warnings: list = []
    subtitle_files = _scan_series_subtitles(series_path, warnings)

    if lang_filter:
        subtitle_files = [
            s for s in subtitle_files if f".{lang_filter}." in os.path.basename(s["path"]).lower()
        ]

    buf = io.BytesIO()
    total_bytes = 0

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for sub in subtitle_files:
            sub_path = sub["path"]
            if not os.path.isfile(sub_path):
                continue
            total_bytes += os.path.getsize(sub_path)
            if total_bytes > _ZIP_SIZE_LIMIT:
                return jsonify({"error": "Export too large (50 MB limit)"}), 413
            rel_path = os.path.relpath(sub_path, series_path)
            zf.write(sub_path, rel_path)

    buf.seek(0)
    series_name = os.path.basename(series_path.rstrip("/\\")) or f"series-{series_id}"
    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{series_name}-subtitles.zip",
    )


@bp.route("/subtitles/download", methods=["GET"])
def download_subtitle():
    """Serve a single subtitle sidecar file as a browser download.

    Query params:
        path: absolute path to the subtitle file (must be within media_path)
    """
    path = request.args.get("path", "").strip()
    if not path:
        return jsonify({"error": "path parameter required"}), 400

    settings = get_settings()
    media_path = getattr(settings, "media_path", "/media")
    if not is_safe_path(path, media_path):
        return jsonify({"error": "Access denied"}), 403

    ext = os.path.splitext(path)[1].lower()
    if ext not in _SUBTITLE_DOWNLOAD_EXTS:
        return jsonify({"error": "Access denied"}), 403

    if not os.path.isfile(path):
        return jsonify({"error": "File not found"}), 404

    return send_file(path, as_attachment=True, download_name=os.path.basename(path))
