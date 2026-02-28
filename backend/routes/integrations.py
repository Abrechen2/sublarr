"""Integrations API blueprint -- Phase 16 external integration endpoints.

Provides endpoints for:
- Bazarr database mapping report
- Plex/Kodi subtitle compatibility checking
- Extended health checks for Sonarr, Radarr, Jellyfin, and media servers
- Multi-format config export (Bazarr, Plex, Kodi, JSON) with ZIP bundling

All backend modules are lazy-imported to avoid circular imports.
"""

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from flask import Blueprint, Response, jsonify, request

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


# ---------------------------------------------------------------------------
# 4. Extended Health: Sonarr
# ---------------------------------------------------------------------------


@bp.route("/health/sonarr", methods=["GET"])
def health_sonarr():
    """Extended health check for all configured Sonarr instances."""
    try:
        from config import get_sonarr_instances
        from sonarr_client import SonarrClient

        instances_config = get_sonarr_instances()
        if not instances_config:
            return jsonify({"instances": [], "message": "No Sonarr instances configured"})

        results = []
        for inst in instances_config:
            name = inst.get("name", "Unnamed")
            try:
                client = SonarrClient(
                    url=inst.get("url", ""),
                    api_key=inst.get("api_key", ""),
                )
                health = client.extended_health_check()
                results.append({"name": name, **health})
            except Exception as exc:
                results.append(
                    {
                        "name": name,
                        "connection": {"healthy": False, "message": str(exc)},
                    }
                )

        return jsonify({"instances": results})
    except Exception as exc:
        logger.error("Sonarr health check failed: %s", exc)
        return jsonify({"error": f"Sonarr health check failed: {exc}"}), 500


# ---------------------------------------------------------------------------
# 5. Extended Health: Radarr
# ---------------------------------------------------------------------------


@bp.route("/health/radarr", methods=["GET"])
def health_radarr():
    """Extended health check for all configured Radarr instances."""
    try:
        from config import get_radarr_instances
        from radarr_client import RadarrClient

        instances_config = get_radarr_instances()
        if not instances_config:
            return jsonify({"instances": [], "message": "No Radarr instances configured"})

        results = []
        for inst in instances_config:
            name = inst.get("name", "Unnamed")
            try:
                client = RadarrClient(
                    url=inst.get("url", ""),
                    api_key=inst.get("api_key", ""),
                )
                health = client.extended_health_check()
                results.append({"name": name, **health})
            except Exception as exc:
                results.append(
                    {
                        "name": name,
                        "connection": {"healthy": False, "message": str(exc)},
                    }
                )

        return jsonify({"instances": results})
    except Exception as exc:
        logger.error("Radarr health check failed: %s", exc)
        return jsonify({"error": f"Radarr health check failed: {exc}"}), 500


# ---------------------------------------------------------------------------
# 6. Extended Health: Jellyfin
# ---------------------------------------------------------------------------


@bp.route("/health/jellyfin", methods=["GET"])
def health_jellyfin():
    """Extended health check for Jellyfin/Emby instances via media server manager."""
    try:
        from mediaserver import get_media_server_manager

        manager = get_media_server_manager()
        manager.load_instances()
        jellyfin_instances = [
            inst for inst in manager._instances.values() if type(inst).name == "jellyfin"
        ]
        if not jellyfin_instances:
            return jsonify(
                {
                    "connection": {"healthy": False, "message": "Jellyfin not configured"},
                }
            )

        instance = jellyfin_instances[0]
        healthy, message = instance.health_check()
        return jsonify({"connection": {"healthy": healthy, "message": message}})
    except Exception as exc:
        logger.error("Jellyfin health check failed: %s", exc)
        return jsonify({"error": f"Jellyfin health check failed: {exc}"}), 500


# ---------------------------------------------------------------------------
# 7. Extended Health: Media Servers
# ---------------------------------------------------------------------------


@bp.route("/health/mediaservers", methods=["GET"])
def health_mediaservers():
    """Extended health check for all configured media server instances."""
    try:
        from mediaserver import get_media_server_manager

        manager = get_media_server_manager()
        manager.load_instances()

        results = []
        for instance_key, instance in manager._instances.items():
            name = instance.config.get("name", instance_key)
            server_type = type(instance).name
            enabled = manager._instance_enabled.get(instance_key, True)

            entry = {
                "name": name,
                "type": server_type,
                "enabled": enabled,
            }

            if hasattr(instance, "extended_health_check"):
                try:
                    health = instance.extended_health_check()
                    entry.update(health)
                except Exception as exc:
                    entry["connection"] = {"healthy": False, "message": str(exc)}
            else:
                # Fall back to basic health_check
                try:
                    healthy, message = instance.health_check()
                    entry["connection"] = {"healthy": healthy, "message": message}
                except Exception as exc:
                    entry["connection"] = {"healthy": False, "message": str(exc)}

            results.append(entry)

        return jsonify({"instances": results})
    except Exception as exc:
        logger.error("Media servers health check failed: %s", exc)
        return jsonify({"error": f"Media servers health check failed: {exc}"}), 500


# ---------------------------------------------------------------------------
# 8. Export Config
# ---------------------------------------------------------------------------


@bp.route("/export", methods=["POST"])
def export_config_endpoint():
    """Export Sublarr config in a specified format.

    Accepts JSON: {format: "bazarr"|"plex"|"kodi"|"json", include_secrets: bool}
    """
    data = request.get_json(silent=True) or {}
    export_format = data.get("format", "json")
    include_secrets = data.get("include_secrets", False)

    valid_formats = {"bazarr", "plex", "kodi", "json"}
    if export_format not in valid_formats:
        return jsonify(
            {
                "error": f"Invalid format '{export_format}'. Supported: {', '.join(sorted(valid_formats))}"
            }
        ), 400

    try:
        from export_manager import export_config

        result = export_config(export_format, include_secrets=include_secrets)
        return jsonify(result)
    except Exception as exc:
        logger.error("Config export failed: %s", exc)
        return jsonify({"error": f"Export failed: {exc}"}), 500


# ---------------------------------------------------------------------------
# 9. Export ZIP
# ---------------------------------------------------------------------------


@bp.route("/export/zip", methods=["POST"])
def export_zip_endpoint():
    """Export Sublarr config as a ZIP archive with multiple formats.

    Accepts JSON: {formats: list, include_secrets: bool}
    Returns ZIP file as application/zip download.
    """
    data = request.get_json(silent=True) or {}
    formats = data.get("formats", [])
    include_secrets = data.get("include_secrets", False)

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

        zip_bytes = export_to_zip(formats, include_secrets=include_secrets)
        return Response(
            zip_bytes,
            mimetype="application/zip",
            headers={
                "Content-Disposition": "attachment; filename=sublarr_export.zip",
            },
        )
    except Exception as exc:
        logger.error("ZIP export failed: %s", exc)
        return jsonify({"error": f"ZIP export failed: {exc}"}), 500


# ---------------------------------------------------------------------------
# 10. Aggregated Health: All Services
# ---------------------------------------------------------------------------


def _health_all_sonarr():
    out = []
    try:
        from config import get_sonarr_instances
        from sonarr_client import SonarrClient

        for inst in get_sonarr_instances():
            name = inst.get("name", "Unnamed")
            try:
                client = SonarrClient(url=inst.get("url", ""), api_key=inst.get("api_key", ""))
                health = client.extended_health_check()
                out.append({"name": name, **health})
            except Exception as exc:
                out.append({"name": name, "connection": {"healthy": False, "message": str(exc)}})
    except Exception as exc:
        logger.debug("Sonarr health aggregation failed: %s", exc)
    return "sonarr", out


def _health_all_radarr():
    out = []
    try:
        from config import get_radarr_instances
        from radarr_client import RadarrClient

        for inst in get_radarr_instances():
            name = inst.get("name", "Unnamed")
            try:
                client = RadarrClient(url=inst.get("url", ""), api_key=inst.get("api_key", ""))
                health = client.extended_health_check()
                out.append({"name": name, **health})
            except Exception as exc:
                out.append({"name": name, "connection": {"healthy": False, "message": str(exc)}})
    except Exception as exc:
        logger.debug("Radarr health aggregation failed: %s", exc)
    return "radarr", out


def _health_all_jellyfin():
    try:
        from mediaserver import get_media_server_manager

        manager = get_media_server_manager()
        manager.load_instances()
        jellyfin_instances = [
            inst for inst in manager._instances.values() if type(inst).name == "jellyfin"
        ]
        if not jellyfin_instances:
            return "jellyfin", {"connection": {"healthy": False, "message": "Not configured"}}
        healthy, message = jellyfin_instances[0].health_check()
        return "jellyfin", {"connection": {"healthy": healthy, "message": message}}
    except Exception as exc:
        logger.debug("Jellyfin health aggregation failed: %s", exc)
        return "jellyfin", {"connection": {"healthy": False, "message": str(exc)}}


def _health_all_media_servers():
    out = []
    try:
        from mediaserver import get_media_server_manager

        manager = get_media_server_manager()
        manager.load_instances()
        for instance_key, instance in manager._instances.items():
            name = instance.config.get("name", instance_key)
            server_type = type(instance).name
            entry = {"name": name, "type": server_type}
            if hasattr(instance, "extended_health_check"):
                try:
                    entry.update(instance.extended_health_check())
                except Exception as exc:
                    entry["connection"] = {"healthy": False, "message": str(exc)}
            else:
                try:
                    healthy, message = instance.health_check()
                    entry["connection"] = {"healthy": healthy, "message": message}
                except Exception as exc:
                    entry["connection"] = {"healthy": False, "message": str(exc)}
            out.append(entry)
    except Exception as exc:
        logger.debug("Media servers health aggregation failed: %s", exc)
    return "media_servers", out


@bp.route("/health/all", methods=["GET"])
def health_all():
    """Aggregated extended health check for all configured services.

    Returns health data from Sonarr, Radarr, Jellyfin, and media server instances.
    """
    result = {"sonarr": [], "radarr": [], "jellyfin": {}, "media_servers": []}

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(_health_all_sonarr),
            executor.submit(_health_all_radarr),
            executor.submit(_health_all_jellyfin),
            executor.submit(_health_all_media_servers),
        ]
        for fut in as_completed(futures):
            try:
                key, value = fut.result()
                result[key] = value
            except Exception as exc:
                logger.debug("Health all task failed: %s", exc)

    return jsonify(result)
