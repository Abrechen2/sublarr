"""Jellyfin/Emby media server backend.

Migrated from jellyfin_client.py into the MediaServer ABC. Preserves all
existing retry logic, rate limit handling, and error logging. Works for
both Jellyfin and Emby since they share the same API (X-MediaBrowser-Token).
"""

import logging
import os
import time

import requests

from mediaserver.base import MediaServer, RefreshResult

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15
MAX_RETRIES = 2
BACKOFF_BASE = 2


class JellyfinEmbyServer(MediaServer):
    """Jellyfin/Emby REST API backend."""

    name = "jellyfin"
    display_name = "Jellyfin / Emby"
    config_fields = [
        {
            "key": "url",
            "label": "Server URL",
            "type": "text",
            "required": True,
            "default": "http://localhost:8096",
            "help": "Jellyfin/Emby server URL (e.g. http://192.168.1.100:8096)",
        },
        {
            "key": "api_key",
            "label": "API Key",
            "type": "password",
            "required": True,
            "default": "",
            "help": "API key from Jellyfin Dashboard > API Keys or Emby Server > API Keys",
        },
        {
            "key": "server_type",
            "label": "Server Type",
            "type": "text",
            "required": False,
            "default": "jellyfin",
            "help": "jellyfin or emby (both use the same API)",
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
        url = config.get("url", "http://localhost:8096")
        self.url = url.rstrip("/")
        self.api_key = config.get("api_key", "")
        self.server_type = config.get("server_type", "jellyfin")
        self.session = requests.Session()
        self.session.headers["X-MediaBrowser-Token"] = self.api_key

    def _get(self, path, params=None, timeout=REQUEST_TIMEOUT):
        """GET request with retry logic."""
        url = f"{self.url}{path}"
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self.session.get(url, params=params, timeout=timeout)
                if resp.status_code == 429:
                    retry_after = resp.headers.get("Retry-After")
                    if retry_after:
                        try:
                            wait_seconds = int(retry_after)
                        except ValueError:
                            wait_seconds = 60
                    else:
                        wait_seconds = 60
                    logger.warning(
                        "Jellyfin GET %s rate limited (attempt %d), waiting %ds",
                        path,
                        attempt,
                        wait_seconds,
                    )
                    if attempt < MAX_RETRIES:
                        time.sleep(wait_seconds)
                        continue
                    else:
                        logger.error(
                            "Jellyfin GET %s rate limited after %d attempts",
                            path,
                            MAX_RETRIES,
                        )
                        return None
                resp.raise_for_status()
                return resp.json()
            except requests.ConnectionError as e:
                logger.warning("Jellyfin GET %s failed (attempt %d): %s", path, attempt, e)
            except requests.Timeout:
                logger.warning("Jellyfin GET %s timed out (attempt %d)", path, attempt)
            except Exception as e:
                logger.error("Jellyfin unexpected error on GET %s: %s", path, e)
                return None
            if attempt < MAX_RETRIES:
                time.sleep(BACKOFF_BASE * attempt)
        return None

    def _post(self, path, data=None, timeout=REQUEST_TIMEOUT):
        """POST request with retry logic."""
        url = f"{self.url}{path}"
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self.session.post(url, json=data, timeout=timeout)
                if resp.status_code == 429:
                    retry_after = resp.headers.get("Retry-After")
                    if retry_after:
                        try:
                            wait_seconds = int(retry_after)
                        except ValueError:
                            wait_seconds = 60
                    else:
                        wait_seconds = 60
                    logger.warning(
                        "Jellyfin POST %s rate limited (attempt %d), waiting %ds",
                        path,
                        attempt,
                        wait_seconds,
                    )
                    if attempt < MAX_RETRIES:
                        time.sleep(wait_seconds)
                        continue
                    else:
                        logger.error(
                            "Jellyfin POST %s rate limited after %d attempts",
                            path,
                            MAX_RETRIES,
                        )
                        return None
                resp.raise_for_status()
                return resp.json() if resp.content else {}
            except requests.ConnectionError as e:
                logger.warning("Jellyfin POST %s failed (attempt %d): %s", path, attempt, e)
            except requests.Timeout:
                logger.warning("Jellyfin POST %s timed out (attempt %d)", path, attempt)
            except Exception as e:
                logger.error("Jellyfin unexpected error on POST %s: %s", path, e)
                return None
            if attempt < MAX_RETRIES:
                time.sleep(BACKOFF_BASE * attempt)
        return None

    def health_check(self) -> tuple[bool, str]:
        """Check if Jellyfin/Emby is reachable.

        Returns:
            (is_healthy, message) tuple
        """
        result = self._get("/System/Info/Public")
        if result is not None:
            server_name = result.get("ServerName", "Unknown")
            version = result.get("Version", "?")
            return True, f"{server_name} v{version}"
        return False, f"Cannot connect to {self.server_type.title()} at {self.url}"

    def refresh_item(self, file_path: str, item_type: str = "") -> RefreshResult:
        """Refresh metadata for a specific item by file path.

        Applies path mapping, searches for the item, then triggers refresh.
        Falls back to refresh_library() if item not found.
        """
        mapped_path = self.apply_path_mapping(file_path)
        item_id = self._search_item_by_path(mapped_path)

        if not item_id:
            logger.info(
                "Item not found by path in %s, falling back to library refresh: %s",
                self.server_type.title(),
                mapped_path,
            )
            return self.refresh_library()

        result = self._post(
            f"/Items/{item_id}/Refresh",
            data={
                "Recursive": False,
                "MetadataRefreshMode": "Default",
                "ImageRefreshMode": "None",
                "ReplaceAllMetadata": False,
                "ReplaceAllImages": False,
            },
        )
        if result is not None:
            type_str = f" ({item_type})" if item_type else ""
            logger.info(
                "Triggered %s item refresh for %s%s",
                self.server_type.title(),
                item_id,
                type_str,
            )
            return RefreshResult(
                success=True,
                message=f"Refreshed item {item_id}{type_str}",
                server_name=self.config.get("name", self.display_name),
                item_id=item_id,
            )

        return RefreshResult(
            success=False,
            message=f"Failed to refresh item {item_id} on {self.server_type.title()}",
            server_name=self.config.get("name", self.display_name),
        )

    def refresh_library(self) -> RefreshResult:
        """Trigger a full library scan (fallback).

        Returns:
            RefreshResult with success status
        """
        result = self._post("/Library/Refresh")
        if result is not None:
            logger.info("Triggered %s full library refresh", self.server_type.title())
            return RefreshResult(
                success=True,
                message=f"Full library refresh triggered on {self.server_type.title()}",
                server_name=self.config.get("name", self.display_name),
            )
        return RefreshResult(
            success=False,
            message=f"Failed to trigger library refresh on {self.server_type.title()}",
            server_name=self.config.get("name", self.display_name),
        )

    def _search_item_by_path(self, file_path: str):
        """Search for a Jellyfin/Emby item by file path.

        Best-effort search: Jellyfin doesn't have a direct path-to-item
        lookup. We search by filename and match by path.

        Returns:
            str or None: Item ID if found
        """
        filename = os.path.basename(file_path)
        name = os.path.splitext(filename)[0]

        result = self._get(
            "/Items",
            params={
                "searchTerm": name,
                "Recursive": True,
                "IncludeItemTypes": "Episode,Movie",
                "Limit": 5,
            },
        )

        if result and result.get("Items"):
            for item in result["Items"]:
                item_path = item.get("Path", "")
                if file_path in item_path or filename in item_path:
                    return item["Id"]
            # Fallback: return first result
            return result["Items"][0].get("Id")

        return None
