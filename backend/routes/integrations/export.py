"""Config export routes — /export, /export/zip."""

import logging

from flask import Response, jsonify, request

from routes.integrations import bp

logger = logging.getLogger(__name__)


@bp.route("/export", methods=["POST"])
def export_config_endpoint():
    """Export Sublarr config in a specified format.

    Accepts JSON: {format: "bazarr"|"plex"|"kodi"|"json", include_secrets: bool}
    """
    data = request.get_json(silent=True) or {}
    export_format = data.get("format", "json")

    valid_formats = {"bazarr", "plex", "kodi", "json"}
    if export_format not in valid_formats:
        return jsonify(
            {
                "error": f"Invalid format '{export_format}'. Supported: {', '.join(sorted(valid_formats))}"
            }
        ), 400

    try:
        from export_manager import export_config

        # Secrets are never serialised to an HTTP response. A leaked API key
        # must not be escalatable into every integrated service credential via
        # this endpoint; secret export is a UI-only flow with a fresh password
        # proof. include_secrets is intentionally ignored here.
        result = export_config(export_format, include_secrets=False)
        return jsonify(result)
    except Exception as exc:
        logger.error("Config export failed: %s", exc)
        return jsonify({"error": "Export failed"}), 500


@bp.route("/export/zip", methods=["POST"])
def export_zip_endpoint():
    """Export Sublarr config as a ZIP archive with multiple formats.

    Accepts JSON: {formats: list, include_secrets: bool}
    Returns ZIP file as application/zip download.
    """
    data = request.get_json(silent=True) or {}
    formats = data.get("formats", [])

    if not formats:
        return jsonify({"error": "formats is required (non-empty list)"}), 400

    valid_formats = {"bazarr", "plex", "kodi", "json"}
    invalid = set(formats) - valid_formats
    if invalid:
        return jsonify(
            {
                "error": f"Invalid format(s): {', '.join(sorted(invalid))}. Supported: {', '.join(sorted(valid_formats))}"
            }
        ), 400

    try:
        from export_manager import export_to_zip

        # Secrets never leave via HTTP (see export_config_endpoint).
        zip_bytes = export_to_zip(formats, include_secrets=False)
        return Response(
            zip_bytes,
            mimetype="application/zip",
            headers={
                "Content-Disposition": "attachment; filename=sublarr_export.zip",
            },
        )
    except Exception as exc:
        logger.error("ZIP export failed: %s", exc)
        return jsonify({"error": "ZIP export failed"}), 500
