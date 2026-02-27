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
_clients_cache = {}  # Cache for multi-instance clients: {instance_name: SonarrClient}


def get_sonarr_client(instance_name=None):
    """Get or create a Sonarr client. Returns None if not configured.

    Args:
        instance_name: Optional instance name. If None, uses first available instance or legacy config.

    Returns:
        SonarrClient instance or None
    """
    global _client, _clients_cache

    # If instance_name is specified, use multi-instance logic
    if instance_name is not None:
        if instance_name in _clients_cache:
            return _clients_cache[instance_name]

        from config import get_sonarr_instances

        instances = get_sonarr_instances()
        for inst in instances:
            if inst.get("name") == instance_name:
                client = SonarrClient(inst["url"], inst["api_key"])
                _clients_cache[instance_name] = client
                return client
        logger.warning("Sonarr instance '%s' not found", instance_name)
        return None

    # Legacy singleton behavior (for backward compatibility)
    if _client is not None:
        return _client

    from config import get_sonarr_instances

    instances = get_sonarr_instances()
    if instances:
        # Use first instance
        inst = instances[0]
        _client = SonarrClient(inst["url"], inst["api_key"])
        return _client

    # Fallback to legacy config
    settings = get_settings()
    if not settings.sonarr_url or not settings.sonarr_api_key:
        logger.debug("Sonarr not configured (sonarr_url or sonarr_api_key missing)")
        return None
    _client = SonarrClient(settings.sonarr_url, settings.sonarr_api_key)
    return _client


def invalidate_client():
    """Reset all client caches so the next call creates fresh instances."""
    global _client, _clients_cache
    _client = None
    _clients_cache = {}


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
                        "Sonarr GET %s rate limited (attempt %d), waiting %ds",
                        path,
                        attempt,
                        wait_seconds,
                    )
                    if attempt < MAX_RETRIES:
                        time.sleep(wait_seconds)
                        continue
                    else:
                        logger.error(
                            "Sonarr GET %s rate limited after %d attempts", path, MAX_RETRIES
                        )
                        return None
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
                        "Sonarr POST %s rate limited (attempt %d), waiting %ds",
                        path,
                        attempt,
                        wait_seconds,
                    )
                    if attempt < MAX_RETRIES:
                        time.sleep(wait_seconds)
                        continue
                    else:
                        logger.error(
                            "Sonarr POST %s rate limited after %d attempts", path, MAX_RETRIES
                        )
                        return None
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

    def get_episode_files_by_series(self, series_id):
        """Get all episode files for a series in one request.

        Uses /episodefile?seriesId=X which returns full file info including path
        and mediaInfo. Much more efficient than fetching per-episode.

        Returns:
            dict: Mapping of episodeFileId -> file info dict (with path, mediaInfo)
        """
        result = self._get("/episodefile", params={"seriesId": series_id})
        files = result or []
        return {f["id"]: f for f in files if f.get("id")}

    def get_tags(self):
        """Get all tags.

        Returns:
            list: List of tag dicts (id, label)
        """
        result = self._get("/tag")
        return result or []

    def get_anime_series(self, anime_tag="anime"):
        """Get series filtered by anime tag, seriesType=anime, or 'Anime' genre.

        Returns:
            list: List of anime series dicts
        """
        tags = self.get_tags()
        anime_tag_ids = set(
            t["id"] for t in tags if t.get("label", "").lower() == anime_tag.lower()
        )

        all_series = self.get_series()
        anime_series = []
        for series in all_series:
            has_tag = anime_tag_ids and any(
                tag_id in anime_tag_ids for tag_id in series.get("tags", [])
            )
            is_anime_type = series.get("seriesType", "").lower() == "anime"
            has_anime_genre = "anime" in [g.lower() for g in series.get("genres", [])]
            if has_tag or is_anime_type or has_anime_genre:
                anime_series.append(series)

        logger.info("Found %d anime series (tag + seriesType + genre)", len(anime_series))
        return anime_series

    def rescan_series(self, series_id):
        """Trigger a RescanSeries command.

        Returns:
            bool: True if command was sent successfully
        """
        result = self._post(
            "/command",
            data={
                "name": "RescanSeries",
                "seriesId": series_id,
            },
        )
        if result is not None:
            logger.info("Triggered Sonarr RescanSeries for series %d", series_id)
            return True
        return False

    def get_episode_metadata(self, series_id, episode_id):
        """Get rich metadata for building a VideoQuery.

        Returns:
            dict: {series_title, season, episode, year, imdb_id, tvdb_id,
                   anidb_id, anilist_id, title}
            or None on error
        """
        series = self.get_series_by_id(series_id)
        if not series:
            return None
        episode = self.get_episode_by_id(episode_id)
        if not episode:
            return None

        # Extract AniDB ID using mapper service
        anidb_id = None
        tvdb_id = series.get("tvdbId")
        series_title = series.get("title", "")

        try:
            from anidb_mapper import get_anidb_id

            anidb_id = get_anidb_id(tvdb_id=tvdb_id, series_title=series_title, series=series)
        except Exception as e:
            logger.debug("Failed to resolve AniDB ID: %s", e)

        # Extract AniList ID from Custom Fields (if available)
        anilist_id = None
        custom_fields = series.get("customFields", {})
        if custom_fields:
            # Try various field name variations
            for field_name in ["anilist_id", "anilistId", "AniList", "AniList ID", "anilist"]:
                value = custom_fields.get(field_name)
                if value:
                    try:
                        anilist_id = int(value) if isinstance(value, (int, str)) else None
                        if anilist_id and anilist_id > 0:
                            break
                    except (ValueError, TypeError):
                        continue

        return {
            "series_title": series_title,
            "year": series.get("year"),
            "season": episode.get("seasonNumber"),
            "episode": episode.get("episodeNumber"),
            "title": episode.get("title", ""),
            "imdb_id": series.get("imdbId", ""),
            "tvdb_id": tvdb_id,
            "anidb_id": anidb_id,
            "anilist_id": anilist_id,
        }

    def extended_health_check(self):
        """Extended diagnostic health check for Sonarr.

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
            "library_access": {"series_count": 0, "accessible": False},
            "webhook_status": {"configured": False, "sublarr_webhooks": []},
            "health_issues": [],
        }

        # 1. Connection + system status
        status = self._get("/system/status")
        if status is None:
            report["connection"]["message"] = f"Cannot connect to Sonarr at {self.url}"
            return report

        report["connection"]["healthy"] = True
        report["connection"]["message"] = "OK"

        # 2. API version info
        report["api_version"]["version"] = status.get("version", "")
        report["api_version"]["branch"] = status.get("branch", "")
        report["api_version"]["app_name"] = status.get("appName", "")

        # 3. Library access
        try:
            series = self._get("/series")
            if series is not None:
                report["library_access"]["accessible"] = True
                report["library_access"]["series_count"] = len(series)
        except Exception as exc:
            logger.debug("Extended health check: series query failed: %s", exc)

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
        """Get library overview with subtitle status.

        Returns:
            list: Series with episode counts and file info
        """
        series_list = self.get_anime_series() if anime_only else self.get_series()
        result = []

        for series in series_list:
            # Sonarr v3 nests counts under "statistics"
            stats = series.get("statistics", {})
            result.append(
                {
                    "id": series.get("id"),
                    "title": series.get("title"),
                    "year": series.get("year"),
                    "seasons": stats.get("seasonCount", series.get("seasonCount", 0)),
                    "episodes": stats.get("episodeCount", series.get("episodeCount", 0)),
                    "episodes_with_files": stats.get(
                        "episodeFileCount", series.get("episodeFileCount", 0)
                    ),
                    "path": series.get("path"),
                    "poster": series.get("images", [{}])[0].get("remoteUrl", "")
                    if series.get("images")
                    else "",
                    "status": series.get("status"),
                }
            )

        return result
