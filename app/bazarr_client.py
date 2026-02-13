"""Bazarr REST API client for subtitle management integration.

Provides graceful degradation: if Bazarr is unreachable, operations
return None/False without blocking the translation pipeline.
"""

import os
import time
import logging

import requests

logger = logging.getLogger(__name__)

BAZARR_URL = os.environ.get("BAZARR_URL", "")
BAZARR_API_KEY = os.environ.get("BAZARR_API_KEY", "")
REQUEST_TIMEOUT = 10
MAX_RETRIES = 3
BACKOFF_BASE = 2

_client = None


def get_bazarr_client():
    """Get or create the singleton Bazarr client. Returns None if not configured."""
    global _client
    if _client is not None:
        return _client
    if not BAZARR_URL or not BAZARR_API_KEY:
        logger.debug("Bazarr not configured (BAZARR_URL or BAZARR_API_KEY missing)")
        return None
    _client = BazarrClient(BAZARR_URL, BAZARR_API_KEY)
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
                "path": ep.get("path"),
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
        # Count anime-tagged from total
        total = data.get("total", 0)
        return total

    def get_episode_subs(self, episode_id):
        """Get subtitle info for a specific episode."""
        data = self._get("/api/episodes", params={"episodeid[]": episode_id})
        if not data or not data.get("data"):
            return None
        return data["data"][0]

    def search_german_ass(self, series_id, episode_id):
        """Search providers for a German ASS subtitle.

        Uses the manual search API to browse results and look for ASS format.
        Returns True if a German ASS was found and downloaded, False otherwise.
        """
        if not series_id or not episode_id:
            return False

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
            if lang_code != "de":
                continue

            # Check if ASS format (from release info or provider hints)
            release = (sub.get("release_info") or "").lower()
            if ".ass" not in release and "ass" not in release:
                continue

            logger.info(
                "Found German ASS from provider %s: %s",
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
                logger.error("Failed to download German ASS via Bazarr: %s", e)

        return False

    def fetch_english_srt(self, series_id, episode_id):
        """Ask Bazarr to download an English SRT for translation.

        Returns the path to the downloaded SRT file, or None.
        """
        if not series_id or not episode_id:
            return None

        try:
            resp = self.session.patch(
                f"{self.url}/api/episodes/subtitles",
                params={
                    "seriesid": series_id,
                    "episodeid": episode_id,
                    "language": "en",
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
                        if code in ("en", "eng"):
                            path = sub.get("path")
                            if path:
                                logger.info("Bazarr downloaded English SRT: %s", path)
                                return path
        except Exception as e:
            logger.error("Failed to fetch English SRT via Bazarr: %s", e)

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
