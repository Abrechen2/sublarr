"""Media server package -- multi-backend media server management.

Provides the MediaServerManager singleton which registers backend types,
manages instances with lazy creation from config_entries, dispatches
refresh_all to ALL configured servers, and tracks per-instance health
via circuit breakers.

CRITICAL DIFFERENCE from TranslationManager: Media servers use refresh_all
(notify ALL servers), not translate_with_fallback (try until one succeeds).
Config is stored as a JSON array in a single media_servers_json config_entries
key, because users configure multiple named instances.
"""

import json
import logging

from circuit_breaker import CircuitBreaker
from mediaserver.base import MediaServer, RefreshResult

logger = logging.getLogger(__name__)


class MediaServerManager:
    """Manages media server backends and dispatches refresh notifications.

    Backend classes are registered at import time. Instances are created
    from a JSON array stored in config_entries as media_servers_json.
    Each entry: {"type": "jellyfin", "name": "My Jellyfin", "enabled": true, ...config}
    """

    def __init__(self):
        self._server_classes: dict[str, type[MediaServer]] = {}
        self._instances: dict[str, MediaServer] = {}
        self._circuit_breakers: dict[str, CircuitBreaker] = {}
        self._instance_enabled: dict[str, bool] = {}

    def register_server_type(self, cls: type[MediaServer]) -> None:
        """Register a server backend class by its name attribute."""
        self._server_classes[cls.name] = cls
        logger.debug("Registered media server type: %s", cls.name)

    def get_all_server_types(self) -> list[dict]:
        """Return info about all registered server types.

        Returns:
            List of dicts with name, display_name, config_fields
        """
        result = []
        for name, cls in self._server_classes.items():
            result.append({
                "name": cls.name,
                "display_name": cls.display_name,
                "config_fields": cls.config_fields,
            })
        return result

    def load_instances(self) -> None:
        """Load media server instances from config_entries DB.

        Reads the media_servers_json key, parses the JSON array, and
        creates instances. Clears old instances before loading.

        Each entry format:
            {"type": "jellyfin", "name": "My Jellyfin", "enabled": true, ...config_keys}
        """
        self._instances.clear()
        self._instance_enabled.clear()
        # Keep circuit breakers across reloads (they track state)

        servers_json = self._load_config_json()
        if not servers_json:
            logger.debug("No media servers configured (media_servers_json empty)")
            return

        for idx, entry in enumerate(servers_json):
            server_type = entry.get("type", "")
            cls = self._server_classes.get(server_type)
            if not cls:
                logger.warning(
                    "Unknown media server type '%s' at index %d, skipping",
                    server_type, idx,
                )
                continue

            instance_key = f"{server_type}_{idx}"
            enabled = entry.get("enabled", True)
            self._instance_enabled[instance_key] = enabled

            # Extract config: everything except type and enabled
            config = {k: v for k, v in entry.items() if k not in ("type", "enabled")}

            try:
                instance = cls(**config)
                self._instances[instance_key] = instance
                logger.info(
                    "Created media server instance: %s (%s)",
                    entry.get("name", instance_key), server_type,
                )
            except Exception as e:
                logger.error(
                    "Failed to create media server %s at index %d: %s",
                    server_type, idx, e,
                )

    def refresh_all(self, file_path: str, item_type: str = "") -> list[RefreshResult]:
        """Notify ALL configured media servers about a new subtitle.

        Unlike translation (try until one succeeds), media servers are
        all-notify: every enabled server gets the refresh. Skips instances
        with OPEN circuit breakers. Never raises -- always returns results.

        Tries item-specific refresh first; if it fails (item not found),
        the backend itself falls back to refresh_library.
        """
        results = []

        for instance_key, instance in self._instances.items():
            # Skip disabled instances
            if not self._instance_enabled.get(instance_key, True):
                continue

            # Check circuit breaker
            cb = self._get_circuit_breaker(instance_key)
            if not cb.allow_request():
                logger.info(
                    "Skipping media server %s (circuit breaker OPEN)",
                    instance_key,
                )
                results.append(RefreshResult(
                    success=False,
                    message=f"Skipped {instance_key} (circuit breaker OPEN)",
                    server_name=instance.config.get("name", instance_key),
                ))
                continue

            try:
                result = instance.refresh_item(file_path, item_type)
                if result.success:
                    cb.record_success()
                else:
                    cb.record_failure()
                results.append(result)
            except Exception as e:
                cb.record_failure()
                logger.warning(
                    "Media server %s refresh failed: %s", instance_key, e
                )
                results.append(RefreshResult(
                    success=False,
                    message=f"Error refreshing {instance_key}: {e}",
                    server_name=instance.config.get("name", instance_key),
                ))

        return results

    def health_check_all(self) -> list[dict]:
        """Check health of all configured media server instances.

        Returns:
            List of dicts with name, type, healthy, message
        """
        results = []
        for instance_key, instance in self._instances.items():
            try:
                healthy, message = instance.health_check()
                results.append({
                    "name": instance.config.get("name", instance_key),
                    "type": type(instance).name,
                    "instance_key": instance_key,
                    "healthy": healthy,
                    "message": message,
                    "enabled": self._instance_enabled.get(instance_key, True),
                })
            except Exception as e:
                results.append({
                    "name": instance.config.get("name", instance_key),
                    "type": type(instance).name,
                    "instance_key": instance_key,
                    "healthy": False,
                    "message": str(e),
                    "enabled": self._instance_enabled.get(instance_key, True),
                })
        return results

    def invalidate_instances(self) -> None:
        """Clear cached instances (for config reload)."""
        self._instances.clear()
        self._instance_enabled.clear()
        logger.info("Invalidated all media server instances")

    def _get_circuit_breaker(self, instance_key: str) -> CircuitBreaker:
        """Get or create a circuit breaker for a server instance."""
        if instance_key not in self._circuit_breakers:
            try:
                from config import get_settings
                settings = get_settings()
                threshold = settings.circuit_breaker_failure_threshold
                cooldown = settings.circuit_breaker_cooldown_seconds
            except Exception:
                threshold = 5
                cooldown = 60
            self._circuit_breakers[instance_key] = CircuitBreaker(
                name=f"mediaserver:{instance_key}",
                failure_threshold=threshold,
                cooldown_seconds=cooldown,
            )
        return self._circuit_breakers[instance_key]

    def _load_config_json(self) -> list[dict]:
        """Load the media_servers_json from config_entries DB.

        Returns:
            Parsed list of server config dicts, or empty list
        """
        try:
            from db.config import get_config_entry
            raw = get_config_entry("media_servers_json")
            if raw:
                data = json.loads(raw)
                if isinstance(data, list):
                    return data
                logger.warning("media_servers_json is not an array: %s", type(data))
        except Exception as e:
            logger.debug("Could not load media_servers_json: %s", e)
        return []


# --- Singleton ---

_manager: MediaServerManager | None = None


def get_media_server_manager() -> MediaServerManager:
    """Get or create the singleton MediaServerManager instance."""
    global _manager
    if _manager is None:
        _manager = MediaServerManager()
        _register_builtin_servers(_manager)
    return _manager


def invalidate_media_server_manager() -> None:
    """Destroy the singleton instance (for testing or config reload)."""
    global _manager
    _manager = None


def _register_builtin_servers(manager: MediaServerManager) -> None:
    """Register all built-in media server backends."""
    from mediaserver.jellyfin import JellyfinEmbyServer
    manager.register_server_type(JellyfinEmbyServer)

    # Plex: optional dependency (plexapi package may not be installed)
    try:
        from mediaserver.plex import PlexServer
        manager.register_server_type(PlexServer)
    except ImportError:
        logger.info("Plex backend not available (plexapi package not installed)")

    # Kodi: uses stdlib requests (always available)
    from mediaserver.kodi import KodiServer
    manager.register_server_type(KodiServer)
