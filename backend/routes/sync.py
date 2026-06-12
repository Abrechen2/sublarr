"""Manual subtitle synchronization endpoints."""

import logging
import os

from flask import Blueprint, jsonify, request

from auth import require_api_key
from config import get_settings
from security_utils import is_safe_path

logger = logging.getLogger(__name__)

bp = Blueprint("sync", __name__, url_prefix="/api/v1/sync")

try:
    from services.video_sync import SyncUnavailableError, sync_with_alass
except ImportError:
    SyncUnavailableError = None  # type: ignore[assignment,misc]
    sync_with_alass = None  # type: ignore[assignment]


@bp.route("/alass", methods=["POST"])
@require_api_key
def alass_sync():
    """Sync a subtitle file to a reference subtitle using alass.

    Body JSON:
        subtitle_path (str): absolute path to subtitle to sync (modified in-place)
        reference_path (str): absolute path to reference subtitle (read-only)

    Returns 200 on success, 400 on bad params, 403 on path traversal, 503 if alass unavailable,
    500 on error.
    """
    if sync_with_alass is None:
        return jsonify({"error": "alass sync unavailable — install alass"}), 503

    data = request.get_json(silent=True) or {}
    subtitle_path = data.get("subtitle_path", "").strip()
    reference_path = data.get("reference_path", "").strip()

    if not subtitle_path or not reference_path:
        return jsonify({"error": "subtitle_path and reference_path are required"}), 400

    settings = get_settings()
    media_path = getattr(settings, "media_path", "/media")

    for path in (subtitle_path, reference_path):
        if not is_safe_path(path, media_path):
            return jsonify({"error": "Access denied — path outside media directory"}), 403

    if not os.path.isfile(subtitle_path):
        return jsonify({"error": f"subtitle_path not found: {subtitle_path}"}), 404
    if not os.path.isfile(reference_path):
        return jsonify({"error": f"reference_path not found: {reference_path}"}), 404

    try:
        sync_result = sync_with_alass(subtitle_path, reference_path)
        logger.info("alass: synced %s using reference %s", subtitle_path, reference_path)
        return jsonify({"status": "ok", **sync_result}), 200
    except Exception as e:
        if SyncUnavailableError and isinstance(e, SyncUnavailableError):
            return jsonify({"error": "alass sync unavailable — install alass"}), 503
        logger.error("alass sync failed: %s", e, exc_info=True)
        return jsonify({"error": "Internal server error"}), 500
