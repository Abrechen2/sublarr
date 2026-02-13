"""Sonarr v3 API client for series/episode management.

Provides series listing, episode enumeration, file paths, tag filtering,
and RescanSeries commands after new subtitle files are created.
"""

import logging
import time

import requests

from config import get_settings

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15
MAX_RETRIES = 3
BACKOFF_BASE = 2

_client = None


def get_sonarr_client():
    """Get or create the singleton Sonarr client. Returns None if not configured."""
    global _client
    if _client is not None:
        return _client
    settings = get_settings()
    if not settings.sonarr_url or not settings.sonarr_api_key:
        logger.debug("Sonarr not configured (sonarr_url or sonarr_api_key missing)")
        return None
    _client = SonarrClient(settings.sonarr_url, settings.sonarr_api_key)
    return _client


class SonarrClient:
    """Sonarr v3 REST API Client."""

    def __init__(self, url, api_key):
        self.url = url.rstrip("/")
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers["X-Api-Key"] = api_key

    def _get(self, path, params=None, timeout=REQUEST_TIMEOUT):
        """GET request with retry logic."""
        url = f"{self.url}/api/v3{path}"
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self.session.get(url, params=params, timeout=timeout)
                resp.raise_for_status()
                return resp.json()
            except requests.ConnectionError as e:
                logger.warning("Sonarr GET %s failed (attempt %d): %s", path, attempt, e)
            except requests.Timeout:
                logger.warning("Sonarr GET %s timed out (attempt %d)", path, attempt)
            except requests.HTTPError as e:
                logger.error("Sonarr HTTP error on GET %s: %s", path, e)
                return None
            except Exception as e:
                logger.error("Sonarr unexpected error on GET %s: %s", path, e)
                return None
            if attempt < MAX_RETRIES:
                time.sleep(BACKOFF_BASE * attempt)
        logger.error("Sonarr GET %s failed after %d attempts", path, MAX_RETRIES)
        return None

    def _post(self, path, data=None, timeout=REQUEST_TIMEOUT):
        """POST request with retry logic."""
        url = f"{self.url}/api/v3{path}"
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self.session.post(url, json=data, timeout=timeout)
                resp.raise_for_status()
                return resp.json() if resp.content else {}
            except requests.ConnectionError as e:
                logger.warning("Sonarr POST %s failed (attempt %d): %s", path, attempt, e)
            except requests.Timeout:
                logger.warning("Sonarr POST %s timed out (attempt %d)", path, attempt)
            except Exception as e:
                logger.error("Sonarr unexpected error on POST %s: %s", path, e)
                return None
            if attempt < MAX_RETRIES:
                time.sleep(BACKOFF_BASE * attempt)
        return None

    def health_check(self):
        """Check if Sonarr is reachable.

        Returns:
            tuple: (is_healthy: bool, message: str)
        """
        result = self._get("/system/status")
        if result is not None:
            return True, "OK"
        return False, f"Cannot connect to Sonarr at {self.url}"

    def get_series(self):
        """Get all series.

        Returns:
            list: List of series dicts, or empty list on error
        """
        result = self._get("/series")
        return result or []

    def get_series_by_id(self, series_id):
        """Get a single series by ID."""
        return self._get(f"/series/{series_id}")

    def get_episodes(self, series_id):
        """Get all episodes for a series.

        Returns:
            list: List of episode dicts
        """
        result = self._get("/episode", params={"seriesId": series_id})
        return result or []

    def get_episode_by_id(self, episode_id):
        """Get a single episode by ID.

        Returns:
            dict: Episode info including episodeFileId and hasFile
        """
        return self._get(f"/episode/{episode_id}")

    def get_episode_file_path(self, episode_id):
        """Get the file path for a specific episode by episode ID.

        Looks up the episode, then fetches the episode file details.

        Returns:
            str or None: Full file path, or None if not found
        """
        episode = self.get_episode_by_id(episode_id)
        if not episode:
            return None

        # Try direct episodeFile.path first (Sonarr v3 often includes it)
        ep_file = episode.get("episodeFile")
        if ep_file and ep_file.get("path"):
            return ep_file["path"]

        # Fallback: get episodeFile separately
        file_id = episode.get("episodeFileId")
        if not file_id or file_id == 0:
            logger.debug("Episode %d has no file", episode_id)
            return None

        file_info = self.get_episode_file(file_id)
        if file_info and file_info.get("path"):
            return file_info["path"]

        return None

    def get_episode_file(self, episode_file_id):
        """Get file info for an episode file.

        Returns:
            dict: Episode file info including path
        """
        return self._get(f"/episodefile/{episode_file_id}")

    def get_tags(self):
        """Get all tags.

        Returns:
            list: List of tag dicts (id, label)
        """
        result = self._get("/tag")
        return result or []

    def get_anime_series(self, anime_tag="anime"):
        """Get series filtered by anime tag.

        Returns:
            list: List of anime series dicts
        """
        tags = self.get_tags()
        anime_tag_ids = [t["id"] for t in tags if t.get("label", "").lower() == anime_tag.lower()]

        if not anime_tag_ids:
            logger.warning("Sonarr: No '%s' tag found", anime_tag)
            return []

        all_series = self.get_series()
        anime_series = []
        for series in all_series:
            series_tags = series.get("tags", [])
            if any(tag_id in series_tags for tag_id in anime_tag_ids):
                anime_series.append(series)

        logger.info("Found %d anime series (tag: %s)", len(anime_series), anime_tag)
        return anime_series

    def rescan_series(self, series_id):
        """Trigger a RescanSeries command.

        Returns:
            bool: True if command was sent successfully
        """
        result = self._post("/command", data={
            "name": "RescanSeries",
            "seriesId": series_id,
        })
        if result is not None:
            logger.info("Triggered Sonarr RescanSeries for series %d", series_id)
            return True
        return False

    def get_library_info(self, anime_only=True):
        """Get library overview with subtitle status.

        Returns:
            list: Series with episode counts and file info
        """
        series_list = self.get_anime_series() if anime_only else self.get_series()
        result = []

        for series in series_list:
            result.append({
                "id": series.get("id"),
                "title": series.get("title"),
                "year": series.get("year"),
                "seasons": series.get("seasonCount", 0),
                "episodes": series.get("episodeCount", 0),
                "episodes_with_files": series.get("episodeFileCount", 0),
                "path": series.get("path"),
                "poster": series.get("images", [{}])[0].get("remoteUrl", "") if series.get("images") else "",
                "status": series.get("status"),
            })

        return result
