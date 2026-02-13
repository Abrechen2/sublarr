"""Bazarr REST API client for subtitle management integration.

Provides graceful degradation: if Bazarr is unreachable, operations
return None/False without blocking the translation pipeline.
All configuration is loaded from config.py Settings.
"""

import time
import logging

import requests

from config import get_settings

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 10
MAX_RETRIES = 3
BACKOFF_BASE = 2

_client = None


def get_bazarr_client():
    """Get or create the singleton Bazarr client. Returns None if not configured."""
    global _client
    if _client is not None:
        return _client
    settings = get_settings()
    if not settings.bazarr_url or not settings.bazarr_api_key:
        logger.debug("Bazarr not configured (bazarr_url or bazarr_api_key missing)")
        return None
    _client = BazarrClient(settings.bazarr_url, settings.bazarr_api_key)
    return _client


class BazarrClient:
    """Bazarr REST API Client."""

    def __init__(self, url, api_key):
        self.url = url.rstrip("/")
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers["X-API-KEY"] = api_key

    def _get(self, path, params=None, timeout=REQUEST_TIMEOUT):
        """GET request with retry logic."""
        url = f"{self.url}{path}"
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self.session.get(url, params=params, timeout=timeout)
                resp.raise_for_status()
                return resp.json()
            except requests.ConnectionError as e:
                logger.warning("Bazarr GET %s failed (attempt %d): %s", path, attempt, e)
            except requests.Timeout:
                logger.warning("Bazarr GET %s timed out (attempt %d)", path, attempt)
            except requests.HTTPError as e:
                logger.error("Bazarr HTTP error on GET %s: %s", path, e)
                return None
            except Exception as e:
                logger.error("Bazarr unexpected error on GET %s: %s", path, e)
                return None
            if attempt < MAX_RETRIES:
                time.sleep(BACKOFF_BASE * attempt)
        logger.error("Bazarr GET %s failed after %d attempts", path, MAX_RETRIES)
        return None

    def _patch(self, path, params=None, timeout=REQUEST_TIMEOUT):
        """PATCH request with retry logic."""
        url = f"{self.url}{path}"
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self.session.patch(url, params=params, timeout=timeout)
                resp.raise_for_status()
                return resp.json() if resp.content else {}
            except requests.ConnectionError as e:
                logger.warning("Bazarr PATCH %s failed (attempt %d): %s", path, attempt, e)
            except requests.Timeout:
                logger.warning("Bazarr PATCH %s timed out (attempt %d)", path, attempt)
            except Exception as e:
                logger.error("Bazarr unexpected error on PATCH %s: %s", path, e)
                return None
            if attempt < MAX_RETRIES:
                time.sleep(BACKOFF_BASE * attempt)
        return None

    def health_check(self):
        """Check if Bazarr is reachable.

        Returns:
            tuple: (is_healthy: bool, message: str)
        """
        result = self._get("/api/system/status")
        if result is not None:
            return True, "OK"
        return False, f"Cannot connect to Bazarr at {self.url}"

    def get_wanted_anime(self, limit=50):
        """Get anime episodes that are missing subtitles.

        Returns:
            list of dicts with episode info, filtered to anime tag only
        """
        data = self._get("/api/episodes/wanted", params={
            "start": 0,
            "length": limit,
        })
        if not data:
            return []

        episodes = []
        for ep in data.get("data", []):
            tags = ep.get("tags", [])
            if "anime" not in tags:
                continue

            episodes.append({
                "series_title": ep.get("seriesTitle"),
                "episode_number": ep.get("episode_number"),
                "episode_title": ep.get("episodeTitle"),
                "sonarr_series_id": ep.get("sonarrSeriesId"),
                "sonarr_episode_id": ep.get("sonarrEpisodeId"),
                "path": ep.get("path"),  # Note: Bazarr wanted API often doesn't include path
                "missing_subtitles": ep.get("missing_subtitles", []),
            })
        return episodes

    def get_wanted_anime_total(self):
        """Get total count of wanted anime episodes."""
        data = self._get("/api/episodes/wanted", params={
            "start": 0,
            "length": 1,
        })
        if not data:
            return 0
        total = data.get("total", 0)
        return total

    def get_episode_subs(self, episode_id):
        """Get subtitle info for a specific episode."""
        data = self._get("/api/episodes", params={"episodeid[]": episode_id})
        if not data or not data.get("data"):
            return None
        return data["data"][0]

    def search_target_ass(self, series_id, episode_id):
        """Search providers for a target language ASS subtitle.

        Uses the manual search API to browse results and look for ASS format.
        Returns True if found and downloaded, False otherwise.
        """
        if not series_id or not episode_id:
            return False

        settings = get_settings()
        target_lang = settings.target_language

        results = self._get(
            "/api/providers/episodes",
            params={"episodeid": episode_id},
            timeout=30,
        )

        if not results:
            return False

        for sub in results:
            # Check language
            lang = sub.get("language", "")
            if isinstance(lang, dict):
                lang_code = lang.get("code2", "")
            else:
                lang_code = str(lang)
            if lang_code != target_lang:
                continue

            # Check if ASS format (from release info or provider hints)
            release = (sub.get("release_info") or "").lower()
            if ".ass" not in release and "ass" not in release:
                continue

            logger.info(
                "Found target ASS from provider %s: %s",
                sub.get("provider"), release,
            )

            # Download it
            try:
                self.session.post(
                    f"{self.url}/api/providers/episodes",
                    params={
                        "seriesid": series_id,
                        "episodeid": episode_id,
                        "hi": str(sub.get("hearing_impaired", False)),
                        "forced": str(sub.get("forced", False)),
                        "original_format": "True",
                        "provider": sub.get("provider"),
                        "subtitle": sub.get("subtitle"),
                    },
                    timeout=30,
                )
                return True
            except Exception as e:
                logger.error("Failed to download target ASS via Bazarr: %s", e)

        return False

    def fetch_source_srt(self, series_id, episode_id):
        """Ask Bazarr to download a source language SRT for translation.

        Returns the path to the downloaded SRT file, or None.
        """
        if not series_id or not episode_id:
            return None

        settings = get_settings()
        source_lang = settings.source_language
        source_tags = settings.get_source_lang_tags()

        try:
            resp = self.session.patch(
                f"{self.url}/api/episodes/subtitles",
                params={
                    "seriesid": series_id,
                    "episodeid": episode_id,
                    "language": source_lang,
                    "forced": "False",
                    "hi": "False",
                },
                timeout=60,
            )
            if resp.status_code == 200:
                ep = self.get_episode_subs(episode_id)
                if ep:
                    for sub in ep.get("subtitles", []):
                        code = sub.get("code2") or sub.get("code3", "")
                        if code in source_tags:
                            path = sub.get("path")
                            if path:
                                logger.info("Bazarr downloaded source SRT: %s", path)
                                return path
        except Exception as e:
            logger.error("Failed to fetch source SRT via Bazarr: %s", e)

        return None

    def notify_scan_disk(self, series_id):
        """Notify Bazarr to scan disk for new subtitle files."""
        if not series_id:
            return False
        result = self._patch("/api/series", params={
            "seriesid": series_id,
            "action": "scan-disk",
        })
        if result is not None:
            logger.info("Notified Bazarr to scan disk for series %s", series_id)
            return True
        return False
