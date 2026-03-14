"""NFO export API endpoints.

POST /api/v1/subtitles/export-nfo
    Trigger NFO sidecar export for a single subtitle file.

POST /api/v1/series/<series_id>/subtitles/export-nfo
    Trigger NFO sidecar export for all subtitles belonging to a series.
"""

import logging
import os

from flask import Blueprint, abort, jsonify, request

from nfo_export import write_nfo
from security_utils import is_safe_path

bp = Blueprint("nfo", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers — thin wrappers so tests can monkeypatch them cleanly
# ---------------------------------------------------------------------------


def _get_series_path_for_nfo(series_id: int) -> str | None:
    """Return the local filesystem path for a series, or None if not found."""
    try:
        from sonarr_client import get_sonarr_client

        client = get_sonarr_client()
        series = client.get_series_by_id(series_id)
        if not series:
            return None
        raw_path = series.get("path", "")
        if not raw_path:
            return None
        from path_mapper import map_path

        return map_path(raw_path)
    except Exception as exc:
        logger.warning("NFO export: could not resolve series path for id=%s: %s", series_id, exc)
        return None


def _get_db_engine():
    """Return the SQLAlchemy db object (monkeypatch-friendly)."""
    from extensions import db

    return db


# ---------------------------------------------------------------------------
# Single subtitle export
# ---------------------------------------------------------------------------


@bp.route("/subtitles/export-nfo", methods=["POST"])
def export_subtitle_nfo():
    """Write an NFO sidecar for a single subtitle file.

    Query parameters:
        path (str, required): Absolute path to the subtitle file.

    Returns:
        200 {"status": "ok", "nfo_path": "..."} on success.
        400 if path is missing.
        403 if path is outside the configured media_path.
        404 if the subtitle file does not exist on disk.
    """
    path = request.args.get("path", "").strip()
    if not path:
        return jsonify({"error": "path parameter is required"}), 400

    from config import get_settings

    settings = get_settings()
    media_path = getattr(settings, "media_path", "/media")

    if not is_safe_path(path, media_path):
        abort(403)

    if not os.path.exists(path):
        return jsonify({"error": "Subtitle file not found"}), 404

    write_nfo(path, {})
    nfo_path = path + ".nfo"
    if not os.path.exists(nfo_path):
        return jsonify({"error": "NFO write failed"}), 500
    return jsonify({"status": "ok", "nfo_path": nfo_path}), 200


# ---------------------------------------------------------------------------
# Series-wide export
# ---------------------------------------------------------------------------


@bp.route("/series/<int:series_id>/subtitles/export-nfo", methods=["POST"])
def export_series_nfo(series_id: int):
    """Write NFO sidecars for all subtitle files in a series.

    Resolves the series filesystem path via Sonarr, then queries
    subtitle_downloads for all matching file_path entries.

    Returns:
        200 {"status": "ok", "exported": N, "skipped": M} on success.
        404 if the series cannot be found.
        500 on DB errors.
    """
    series_path = _get_series_path_for_nfo(series_id)
    if not series_path:
        return jsonify({"error": "Series not found"}), 404

    from config import get_settings

    settings = get_settings()
    media_path = getattr(settings, "media_path", "/media")

    if not is_safe_path(series_path, media_path):
        return jsonify({"error": "Access denied"}), 403

    try:
        db = _get_db_engine()
        prefix = series_path.rstrip("/\\") + "/"
        with db.engine.connect() as conn:
            from sqlalchemy import text as _text

            rows = conn.execute(
                _text(
                    "SELECT DISTINCT file_path FROM subtitle_downloads"
                    " WHERE file_path LIKE :pat"
                ),
                {"pat": prefix + "%"},
            ).fetchall()
    except Exception as exc:
        logger.error("NFO export: DB error for series %s: %s", series_id, exc)
        return jsonify({"error": "Database error"}), 500

    exported = 0
    skipped = 0
    for (fp,) in rows:
        if not is_safe_path(fp, media_path):
            skipped += 1
            logger.debug("NFO export: skipping unsafe path %s", fp)
            continue
        if not os.path.exists(fp):
            skipped += 1
            logger.debug("NFO export: skipping missing file %s", fp)
            continue
        write_nfo(fp, {})
        exported += 1

    return jsonify({"status": "ok", "exported": exported, "skipped": skipped}), 200
