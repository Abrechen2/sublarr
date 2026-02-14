"""Radarr v3 API client for movie management.

Provides movie listing, file paths, tag filtering,
and RescanMovie commands after new subtitle files are created.
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


def get_radarr_client():
    """Get or create the singleton Radarr client. Returns None if not configured."""
    global _client
    if _client is not None:
        return _client
    settings = get_settings()
    if not settings.radarr_url or not settings.radarr_api_key:
        logger.debug("Radarr not configured (radarr_url or radarr_api_key missing)")
        return None
    _client = RadarrClient(settings.radarr_url, settings.radarr_api_key)
    return _client


def invalidate_client():
    """Reset the singleton so the next call to get_radarr_client() creates a fresh instance."""
    global _client
    _client = None


class RadarrClient:
    """Radarr v3 REST API Client."""

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
                logger.warning("Radarr GET %s failed (attempt %d): %s", path, attempt, e)
            except requests.Timeout:
                logger.warning("Radarr GET %s timed out (attempt %d)", path, attempt)
            except requests.HTTPError as e:
                logger.error("Radarr HTTP error on GET %s: %s", path, e)
                return None
            except Exception as e:
                logger.error("Radarr unexpected error on GET %s: %s", path, e)
                return None
            if attempt < MAX_RETRIES:
                time.sleep(BACKOFF_BASE * attempt)
        logger.error("Radarr GET %s failed after %d attempts", path, MAX_RETRIES)
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
                logger.warning("Radarr POST %s failed (attempt %d): %s", path, attempt, e)
            except requests.Timeout:
                logger.warning("Radarr POST %s timed out (attempt %d)", path, attempt)
            except Exception as e:
                logger.error("Radarr unexpected error on POST %s: %s", path, e)
                return None
            if attempt < MAX_RETRIES:
                time.sleep(BACKOFF_BASE * attempt)
        return None

    def health_check(self):
        """Check if Radarr is reachable.

        Returns:
            tuple: (is_healthy: bool, message: str)
        """
        result = self._get("/system/status")
        if result is not None:
            return True, "OK"
        return False, f"Cannot connect to Radarr at {self.url}"

    def get_movies(self):
        """Get all movies.

        Returns:
            list: List of movie dicts
        """
        result = self._get("/movie")
        return result or []

    def get_movie_by_id(self, movie_id):
        """Get a single movie by ID."""
        return self._get(f"/movie/{movie_id}")

    def get_movie_file(self, movie_file_id):
        """Get file info for a movie file.

        Returns:
            dict: Movie file info including path
        """
        return self._get(f"/moviefile/{movie_file_id}")

    def get_tags(self):
        """Get all tags.

        Returns:
            list: List of tag dicts (id, label)
        """
        result = self._get("/tag")
        return result or []

    def get_anime_movies(self, anime_tag="anime"):
        """Get movies filtered by anime tag.

        Returns:
            list: List of anime movie dicts
        """
        tags = self.get_tags()
        anime_tag_ids = [t["id"] for t in tags if t.get("label", "").lower() == anime_tag.lower()]

        if not anime_tag_ids:
            logger.warning("Radarr: No '%s' tag found", anime_tag)
            return []

        all_movies = self.get_movies()
        anime_movies = []
        for movie in all_movies:
            movie_tags = movie.get("tags", [])
            if any(tag_id in movie_tags for tag_id in anime_tag_ids):
                anime_movies.append(movie)

        logger.info("Found %d anime movies (tag: %s)", len(anime_movies), anime_tag)
        return anime_movies

    def rescan_movie(self, movie_id):
        """Trigger a RescanMovie command.

        Returns:
            bool: True if command was sent successfully
        """
        result = self._post("/command", data={
            "name": "RescanMovie",
            "movieId": movie_id,
        })
        if result is not None:
            logger.info("Triggered Radarr RescanMovie for movie %d", movie_id)
            return True
        return False

    def get_movie_metadata(self, movie_id):
        """Get rich metadata for building a VideoQuery.

        Returns:
            dict: {title, year, imdb_id} or None on error
        """
        movie = self.get_movie_by_id(movie_id)
        if not movie:
            return None
        return {
            "title": movie.get("title", ""),
            "year": movie.get("year"),
            "imdb_id": movie.get("imdbId", ""),
        }

    def get_library_info(self, anime_only=True):
        """Get library overview for movies.

        Returns:
            list: Movies with file info
        """
        movies = self.get_anime_movies() if anime_only else self.get_movies()
        result = []

        for movie in movies:
            result.append({
                "id": movie.get("id"),
                "title": movie.get("title"),
                "year": movie.get("year"),
                "has_file": movie.get("hasFile", False),
                "path": movie.get("path"),
                "poster": movie.get("images", [{}])[0].get("remoteUrl", "") if movie.get("images") else "",
                "status": movie.get("status"),
            })

        return result
