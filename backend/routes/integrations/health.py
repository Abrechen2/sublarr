"""Extended health-check routes — /health/sonarr, /health/radarr, /health/jellyfin, /health/mediaservers, /health/all."""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from flask import jsonify

from routes.integrations import bp

logger = logging.getLogger(__name__)


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
