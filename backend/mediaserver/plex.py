"""Plex media server backend using the plexapi library.

Connects via plexapi.server.PlexServer, finds items by file path across
library sections, and triggers per-item or section-wide metadata refresh.
plexapi is an optional dependency -- the class is still importable without it.
"""

import logging
from typing import Optional

import requests

from mediaserver.base import MediaServer, RefreshResult

logger = logging.getLogger(__name__)

# Guard plexapi import -- optional dependency
try:
    from plexapi.server import PlexServer as _PlexServer
    from plexapi import exceptions as plex_exceptions
    _HAS_PLEXAPI = True
except ImportError:
    _PlexServer = None
    plex_exceptions = None
    _HAS_PLEXAPI = False


class PlexServer(MediaServer):
    """Plex media server backend using plexapi library."""

    name = "plex"
    display_name = "Plex"
    config_fields = [
        {
            "key": "url",
            "label": "Server URL",
            "type": "text",
            "required": True,
            "default": "http://localhost:32400",
            "help": "Plex server URL (e.g. http://192.168.1.100:32400)",
        },
        {
            "key": "token",
            "label": "X-Plex-Token",
            "type": "password",
            "required": True,
            "default": "",
            "help": "Find in Plex Settings > Troubleshooting > View XML > X-Plex-Token parameter",
        },
        {
            "key": "path_mapping",
            "label": "Path Mapping",
            "type": "text",
            "required": False,
            "default": "",
            "help": "from_path:to_path for Docker volume mapping (e.g. /media:/data)",
        },
    ]

    def __init__(self, **config):
        super().__init__(**config)
        self.url = config.get("url", "http://localhost:32400").rstrip("/")
        self.token = config.get("token", "")
        self._server: Optional[object] = None  # Lazily created PlexServer

    def _get_server(self):
        """Lazily create and cache the plexapi PlexServer connection.

        Raises:
            RuntimeError: If plexapi is not installed
            Exception: If connection fails
        """
        if not _HAS_PLEXAPI:
            raise RuntimeError(
                "plexapi package not installed. Install with: pip install PlexAPI"
            )

        if self._server is None:
            self._server = _PlexServer(self.url, self.token)
        return self._server

    def health_check(self) -> tuple[bool, str]:
        """Check if Plex is reachable.

        Returns:
            (is_healthy, message) tuple
        """
        if not _HAS_PLEXAPI:
            return False, "plexapi package not installed. Install with: pip install PlexAPI"

        try:
            server = self._get_server()
            friendly_name = server.friendlyName
            version = server.version
            return True, f"{friendly_name} v{version}"
        except Exception as e:
            # Reset cached server on connection failure
            self._server = None
            if plex_exceptions and isinstance(e, plex_exceptions.Unauthorized):
                return False, f"Plex authentication failed (invalid token): {e}"
            if isinstance(e, requests.ConnectionError):
                return False, f"Cannot connect to Plex at {self.url}"
            return False, f"Plex health check failed: {e}"

    def extended_health_check(self) -> dict:
        """Extended diagnostic health check for Plex.

        Returns a structured dict with connection status, server info,
        library sections, and health issues. Each sub-query is wrapped
        in try/except for graceful degradation.

        Returns:
            dict with keys: connection, server_info, library_access,
                  health_issues
        """
        report = {
            "connection": {"healthy": False, "message": ""},
            "server_info": {"friendly_name": "", "version": "", "platform": ""},
            "library_access": {"section_count": 0, "sections": [], "accessible": False},
            "health_issues": [],
        }

        # 1. Check plexapi availability
        if not _HAS_PLEXAPI:
            report["connection"]["message"] = "plexapi not installed"
            return report

        # 2. Connect to server
        try:
            server = self._get_server()
        except Exception as exc:
            self._server = None
            report["connection"]["message"] = f"Cannot connect to Plex at {self.url}: {exc}"
            return report

        report["connection"]["healthy"] = True
        report["connection"]["message"] = "OK"

        # 3. Server info
        try:
            report["server_info"]["friendly_name"] = getattr(server, "friendlyName", "")
            report["server_info"]["version"] = getattr(server, "version", "")
            report["server_info"]["platform"] = getattr(server, "platform", "")
        except Exception as exc:
            logger.debug("Extended health check: server info failed: %s", exc)

        # 4. Library sections
        try:
            sections = server.library.sections()
            report["library_access"]["accessible"] = True
            report["library_access"]["section_count"] = len(sections)
            for section in sections:
                report["library_access"]["sections"].append({
                    "title": getattr(section, "title", ""),
                    "type": getattr(section, "type", ""),
                })
        except Exception as exc:
            logger.debug("Extended health check: library sections failed: %s", exc)

        return report

    def refresh_item(self, file_path: str, item_type: str = "") -> RefreshResult:
        """Refresh metadata for a specific item by file path.

        Searches library sections for the item matching the file path,
        then triggers item.refresh(). Falls back to refresh_library()
        if item not found.
        """
        mapped_path = self.apply_path_mapping(file_path)

        try:
            server = self._get_server()
        except Exception as e:
            return RefreshResult(
                success=False,
                message=f"Cannot connect to Plex: {e}",
                server_name=self.config.get("name", self.display_name),
            )

        try:
            sections = server.library.sections()
        except Exception as e:
            return RefreshResult(
                success=False,
                message=f"Failed to get Plex library sections: {e}",
                server_name=self.config.get("name", self.display_name),
            )

        # Determine which section types to search
        for section in sections:
            # Filter by section type based on item_type hint
            if item_type == "episode" and section.type != "show":
                continue
            if item_type == "movie" and section.type != "movie":
                continue

            try:
                item = self._find_item_in_section(section, mapped_path)
                if item:
                    item.refresh()
                    item_title = getattr(item, "title", "Unknown")
                    logger.info(
                        "Triggered Plex item refresh for '%s' in section '%s'",
                        item_title, section.title,
                    )
                    return RefreshResult(
                        success=True,
                        message=f"Refreshed '{item_title}' in {section.title}",
                        server_name=self.config.get("name", self.display_name),
                        item_id=str(getattr(item, "ratingKey", "")),
                    )
            except Exception as e:
                logger.debug(
                    "Error searching Plex section '%s': %s", section.title, e
                )
                continue

        # Item not found -- fall back to full library refresh
        logger.info(
            "Item not found by path in Plex, falling back to library refresh: %s",
            mapped_path,
        )
        return self.refresh_library()

    def refresh_library(self) -> RefreshResult:
        """Trigger a full library scan across all sections.

        Returns:
            RefreshResult with success status
        """
        try:
            server = self._get_server()
            sections = server.library.sections()
            for section in sections:
                try:
                    section.update()
                except Exception as e:
                    logger.warning(
                        "Failed to update Plex section '%s': %s",
                        section.title, e,
                    )
            logger.info("Triggered Plex full library refresh (%d sections)", len(sections))
            return RefreshResult(
                success=True,
                message=f"Full library refresh triggered ({len(sections)} sections)",
                server_name=self.config.get("name", self.display_name),
            )
        except Exception as e:
            return RefreshResult(
                success=False,
                message=f"Failed to trigger Plex library refresh: {e}",
                server_name=self.config.get("name", self.display_name),
            )

    def _find_item_in_section(self, section, mapped_file_path: str):
        """Search a library section for an item matching the file path.

        Uses server-side filtering by file path prefix (Media__Part__file),
        then verifies the exact file path match client-side.

        Args:
            section: plexapi library section
            mapped_file_path: File path after path mapping

        Returns:
            Plex item if found, None otherwise
        """
        import os
        mapped_dir = os.path.dirname(mapped_file_path)

        try:
            # Server-side filter by directory prefix
            results = section.search(
                filters={"Media__Part__file__startswith": mapped_dir}
            )
        except Exception:
            # Fallback: some older Plex versions may not support this filter
            logger.debug(
                "Media__Part__file filter not supported in section '%s', skipping",
                section.title,
            )
            return None

        for item in results:
            # Check locations for movies
            if hasattr(item, "locations"):
                for location in item.locations:
                    if mapped_file_path in location or location in mapped_file_path:
                        return item

            # Check media parts for episodes and other types
            if hasattr(item, "media"):
                for media in item.media:
                    for part in media.parts:
                        if hasattr(part, "file"):
                            if mapped_file_path in part.file or part.file in mapped_file_path:
                                return item

            # For show sections, check episodes
            if section.type == "show" and hasattr(item, "episodes"):
                try:
                    for episode in item.episodes():
                        if hasattr(episode, "media"):
                            for media in episode.media:
                                for part in media.parts:
                                    if hasattr(part, "file"):
                                        if mapped_file_path in part.file or part.file in mapped_file_path:
                                            return episode
                except Exception:
                    continue

        return None
