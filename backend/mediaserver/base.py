"""Abstract base class for media server backends and shared data models.

All media server backends implement the same interface: health check,
item-specific refresh, and full library refresh. Adapted from the
TranslationBackend ABC pattern in translation/base.py.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class RefreshResult:
    """Result from a media server refresh call."""

    success: bool
    message: str
    server_name: str = ""
    item_id: str | None = None


class MediaServer(ABC):
    """Abstract base class for media server backends.

    Providers implement three required methods (health_check, refresh_item,
    refresh_library) plus get_config_fields.

    Class-level attributes for config UI and manager orchestration:
        name: Unique backend identifier (lowercase, e.g. "jellyfin", "plex", "kodi")
        display_name: Human-readable name for Settings UI
        config_fields: Declarative config field definitions for dynamic UI forms.
            Each dict: {"key": str, "label": str, "type": "text"|"password"|"number",
                        "required": bool, "default": str, "help": str}
    """

    name: str = "unknown"
    display_name: str = "Unknown"
    config_fields: list[dict] = []

    def __init__(self, **config):
        self.config = config

    @abstractmethod
    def health_check(self) -> tuple[bool, str]:
        """Check if the media server is reachable and configured correctly.

        Returns:
            (is_healthy, message) tuple
        """
        ...

    @abstractmethod
    def refresh_item(self, file_path: str, item_type: str = "") -> RefreshResult:
        """Refresh metadata for a specific item by file path.

        Args:
            file_path: Path to the media file (used to find item in server)
            item_type: "episode" or "movie" hint

        Returns:
            RefreshResult with success status
        """
        ...

    @abstractmethod
    def refresh_library(self) -> RefreshResult:
        """Trigger a full library scan (fallback).

        Returns:
            RefreshResult with success status
        """
        ...

    def get_config_fields(self) -> list[dict]:
        """Return config field definitions for the Settings UI.

        Returns:
            List of field dicts with key, label, type, required, default, help
        """
        return self.config_fields

    def apply_path_mapping(self, file_path: str) -> str:
        """Transform file_path using optional path_mapping from config.

        If path_mapping is set as "from_path:to_path", replaces from_path
        prefix with to_path. If not set, returns file_path unchanged.

        Args:
            file_path: Original file path

        Returns:
            Mapped file path
        """
        path_mapping = self.config.get("path_mapping", "")
        if not path_mapping or ":" not in path_mapping:
            return file_path

        from_path, to_path = path_mapping.split(":", 1)
        if file_path.startswith(from_path):
            return to_path + file_path[len(from_path) :]
        return file_path
