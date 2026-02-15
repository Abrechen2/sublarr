"""TMDB API v3 client for TV and movie metadata lookups.

Provides search and detail endpoints for TV series and movies using
Bearer token authentication. Returns None on errors (never crashes).
"""

import logging

import requests

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15


class TMDBClient:
    """TMDB (The Movie Database) API v3 client."""

    BASE_URL = "https://api.themoviedb.org"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {api_key}"
        self.session.headers["Accept"] = "application/json"

    def _get(self, path: str, params: dict = None) -> dict | None:
        """GET request helper. Returns parsed JSON or None on failure."""
        url = f"{self.BASE_URL}{path}"
        try:
            resp = self.session.get(url, params=params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.warning("TMDB GET %s failed: %s", path, e)
            return None

    def search_tv(self, query: str, year: int = None) -> dict | None:
        """Search for TV series by title.

        Args:
            query: Series title to search for.
            year: Optional first air date year filter.

        Returns:
            First matching result dict or None.
        """
        params = {"query": query, "language": "en-US", "page": 1}
        if year:
            params["first_air_date_year"] = year
        data = self._get("/3/search/tv", params=params)
        if data and data.get("results"):
            return data["results"][0]
        return None

    def search_movie(self, query: str, year: int = None) -> dict | None:
        """Search for a movie by title.

        Args:
            query: Movie title to search for.
            year: Optional release year filter.

        Returns:
            First matching result dict or None.
        """
        params = {"query": query, "language": "en-US", "page": 1}
        if year:
            params["year"] = year
        data = self._get("/3/search/movie", params=params)
        if data and data.get("results"):
            return data["results"][0]
        return None

    def get_tv_details(self, tv_id: int) -> dict | None:
        """Get full details for a TV series.

        Args:
            tv_id: TMDB TV series ID.

        Returns:
            Full details dict or None.
        """
        return self._get(f"/3/tv/{tv_id}", params={"language": "en-US"})

    def get_tv_external_ids(self, tv_id: int) -> dict | None:
        """Get external IDs (IMDB, TVDB, etc.) for a TV series.

        Args:
            tv_id: TMDB TV series ID.

        Returns:
            Dict with imdb_id, tvdb_id, etc. or None.
        """
        return self._get(f"/3/tv/{tv_id}/external_ids")

    def get_tv_season(self, tv_id: int, season_number: int) -> dict | None:
        """Get season details including episode list.

        Args:
            tv_id: TMDB TV series ID.
            season_number: Season number.

        Returns:
            Season dict with episodes list or None.
        """
        return self._get(
            f"/3/tv/{tv_id}/season/{season_number}",
            params={"language": "en-US"},
        )

    def get_movie_details(self, movie_id: int) -> dict | None:
        """Get full details for a movie.

        Args:
            movie_id: TMDB movie ID.

        Returns:
            Full details dict or None.
        """
        return self._get(f"/3/movie/{movie_id}", params={"language": "en-US"})

    def get_movie_external_ids(self, movie_id: int) -> dict | None:
        """Get external IDs for a movie.

        Args:
            movie_id: TMDB movie ID.

        Returns:
            Dict with imdb_id, etc. or None.
        """
        return self._get(f"/3/movie/{movie_id}/external_ids")
