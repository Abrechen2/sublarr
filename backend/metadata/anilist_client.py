"""AniList GraphQL client for anime and manga metadata lookups.

Provides search and detail endpoints via the public AniList GraphQL API.
No API key required. Rate limited to 90 req/min (0.7s sleep between calls).
Returns None on errors (never crashes).
"""

import logging
import time

import requests

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15


class AniListClient:
    """AniList GraphQL API client."""

    ANILIST_URL = "https://graphql.anilist.co"

    SEARCH_QUERY = """
    query ($search: String, $type: MediaType) {
        Page(page: 1, perPage: 5) {
            media(search: $search, type: $type, sort: SEARCH_MATCH) {
                id
                idMal
                title {
                    romaji
                    english
                    native
                }
                format
                status
                episodes
                seasonYear
                coverImage {
                    large
                }
                genres
            }
        }
    }
    """

    DETAILS_QUERY = """
    query ($id: Int) {
        Media(id: $id) {
            id
            idMal
            title {
                romaji
                english
                native
            }
            format
            status
            episodes
            seasonYear
            coverImage {
                large
            }
            genres
            externalLinks {
                site
                url
            }
            relations {
                edges {
                    relationType
                    node {
                        id
                        title {
                            romaji
                            english
                        }
                        type
                        format
                    }
                }
            }
        }
    }
    """

    def __init__(self):
        self.session = requests.Session()
        self.session.headers["Content-Type"] = "application/json"
        self.session.headers["Accept"] = "application/json"
        self._last_request_time = 0.0

    def _query(self, query: str, variables: dict) -> dict | None:
        """Execute a GraphQL query with rate limiting.

        Enforces a minimum 0.7s gap between requests to stay within
        AniList's 90 req/min rate limit.

        Args:
            query: GraphQL query string.
            variables: Query variables dict.

        Returns:
            Response data dict or None on failure.
        """
        # Rate limiting: ensure at least 0.7s between requests
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < 0.7:
            time.sleep(0.7 - elapsed)

        try:
            resp = self.session.post(
                self.ANILIST_URL,
                json={"query": query, "variables": variables},
                timeout=REQUEST_TIMEOUT,
            )
            self._last_request_time = time.time()
            resp.raise_for_status()
            result = resp.json()
            if "errors" in result:
                logger.warning("AniList GraphQL errors: %s", result["errors"])
                return None
            return result.get("data")
        except requests.RequestException as e:
            logger.warning("AniList query failed: %s", e)
            self._last_request_time = time.time()
            return None

    def search_anime(self, title: str) -> dict | None:
        """Search for anime by title.

        Args:
            title: Anime title to search for.

        Returns:
            First matching media result dict or None.
        """
        data = self._query(self.SEARCH_QUERY, {"search": title, "type": "ANIME"})
        if data and data.get("Page", {}).get("media"):
            return data["Page"]["media"][0]
        return None

    def search_manga(self, title: str) -> dict | None:
        """Search for manga by title (useful for light novel adaptations).

        Args:
            title: Manga/light novel title to search for.

        Returns:
            First matching media result dict or None.
        """
        data = self._query(self.SEARCH_QUERY, {"search": title, "type": "MANGA"})
        if data and data.get("Page", {}).get("media"):
            return data["Page"]["media"][0]
        return None

    def get_details(self, anilist_id: int) -> dict | None:
        """Get full details for an AniList media entry.

        Args:
            anilist_id: AniList media ID.

        Returns:
            Full media details dict or None.
        """
        data = self._query(self.DETAILS_QUERY, {"id": anilist_id})
        if data and data.get("Media"):
            return data["Media"]
        return None
