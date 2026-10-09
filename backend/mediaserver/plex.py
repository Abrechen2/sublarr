"""Plex media server backend using the plexapi library.

Connects via plexapi.server.PlexServer and asks Plex to scan the folder that
received a new subtitle (partial scan), falling back to section-wide scans.
plexapi is an optional dependency -- the class is still importable without it.
"""

import logging
import os

import requests

from mediaserver.base import MediaServer, RefreshResult

logger = logging.getLogger(__name__)

# Guard plexapi import -- optional dependency
try:
    from plexapi import exceptions as plex_exceptions
    from plexapi.server import PlexServer as _PlexServer

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
        self._server: object | None = None  # Lazily created PlexServer

    def _get_server(self):
        """Lazily create and cache the plexapi PlexServer connection.

        Raises:
            RuntimeError: If plexapi is not installed
            Exception: If connection fails
        """
        if not _HAS_PLEXAPI:
            raise RuntimeError("plexapi package not installed. Install with: pip install PlexAPI")

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
                report["library_access"]["sections"].append(
                    {
                        "title": getattr(section, "title", ""),
                        "type": getattr(section, "type", ""),
                    }
                )
        except Exception as exc:
            logger.debug("Extended health check: library sections failed: %s", exc)

        return report

    def refresh_item(
        self, file_path: str, item_type: str = "", library_fallback: bool = True
    ) -> RefreshResult:
        """Scan the folder that holds ``file_path`` in the library that owns it.

        A new subtitle is a new file on disk, which is a scan job for Plex:
        ``section.update(path=folder)`` is its partial scan. The section is the
        one whose root folder contains the file, so no search is needed.

        The previous lookup filtered on ``Media__Part__file__startswith``, a
        name plexapi rejects before anything reaches Plex, so every subtitle
        ended in a full scan of every library (#219).

        When no section contains the folder (usually a path mapping that does
        not match Plex's view), sections of the matching type get a full scan
        — or, with ``library_fallback=False``, the caller is told to run one.
        """
        mapped_path = self.apply_path_mapping(file_path)
        server_name = self.config.get("name", self.display_name)

        try:
            sections = self._get_server().library.sections()
        except Exception as e:
            self._server = None
            return RefreshResult(
                success=False,
                message=f"Cannot reach Plex library sections: {e}",
                server_name=server_name,
            )

        folder = os.path.dirname(mapped_path)
        section = _section_containing(_sections_of_type(sections, item_type), folder)
        if section is not None:
            try:
                section.update(path=folder)
            except Exception as e:
                logger.warning(
                    "Plex partial scan of '%s' in section '%s' failed: %s",
                    folder,
                    section.title,
                    e,
                )
                return RefreshResult(
                    success=False,
                    message=f"Plex partial scan failed in {section.title}: {e}",
                    server_name=server_name,
                )
            logger.info(
                "Triggered Plex partial scan of '%s' in section '%s'", folder, section.title
            )
            return RefreshResult(
                success=True,
                message=f"Scanned {folder} in {section.title}",
                server_name=server_name,
            )

        if not library_fallback:
            return RefreshResult(
                success=False,
                message=f"No Plex library contains {folder}",
                server_name=server_name,
                needs_library_refresh=True,
            )
        logger.info(
            "No Plex library contains '%s' (check the path mapping), scanning %s libraries",
            folder,
            item_type or "all",
        )
        return self.refresh_library(item_type)

    def refresh_library(self, item_type: str = "") -> RefreshResult:
        """Trigger a full scan of every section, or only those matching ``item_type``."""
        server_name = self.config.get("name", self.display_name)
        try:
            sections = _sections_of_type(self._get_server().library.sections(), item_type)
        except Exception as e:
            self._server = None
            return RefreshResult(
                success=False,
                message=f"Failed to trigger Plex library refresh: {e}",
                server_name=server_name,
            )
        for section in sections:
            try:
                section.update()
            except Exception as e:
                logger.warning("Failed to update Plex section '%s': %s", section.title, e)
        logger.info("Triggered Plex full library refresh (%d sections)", len(sections))
        return RefreshResult(
            success=True,
            message=f"Full library refresh triggered ({len(sections)} sections)",
            server_name=server_name,
        )


_SECTION_TYPE_FOR_ITEM = {"episode": "show", "movie": "movie"}


def _sections_of_type(sections, item_type: str) -> list:
    wanted = _SECTION_TYPE_FOR_ITEM.get(item_type)
    return [s for s in sections if wanted is None or s.type == wanted]


def _normalise(path: str) -> str:
    return path.replace("\\", "/").rstrip("/")


def _section_containing(sections, folder: str):
    """The section with the deepest root folder that contains ``folder``, or None."""
    target = _normalise(folder)
    best, best_len = None, -1
    for section in sections:
        for location in getattr(section, "locations", None) or []:
            root = _normalise(location)
            if root and (target == root or target.startswith(root + "/")) and len(root) > best_len:
                best, best_len = section, len(root)
    return best
