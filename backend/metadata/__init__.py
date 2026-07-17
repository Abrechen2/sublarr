"""Metadata package -- TMDB, AniList, and TVDB API clients with resolver.

MetadataResolver orchestrates lookups across all three providers with
caching via the metadata_cache DB table.
"""

import contextlib
import json
import logging

from metadata.anilist_client import AniListClient, get_anilist_client
from metadata.tmdb_client import TMDBClient
from metadata.tvdb_client import TVDBClient

logger = logging.getLogger(__name__)

TMDB_POSTER_BASE = "https://image.tmdb.org/t/p/w500"

# Stop a transient API outage from poisoning the cache for a full TTL.
# Filename-stub results carry no provider IDs and arise specifically when
# every upstream lookup failed (TMDB/TVDB/AniList all returned None or
# raised). Caching one would force a 30-day window of stub-quality data
# even after the upstream comes back online — instead we always re-try.
_FILENAME_STUB_SOURCE = "filename"


class MetadataResolver:
    """Orchestrates metadata lookups across TMDB, AniList, and TVDB.

    Lookup chain:
    - Anime: AniList first, then TMDB, then TVDB fallback
    - General: TMDB primary, TVDB fallback
    - Results are normalized to a consistent dict format
    - Caching via DB metadata_cache table (if available)
    """

    def __init__(self, tmdb_key: str = "", tvdb_key: str = "", tvdb_pin: str = ""):
        self._tmdb_key = tmdb_key
        self._tvdb_key = tvdb_key
        self._tvdb_pin = tvdb_pin
        self._tmdb_instance = None
        self._anilist_instance = None
        self._tvdb_instance = None

    @property
    def _tmdb(self) -> TMDBClient | None:
        """Lazy TMDB client creation. None if no API key provided."""
        if not self._tmdb_key:
            return None
        if self._tmdb_instance is None:
            self._tmdb_instance = TMDBClient(self._tmdb_key)
        return self._tmdb_instance

    @property
    def _anilist(self) -> AniListClient:
        """Process-wide AniList client (singleton). Always available (no key needed).

        Routed through get_anilist_client() so the shared 0.7s inter-request
        rate-lock actually spans every AniList consumer in the process —
        concurrent scanning + wanted-search must not jointly exceed AniList's
        90 req/min budget via two independently-rate-limited clients.
        """
        if self._anilist_instance is None:
            self._anilist_instance = get_anilist_client()
        return self._anilist_instance

    @property
    def _tvdb(self) -> TVDBClient | None:
        """Lazy TVDB client creation. None if no API key provided."""
        if not self._tvdb_key:
            return None
        if self._tvdb_instance is None:
            self._tvdb_instance = TVDBClient(self._tvdb_key, self._tvdb_pin)
        return self._tvdb_instance

    def _get_cached(self, cache_key: str) -> dict | None:
        """Try to get cached metadata from the ``metadata_cache`` table.

        Returns the deserialised result dict, or ``None`` when the entry is
        missing, expired, or the cache layer is unavailable. Silent on every
        failure so a broken cache never blocks a lookup.
        """
        try:
            from db.standalone import get_cached_metadata

            entry = get_cached_metadata(cache_key)
        except Exception:
            return None

        if not entry:
            return None
        raw = entry.get("response_json")
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            logger.debug("Cache entry for %s is not valid JSON; ignoring", cache_key)
            return None

    def _set_cached(self, cache_key: str, data: dict) -> None:
        """Persist a resolver result to ``metadata_cache``.

        Skips filename-stub results (see ``_FILENAME_STUB_SOURCE`` comment) so
        a transient API outage cannot poison the cache for the full TTL. All
        other failures (DB unreachable, JSON serialisation, etc.) are
        swallowed — caching is best-effort, not load-bearing.
        """
        if not isinstance(data, dict):
            return
        if data.get("metadata_source") == _FILENAME_STUB_SOURCE:
            return
        try:
            from db.standalone import cache_metadata

            cache_metadata(
                cache_key,
                provider=data.get("metadata_source", "resolver"),
                response_json=json.dumps(data, default=str),
                ttl_days=30,
            )
        except Exception:
            logger.debug("Cache write for %s failed; continuing without cache", cache_key)

    def resolve_series(self, title: str, year: int = None, is_anime: bool = False) -> dict:
        """Resolve metadata for a TV series using the lookup chain.

        Lookup order:
        1. Check DB cache
        2. If anime: AniList first
        3. TMDB primary (with external IDs for cross-reference)
        4. TVDB fallback
        5. Filename fallback if all fail

        Args:
            title: Series title to search for.
            year: Optional year filter.
            is_anime: If True, prioritize AniList lookup.

        Returns:
            Normalized metadata dict with title, year, IDs, poster_url, etc.
        """
        cache_key = f"series:{title.lower()}:{year or ''}"

        # Check cache first
        cached = self._get_cached(cache_key)
        if cached:
            logger.debug("Cache hit for %s", cache_key)
            return cached

        result = None

        # For anime, try AniList first
        if is_anime:
            result = self._try_anilist_series(title)
            if result:
                # Also try TMDB for cross-referencing IDs
                tmdb_result = self._try_tmdb_series(title, year)
                if tmdb_result:
                    result["tmdb_id"] = tmdb_result.get("tmdb_id")
                    result["tvdb_id"] = tmdb_result.get("tvdb_id")
                    result["imdb_id"] = tmdb_result.get("imdb_id") or result.get("imdb_id")

        # TMDB primary lookup
        if not result and self._tmdb:
            result = self._try_tmdb_series(title, year)

        # TVDB fallback
        if not result and self._tvdb:
            result = self._try_tvdb_series(title, year)

        # Filename fallback
        if not result:
            result = {
                "title": title,
                "year": year,
                "tmdb_id": None,
                "tvdb_id": None,
                "anilist_id": None,
                "imdb_id": None,
                "poster_url": None,
                "is_anime": is_anime,
                "episode_count": None,
                "season_count": None,
                "metadata_source": "filename",
            }

        # Cache and return
        self._set_cached(cache_key, result)
        return result

    def resolve_movie(self, title: str, year: int = None) -> dict:
        """Resolve metadata for a movie.

        Lookup order:
        1. Check DB cache
        2. TMDB search + details + external IDs
        3. Filename fallback if all fail

        Args:
            title: Movie title to search for.
            year: Optional year filter.

        Returns:
            Normalized metadata dict with title, year, IDs, poster_url, etc.
        """
        cache_key = f"movie:{title.lower()}:{year or ''}"

        # Check cache first
        cached = self._get_cached(cache_key)
        if cached:
            logger.debug("Cache hit for %s", cache_key)
            return cached

        result = None

        # TMDB primary lookup
        if self._tmdb:
            result = self._try_tmdb_movie(title, year)

        # Filename fallback
        if not result:
            result = {
                "title": title,
                "year": year,
                "tmdb_id": None,
                "imdb_id": None,
                "poster_url": None,
                "metadata_source": "filename",
            }

        # Cache and return
        self._set_cached(cache_key, result)
        return result

    def _try_anilist_series(self, title: str) -> dict | None:
        """Attempt AniList anime search and normalize result."""
        search_result = self._anilist.search_anime(title)
        if search_result:
            return self._normalize_anilist(search_result)
        return None

    def _try_tmdb_series(self, title: str, year: int = None) -> dict | None:
        """Attempt TMDB TV search with details and external IDs."""
        if not self._tmdb:
            return None
        search_result = self._tmdb.search_tv(title, year=year)
        if not search_result:
            return None

        tv_id = search_result.get("id")
        details = self._tmdb.get_tv_details(tv_id) if tv_id else None
        external_ids = self._tmdb.get_tv_external_ids(tv_id) if tv_id else None
        return self._normalize_tmdb_tv(search_result, details, external_ids)

    def _try_tvdb_series(self, title: str, year: int = None) -> dict | None:
        """Attempt TVDB series search and normalize result."""
        if not self._tvdb:
            return None
        search_result = self._tvdb.search_series(title, year=year)
        if search_result:
            return self._normalize_tvdb(search_result)
        return None

    def _try_tmdb_movie(self, title: str, year: int = None) -> dict | None:
        """Attempt TMDB movie search with details and external IDs."""
        if not self._tmdb:
            return None
        search_result = self._tmdb.search_movie(title, year=year)
        if not search_result:
            return None

        movie_id = search_result.get("id")
        details = self._tmdb.get_movie_details(movie_id) if movie_id else None
        external_ids = self._tmdb.get_movie_external_ids(movie_id) if movie_id else None
        return self._normalize_tmdb_movie(search_result, details, external_ids)

    def _normalize_tmdb_tv(
        self,
        search_result: dict,
        details: dict = None,
        external_ids: dict = None,
    ) -> dict:
        """Normalize TMDB TV search result to standard format."""
        poster_path = search_result.get("poster_path")
        poster_url = f"{TMDB_POSTER_BASE}{poster_path}" if poster_path else None

        result = {
            "title": search_result.get("name", ""),
            "year": None,
            "tmdb_id": search_result.get("id"),
            "tvdb_id": None,
            "anilist_id": None,
            "imdb_id": None,
            "poster_url": poster_url,
            "is_anime": False,
            "episode_count": None,
            "season_count": None,
            "metadata_source": "tmdb",
        }

        # Extract year from first_air_date
        first_air_date = search_result.get("first_air_date", "")
        if first_air_date and len(first_air_date) >= 4:
            with contextlib.suppress(ValueError):
                result["year"] = int(first_air_date[:4])

        # Enrich from details
        if details:
            result["season_count"] = details.get("number_of_seasons")
            result["episode_count"] = details.get("number_of_episodes")
            # Check genres for anime detection
            genres = [g.get("name", "").lower() for g in details.get("genres", [])]
            if "animation" in genres:
                origin = details.get("origin_country", [])
                if "JP" in origin:
                    result["is_anime"] = True

        # Enrich from external IDs
        if external_ids:
            result["tvdb_id"] = external_ids.get("tvdb_id")
            result["imdb_id"] = external_ids.get("imdb_id")

        return result

    def _normalize_anilist(self, result: dict) -> dict:
        """Normalize AniList search result to standard format."""
        title_obj = result.get("title", {})
        # Prefer English title, fall back to romaji
        title = title_obj.get("english") or title_obj.get("romaji") or ""

        cover = result.get("coverImage", {})
        poster_url = cover.get("large") if cover else None

        return {
            "title": title,
            "year": result.get("seasonYear"),
            "tmdb_id": None,
            "tvdb_id": None,
            "anilist_id": result.get("id"),
            "imdb_id": None,
            "poster_url": poster_url,
            "is_anime": True,
            "episode_count": result.get("episodes"),
            "season_count": None,
            "metadata_source": "anilist",
        }

    def _normalize_tvdb(self, result: dict) -> dict:
        """Normalize TVDB search result to standard format."""
        # TVDB search returns different field names
        tvdb_id = result.get("tvdb_id") or result.get("id")
        if isinstance(tvdb_id, str):
            try:
                tvdb_id = int(tvdb_id)
            except ValueError:
                tvdb_id = None

        year = result.get("year")
        if isinstance(year, str):
            try:
                year = int(year)
            except ValueError:
                year = None

        poster_url = result.get("image_url") or result.get("thumbnail")

        return {
            "title": result.get("name", ""),
            "year": year,
            "tmdb_id": None,
            "tvdb_id": tvdb_id,
            "anilist_id": None,
            "imdb_id": None,
            "poster_url": poster_url,
            "is_anime": False,
            "episode_count": None,
            "season_count": None,
            "metadata_source": "tvdb",
        }

    def _normalize_tmdb_movie(
        self,
        search_result: dict,
        details: dict = None,
        external_ids: dict = None,
    ) -> dict:
        """Normalize TMDB movie search result to standard format."""
        poster_path = search_result.get("poster_path")
        poster_url = f"{TMDB_POSTER_BASE}{poster_path}" if poster_path else None

        result = {
            "title": search_result.get("title", ""),
            "year": None,
            "tmdb_id": search_result.get("id"),
            "imdb_id": None,
            "poster_url": poster_url,
            "metadata_source": "tmdb",
        }

        # Extract year from release_date
        release_date = search_result.get("release_date", "")
        if release_date and len(release_date) >= 4:
            with contextlib.suppress(ValueError):
                result["year"] = int(release_date[:4])

        # Enrich from external IDs
        if external_ids:
            result["imdb_id"] = external_ids.get("imdb_id")

        return result
