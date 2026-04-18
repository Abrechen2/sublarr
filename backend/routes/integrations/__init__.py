"""Integrations API blueprint — external integration endpoints.

Provides endpoints for:
- Bazarr database mapping report
- Plex/Kodi subtitle compatibility checking  (this module)
- Extended health checks for Sonarr, Radarr, Jellyfin, media servers  (health.py)
- Multi-format config export (Bazarr, Plex, Kodi, JSON) with ZIP bundling  (export.py)

All backend modules are lazy-imported to avoid circular imports.

`bazarr_mapping_report` stays in this __init__.py so test patches targeting
`routes.integrations.is_safe_path` continue to work unchanged.
"""

import logging
import os

from flask import Blueprint, jsonify, request

from security_utils import is_safe_path

logger = logging.getLogger(__name__)

bp = Blueprint("integrations", __name__, url_prefix="/api/v1/integrations")


# ---------------------------------------------------------------------------
# 1. Bazarr Mapping Report
# ---------------------------------------------------------------------------


@bp.route("/bazarr/mapping-report", methods=["POST"])
def bazarr_mapping_report():
    """Generate a detailed mapping report of a Bazarr database.

    Accepts JSON: {db_path: str}
    Validates db_path exists and is a file.
    """
    data = request.get_json(silent=True) or {}
    db_path = data.get("db_path", "")

    if not db_path:
        return jsonify({"error": "db_path is required"}), 400

    from config import get_settings

    _s = get_settings()
    _config_dir = getattr(_s, "config_dir", "/config")
    if not is_safe_path(db_path, _config_dir) and not is_safe_path(db_path, _s.media_path):
        return jsonify({"error": "db_path must be under /config or the configured media_path"}), 403

    if not os.path.isfile(db_path):
        return jsonify({"error": f"File not found: {db_path}"}), 400

    try:
        from bazarr_migrator import generate_mapping_report

        report = generate_mapping_report(db_path)
        return jsonify(report)
    except Exception as exc:
        logger.error("Bazarr mapping report failed: %s", exc)
        return jsonify({"error": f"Mapping report failed: {exc}"}), 500


# ---------------------------------------------------------------------------
# 2. Compatibility Check (Batch)
# ---------------------------------------------------------------------------


@bp.route("/compat-check", methods=["POST"])
def compat_check_batch():
    """Run batch compatibility check on subtitle files.

    Accepts JSON: {subtitle_paths: list, video_path: str, target: "plex"|"kodi"}
    """
    data = request.get_json(silent=True) or {}
    subtitle_paths = data.get("subtitle_paths", [])
    video_path = data.get("video_path", "")
    target = data.get("target", "plex")

    if not subtitle_paths:
        return jsonify({"error": "subtitle_paths is required (non-empty list)"}), 400

    if not video_path:
        return jsonify({"error": "video_path is required"}), 400

    if target not in ("plex", "kodi"):
        return jsonify({"error": f"target must be 'plex' or 'kodi', got '{target}'"}), 400

    try:
        from compat_checker import batch_check_compatibility

        result = batch_check_compatibility(subtitle_paths, video_path, target)
        return jsonify(result)
    except Exception as exc:
        logger.error("Batch compat check failed: %s", exc)
        return jsonify({"error": f"Compatibility check failed: {exc}"}), 500


# ---------------------------------------------------------------------------
# 3. Compatibility Check (Single)
# ---------------------------------------------------------------------------


@bp.route("/compat-check/single", methods=["POST"])
def compat_check_single():
    """Run compatibility check on a single subtitle file.

    Accepts JSON: {subtitle_path: str, video_path: str, target: "plex"|"kodi"}
    """
    data = request.get_json(silent=True) or {}
    subtitle_path = data.get("subtitle_path", "")
    video_path = data.get("video_path", "")
    target = data.get("target", "plex")

    if not subtitle_path:
        return jsonify({"error": "subtitle_path is required"}), 400

    if not video_path:
        return jsonify({"error": "video_path is required"}), 400

    if target not in ("plex", "kodi"):
        return jsonify({"error": f"target must be 'plex' or 'kodi', got '{target}'"}), 400

    try:
        if target == "plex":
            from compat_checker import check_plex_compatibility

            result = check_plex_compatibility(subtitle_path, video_path)
        else:
            from compat_checker import check_kodi_compatibility

            result = check_kodi_compatibility(subtitle_path, video_path)
        return jsonify(result)
    except Exception as exc:
        logger.error("Single compat check failed: %s", exc)
        return jsonify({"error": f"Compatibility check failed: {exc}"}), 500


# Register route submodules — must come after bp is defined.
from routes.integrations import (  # noqa: E402, F401
    export,
    health,
)
