"""TVDB API v4 client for TV series and movie metadata lookups.

Provides search and detail endpoints with JWT authentication.
Token is acquired automatically and refreshed when expired.
Returns None on errors (never crashes).
"""

import logging
import time

import requests

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15
TOKEN_VALIDITY_SECONDS = 24 * 60 * 60  # 24 hours


class TVDBClient:
    """TVDB (TheTVDB) API v4 client with JWT auth."""

    BASE_URL = "https://api4.thetvdb.com"

    def __init__(self, api_key: str, pin: str = ""):
        self.api_key = api_key
        self.pin = pin
        self.session = requests.Session()
        self.session.headers["Accept"] = "application/json"
        self._token = ""
        self._token_expires = 0.0

    def _ensure_auth(self) -> bool:
        """Authenticate with TVDB if token is missing or expired.

        Returns:
            True if authenticated, False on failure.
        """
        if self._token and time.time() < self._token_expires:
            return True

        try:
            resp = self.session.post(
                f"{self.BASE_URL}/v4/login",
                json={"apikey": self.api_key, "pin": self.pin},
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            token = data.get("data", {}).get("token", "")
            if not token:
                logger.warning("TVDB login returned no token")
                return False
            self._token = token
            self._token_expires = time.time() + TOKEN_VALIDITY_SECONDS
            self.session.headers["Authorization"] = f"Bearer {token}"
            logger.debug("TVDB authentication successful")
            return True
        except requests.RequestException as e:
            logger.warning("TVDB authentication failed: %s", e)
            return False

    def _get(self, path: str, params: dict = None) -> dict | None:
        """GET request helper with automatic authentication.

        Returns:
            Parsed JSON response or None on failure.
        """
        if not self._ensure_auth():
            return None
        url = f"{self.BASE_URL}{path}"
        try:
            resp = self.session.get(url, params=params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.warning("TVDB GET %s failed: %s", path, e)
            return None

    def search_series(self, query: str, year: int = None) -> dict | None:
        """Search for a TV series by title.

        Args:
            query: Series title to search for.
            year: Optional year filter.

        Returns:
            First matching result dict or None.
        """
        params = {"query": query, "type": "series"}
        if year:
            params["year"] = year
        data = self._get("/v4/search", params=params)
        if data and data.get("data"):
            return data["data"][0]
        return None

    def get_series(self, series_id: int) -> dict | None:
        """Get full details for a TV series.

        Args:
            series_id: TVDB series ID.

        Returns:
            Series data dict or None.
        """
        data = self._get(f"/v4/series/{series_id}")
        if data and data.get("data"):
            return data["data"]
        return None

    def get_series_episodes(self, series_id: int, page: int = 0) -> dict | None:
        """Get episodes for a TV series.

        Args:
            series_id: TVDB series ID.
            page: Page number (0-indexed).

        Returns:
            Episodes data dict or None.
        """
        data = self._get(
            f"/v4/series/{series_id}/episodes/default",
            params={"page": page},
        )
        if data and data.get("data"):
            return data["data"]
        return None

    def search_movie(self, query: str, year: int = None) -> dict | None:
        """Search for a movie by title.

        Args:
            query: Movie title to search for.
            year: Optional year filter.

        Returns:
            First matching result dict or None.
        """
        params = {"query": query, "type": "movie"}
        if year:
            params["year"] = year
        data = self._get("/v4/search", params=params)
        if data and data.get("data"):
            return data["data"][0]
        return None
