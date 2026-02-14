"""Jellyfin/Emby API client for library refresh notifications.

After a new subtitle file is created, Jellyfin/Emby can be notified
to refresh metadata so the new subtitle appears in the player.
Emby uses an identical API structure.
"""

import logging
import time

import requests

from config import get_settings

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15
MAX_RETRIES = 2
BACKOFF_BASE = 2

_client = None


def get_jellyfin_client():
    """Get or create the singleton Jellyfin client. Returns None if not configured."""
    global _client
    if _client is not None:
        return _client
    settings = get_settings()
    if not settings.jellyfin_url or not settings.jellyfin_api_key:
        logger.debug("Jellyfin not configured (jellyfin_url or jellyfin_api_key missing)")
        return None
    _client = JellyfinClient(settings.jellyfin_url, settings.jellyfin_api_key)
    return _client


def invalidate_client():
    """Reset the singleton so the next call to get_jellyfin_client() creates a fresh instance."""
    global _client
    _client = None


class JellyfinClient:
    """Jellyfin/Emby REST API Client."""

    def __init__(self, url, api_key):
        self.url = url.rstrip("/")
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers["X-MediaBrowser-Token"] = api_key

    def _post(self, path, data=None, timeout=REQUEST_TIMEOUT):
        """POST request with retry logic."""
        url = f"{self.url}{path}"
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self.session.post(url, json=data, timeout=timeout)
                # Handle rate limiting (429) before raise_for_status
                if resp.status_code == 429:
                    retry_after = resp.headers.get("Retry-After")
                    if retry_after:
                        try:
                            wait_seconds = int(retry_after)
                        except ValueError:
                            wait_seconds = 60
                    else:
                        wait_seconds = 60
                    logger.warning("Jellyfin POST %s rate limited (attempt %d), waiting %ds", path, attempt, wait_seconds)
                    if attempt < MAX_RETRIES:
                        time.sleep(wait_seconds)
                        continue
                    else:
                        logger.error("Jellyfin POST %s rate limited after %d attempts", path, MAX_RETRIES)
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

    def _get(self, path, params=None, timeout=REQUEST_TIMEOUT):
        """GET request with retry logic."""
        url = f"{self.url}{path}"
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self.session.get(url, params=params, timeout=timeout)
                # Handle rate limiting (429) before raise_for_status
                if resp.status_code == 429:
                    retry_after = resp.headers.get("Retry-After")
                    if retry_after:
                        try:
                            wait_seconds = int(retry_after)
                        except ValueError:
                            wait_seconds = 60
                    else:
                        wait_seconds = 60
                    logger.warning("Jellyfin GET %s rate limited (attempt %d), waiting %ds", path, attempt, wait_seconds)
                    if attempt < MAX_RETRIES:
                        time.sleep(wait_seconds)
                        continue
                    else:
                        logger.error("Jellyfin GET %s rate limited after %d attempts", path, MAX_RETRIES)
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

    def health_check(self):
        """Check if Jellyfin/Emby is reachable.

        Returns:
            tuple: (is_healthy: bool, message: str)
        """
        result = self._get("/System/Info/Public")
        if result is not None:
            server_name = result.get("ServerName", "Unknown")
            version = result.get("Version", "?")
            return True, f"{server_name} v{version}"
        return False, f"Cannot connect to Jellyfin at {self.url}"

    def refresh_item(self, item_id, item_type=None):
        """Refresh metadata for a specific item.

        Args:
            item_id: Jellyfin/Emby item ID
            item_type: Optional item type ("Episode" or "Movie") for logging

        Returns:
            bool: True if refresh was triggered successfully
        """
        result = self._post(f"/Items/{item_id}/Refresh", data={
            "Recursive": False,
            "MetadataRefreshMode": "Default",
            "ImageRefreshMode": "None",
            "ReplaceAllMetadata": False,
            "ReplaceAllImages": False,
        })
        if result is not None:
            type_str = f" ({item_type})" if item_type else ""
            logger.info("Triggered Emby item refresh for %s%s", item_id, type_str)
            return True
        return False

    def refresh_library(self):
        """Trigger a full library scan (fallback).

        Returns:
            bool: True if scan was triggered successfully
        """
        result = self._post("/Library/Refresh")
        if result is not None:
            logger.info("Triggered Jellyfin full library refresh")
            return True
        return False

    def search_item_by_path(self, file_path):
        """Search for a Jellyfin item by file path.

        This is a best-effort search — Jellyfin doesn't have a direct
        path-to-item lookup. We search by filename.

        Returns:
            str or None: Item ID if found
        """
        import os
        filename = os.path.basename(file_path)
        name = os.path.splitext(filename)[0]

        result = self._get("/Items", params={
            "searchTerm": name,
            "Recursive": True,
            "IncludeItemTypes": "Episode,Movie",
            "Limit": 5,
        })

        if result and result.get("Items"):
            for item in result["Items"]:
                item_path = item.get("Path", "")
                if file_path in item_path or filename in item_path:
                    return item["Id"]
            # Fallback: return first result
            return result["Items"][0].get("Id")

        return None
