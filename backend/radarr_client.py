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
_clients_cache = {}  # Cache for multi-instance clients: {instance_name: RadarrClient}


def get_radarr_client(instance_name=None):
    """Get or create a Radarr client. Returns None if not configured.

    Args:
        instance_name: Optional instance name. If None, uses first available instance or legacy config.

    Returns:
        RadarrClient instance or None
    """
    global _client, _clients_cache

    # If instance_name is specified, use multi-instance logic
    if instance_name is not None:
        if instance_name in _clients_cache:
            return _clients_cache[instance_name]

        from config import get_radarr_instances

        instances = get_radarr_instances()
        for inst in instances:
            if inst.get("name") == instance_name:
                client = RadarrClient(inst["url"], inst["api_key"])
                _clients_cache[instance_name] = client
                return client
        logger.warning("Radarr instance '%s' not found", instance_name)
        return None

    # Legacy singleton behavior (for backward compatibility)
    if _client is not None:
        return _client

    from config import get_radarr_instances

    instances = get_radarr_instances()
    if instances:
        # Use first instance
        inst = instances[0]
        _client = RadarrClient(inst["url"], inst["api_key"])
        return _client

    # Fallback to legacy config
    settings = get_settings()
    if not settings.radarr_url or not settings.radarr_api_key:
        logger.debug("Radarr not configured (radarr_url or radarr_api_key missing)")
        return None
    _client = RadarrClient(settings.radarr_url, settings.radarr_api_key)
    return _client


def invalidate_client():
    """Reset all client caches so the next call creates fresh instances."""
    global _client, _clients_cache
    _client = None
    _clients_cache = {}


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
                    logger.warning(
                        "Radarr GET %s rate limited (attempt %d), waiting %ds",
                        path,
                        attempt,
                        wait_seconds,
                    )
                    if attempt < MAX_RETRIES:
                        time.sleep(wait_seconds)
                        continue
                    else:
                        logger.error(
                            "Radarr GET %s rate limited after %d attempts", path, MAX_RETRIES
                        )
                        return None
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
                    logger.warning(
                        "Radarr POST %s rate limited (attempt %d), waiting %ds",
                        path,
                        attempt,
                        wait_seconds,
                    )
                    if attempt < MAX_RETRIES:
                        time.sleep(wait_seconds)
                        continue
                    else:
                        logger.error(
                            "Radarr POST %s rate limited after %d attempts", path, MAX_RETRIES
                        )
                        return None
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
        """Get movies filtered by anime tag OR 'Anime' genre.

        Returns:
            list: List of anime movie dicts
        """
        tags = self.get_tags()
        anime_tag_ids = set(
            t["id"] for t in tags if t.get("label", "").lower() == anime_tag.lower()
        )

        all_movies = self.get_movies()
        anime_movies = []
        for movie in all_movies:
            has_tag = anime_tag_ids and any(
                tag_id in anime_tag_ids for tag_id in movie.get("tags", [])
            )
            has_anime_genre = "anime" in [g.lower() for g in movie.get("genres", [])]
            if has_tag or has_anime_genre:
                anime_movies.append(movie)

        logger.info("Found %d anime movies (tag + genre)", len(anime_movies))
        return anime_movies

    def rescan_movie(self, movie_id):
        """Trigger a RescanMovie command.

        Returns:
            bool: True if command was sent successfully
        """
        result = self._post(
            "/command",
            data={
                "name": "RescanMovie",
                "movieId": movie_id,
            },
        )
        if result is not None:
            logger.info("Triggered Radarr RescanMovie for movie %d", movie_id)
            return True
        return False

    def get_movie_metadata(self, movie_id):
        """Get rich metadata for building a VideoQuery.

        Returns:
            dict: {title, year, imdb_id, tmdb_id, genres} or None on error
        """
        movie = self.get_movie_by_id(movie_id)
        if not movie:
            return None
        return {
            "title": movie.get("title", ""),
            "year": movie.get("year"),
            "imdb_id": movie.get("imdbId", ""),
            "tmdb_id": movie.get("tmdbId"),
            "genres": movie.get("genres", []),
        }

    def extended_health_check(self):
        """Extended diagnostic health check for Radarr.

        Returns a structured dict with connection status, API version info,
        library access, webhook status, and health issues. Each sub-query
        is wrapped in try/except for graceful degradation.

        Returns:
            dict with keys: connection, api_version, library_access,
                  webhook_status, health_issues
        """
        report = {
            "connection": {"healthy": False, "message": ""},
            "api_version": {"version": "", "branch": "", "app_name": ""},
            "library_access": {"movie_count": 0, "accessible": False},
            "webhook_status": {"configured": False, "sublarr_webhooks": []},
            "health_issues": [],
        }

        # 1. Connection + system status
        status = self._get("/system/status")
        if status is None:
            report["connection"]["message"] = f"Cannot connect to Radarr at {self.url}"
            return report

        report["connection"]["healthy"] = True
        report["connection"]["message"] = "OK"

        # 2. API version info
        report["api_version"]["version"] = status.get("version", "")
        report["api_version"]["branch"] = status.get("branch", "")
        report["api_version"]["app_name"] = status.get("appName", "")

        # 3. Library access
        try:
            movies = self._get("/movie")
            if movies is not None:
                report["library_access"]["accessible"] = True
                report["library_access"]["movie_count"] = len(movies)
        except Exception as exc:
            logger.debug("Extended health check: movie query failed: %s", exc)

        # 4. Webhook status
        try:
            notifications = self._get("/notification")
            if notifications is not None:
                report["webhook_status"]["configured"] = True
                for notif in notifications:
                    name = str(notif.get("name", "")).lower()
                    implementation = str(notif.get("implementation", "")).lower()
                    if "sublarr" in name or "sublarr" in implementation:
                        report["webhook_status"]["sublarr_webhooks"].append(
                            {
                                "name": notif.get("name", ""),
                                "implementation": notif.get("implementation", ""),
                            }
                        )
        except Exception as exc:
            logger.debug("Extended health check: notification query failed: %s", exc)

        # 5. Health issues
        try:
            health = self._get("/health")
            if health is not None:
                for item in health:
                    report["health_issues"].append(
                        {
                            "type": item.get("type", ""),
                            "message": item.get("message", ""),
                        }
                    )
        except Exception as exc:
            logger.debug("Extended health check: health query failed: %s", exc)

        return report

    def get_library_info(self, anime_only=True):
        """Get library overview for movies.

        Returns:
            list: Movies with file info
        """
        movies = self.get_anime_movies() if anime_only else self.get_movies()
        result = []

        for movie in movies:
            result.append(
                {
                    "id": movie.get("id"),
                    "title": movie.get("title"),
                    "year": movie.get("year"),
                    "has_file": movie.get("hasFile", False),
                    "path": movie.get("path"),
                    "poster": movie.get("images", [{}])[0].get("remoteUrl", "")
                    if movie.get("images")
                    else "",
                    "status": movie.get("status"),
                }
            )

        return result
