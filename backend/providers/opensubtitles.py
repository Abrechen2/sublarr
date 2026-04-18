"""OpenSubtitles.com REST API v2 provider.

Uses the new REST API (not the legacy XML-RPC). Requires an API key
from opensubtitles.com. Supports ASS format filtering.

API docs: https://opensubtitles.stoplight.io/docs/opensubtitles-api/
License: GPL-3.0
"""

import contextlib
import logging
import os
from typing import ClassVar

from werkzeug.utils import secure_filename as _secure_filename

from providers import _stream_download, register_provider
from providers.base import (
    ProviderError,
    ProviderRateLimitError,
    SubtitleProvider,
    SubtitleResult,
    VideoQuery,
)
from providers.http_session import create_session
from providers.opensubtitles_fetch import _OpenSubtitlesFetchMixin  # noqa: F401
from providers.opensubtitles_helpers import (  # noqa: F401 — re-exported for back-compat
    _FORMAT_MAP,
    _UPLOADER_RANK_BONUS,
    API_BASE,
    _compute_opensubtitles_hash,
)
from security_utils import validate_download_url

logger = logging.getLogger(__name__)


@register_provider
class OpenSubtitlesProvider(SubtitleProvider, _OpenSubtitlesFetchMixin):
    """OpenSubtitles.com REST API v2 provider."""

    name = "opensubtitles"

    # Free tier caps at 1000 downloads/day, 5 req/sec. VIP tiers are documented at
    # https://www.opensubtitles.com/vip — we cap a bit below the hard limit to
    # leave headroom for concurrent manual searches.
    rate_limits: ClassVar[dict[str, dict[str, int]]] = {
        "free": {"second": 5, "hour": 200, "day": 1000},
        "vip": {"second": 10, "hour": 1000, "day": 10000},
        "vip+": {"second": 20, "hour": 5000, "day": 100000},
    }
    languages = {
        "en",
        "de",
        "fr",
        "es",
        "it",
        "pt",
        "ru",
        "ja",
        "zh",
        "ko",
        "ar",
        "nl",
        "pl",
        "sv",
        "da",
        "no",
        "fi",
        "cs",
        "hu",
        "tr",
        "th",
        "vi",
        "id",
        "hi",
    }

    # Plugin system attributes
    config_fields = [
        {"key": "opensubtitles_api_key", "label": "API Key", "type": "password", "required": True},
        {"key": "opensubtitles_username", "label": "Username", "type": "text", "required": False},
        {
            "key": "opensubtitles_password",
            "label": "Password",
            "type": "password",
            "required": False,
        },
    ]
    rate_limit = (40, 10)
    timeout = 15
    max_retries = 3

    def __init__(self, api_key: str = "", username: str = "", password: str = "", **kwargs):
        super().__init__(**kwargs)
        self.api_key = api_key
        self.username = username
        self.password = password
        self.session = None
        self._token: str | None = None

    def initialize(self):
        if not self.api_key:
            logger.warning("OpenSubtitles: no API key configured, provider will be disabled")
            return

        logger.debug("OpenSubtitles: initializing with API key (length: %d)", len(self.api_key))
        self.session = create_session(
            max_retries=2,
            backoff_factor=1.0,
            timeout=15,
            user_agent="Sublarr v1.0",
        )
        self.session.headers.update(
            {
                "Api-Key": self.api_key,
                "Content-Type": "application/json",
            }
        )

        # Login if credentials provided (gives higher download limits)
        if self.username and self.password:
            logger.debug("OpenSubtitles: attempting login with username")
            self._login()
        else:
            logger.debug("OpenSubtitles: initialized without user login (using API key only)")

        # Detect active tier so the budget manager picks the right rate_limits
        # entry. Never let this break initialization — fall back to "free" on any
        # error (network, API change, etc.).
        try:
            self.tier = self.detect_tier()
        except Exception as e:
            logger.warning("OpenSubtitles: tier detection failed, defaulting to free: %s", e)
            self.tier = "free"

    def _login(self):
        """Authenticate to get a user token (higher rate limits)."""
        try:
            resp = self.session.post(
                f"{API_BASE}/login",
                json={
                    "username": self.username,
                    "password": self.password,
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                self._token = data.get("token")
                if self._token:
                    self.session.headers["Authorization"] = f"Bearer {self._token}"
                    logger.info("OpenSubtitles: logged in as %s", self.username)
            else:
                logger.warning("OpenSubtitles login failed: %s", resp.status_code)
        except Exception as e:
            logger.warning("OpenSubtitles login error: %s", e)

    def detect_tier(self, *, force: bool = False) -> str:
        """Query /api/v1/infos/user to determine the current account tier.

        Returns: 'free', 'vip', or 'vip+' — defaults to 'free' on any error.

        Caches the result on the instance; subsequent calls return the cached
        value unless ``force=True``. Call with ``force=True`` after an
        API-key change to re-detect the tier from the server.
        """
        if not force and hasattr(self, "_cached_tier"):
            return self._cached_tier

        try:
            resp = self.session.get(f"{API_BASE}/infos/user")
            if resp.status_code != 200:
                tier = "free"
            else:
                data = resp.json().get("data", {})
                if data.get("vip"):
                    tier = "vip+" if data.get("level", "").lower().startswith("vip+") else "vip"
                else:
                    tier = "free"
        except Exception as e:
            logger.warning("OpenSubtitles tier detection failed: %s", e)
            tier = "free"

        self._cached_tier = tier
        return tier

    def terminate(self):
        if self.session:
            # Logout if we have a token
            if self._token:
                with contextlib.suppress(Exception):
                    self.session.delete(f"{API_BASE}/logout")
            self.session.close()
            self.session = None
        # Drop cached tier so a fresh initialize() after a credentials change
        # re-detects from the server instead of reusing the stale value.
        if hasattr(self, "_cached_tier"):
            del self._cached_tier

    def health_check(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "API key not configured"
        if not self.session:
            return False, "Not initialized"
        try:
            resp = self.session.get(f"{API_BASE}/infos/user")
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                remaining = data.get("remaining_downloads", "?")
                return True, f"OK (downloads remaining: {remaining})"
            return False, f"HTTP {resp.status_code}"
        except Exception as e:
            return False, str(e)

    def search(self, query: VideoQuery) -> list[SubtitleResult]:
        if not self.session or not self.api_key:
            logger.warning(
                "OpenSubtitles: cannot search - session=%s, api_key=%s",
                self.session is not None,
                bool(self.api_key),
            )
            return []

        logger.debug(
            "OpenSubtitles: searching for %s (languages: %s)", query.display_name, query.languages
        )
        results = []

        # Build search params
        params = {}

        # Language filter
        if query.languages:
            params["languages"] = ",".join(query.languages)

        # Prefer hash match (most accurate)
        if query.file_path and os.path.exists(query.file_path):
            file_hash = query.file_hash or _compute_opensubtitles_hash(query.file_path)
            if file_hash:
                params["moviehash"] = file_hash

        # IMDB ID search
        if query.imdb_id:
            imdb_num = query.imdb_id.replace("tt", "")
            params["imdb_id"] = imdb_num

        # Episode search
        if query.is_episode:
            if not params.get("imdb_id") and not params.get("moviehash"):
                params["query"] = query.series_title
            if query.season is not None:
                params["season_number"] = query.season
            if query.episode is not None:
                params["episode_number"] = query.episode
        elif query.is_movie:
            if not params.get("imdb_id") and not params.get("moviehash"):
                params["query"] = query.title

        if not params.get("query") and not params.get("imdb_id") and not params.get("moviehash"):
            logger.warning("OpenSubtitles: insufficient search criteria - params: %s", params)
            return []

        logger.debug("OpenSubtitles: API request params: %s", params)
        results = self._fetch_and_parse(params, query)

        # Fallback 1: Season-1 collapse — OpenSubtitles indexes many anime series as a
        # single season while Sonarr tracks them as multiple seasons.  The uploaded
        # episode number stays the same (e.g. Sonarr S02E15 → OS S01E15, NOT S01Eabs).
        # The moviehash is stripped because the file hash never matches across seasons;
        # if there is no IMDB ID, a title query is added so the request stays valid.
        if (
            not results
            and query.is_episode
            and query.season is not None
            and query.season > 1
            and query.episode is not None
        ):
            # Strip hash (wrong for multi-season anime), keep IMDB if present
            fallback_params = {k: v for k, v in params.items() if k != "moviehash"}
            fallback_params.update({"season_number": 1, "episode_number": query.episode})
            # Ensure there is a search term when IMDB is also absent
            if not fallback_params.get("imdb_id") and not fallback_params.get("query"):
                if query.series_title:
                    fallback_params["query"] = query.series_title
            logger.debug(
                "OpenSubtitles: 0 results for S%02dE%02d — retrying with S01E%02d "
                "(season-1 collapse; params: %s)",
                query.season,
                query.episode,
                query.episode,
                fallback_params,
            )
            results = self._fetch_and_parse(fallback_params, query)
            if results:
                logger.info(
                    "OpenSubtitles: season-1 collapse found %d results for S01E%02d",
                    len(results),
                    query.episode,
                )

        # Fallback 2: Title search without IMDB — some uploaders do not link an IMDB ID.
        # If the primary search was IMDB-based and the season-1 collapse also found
        # nothing, retry with a pure title query (season=1, same episode) so that
        # un-linked entries are reachable (e.g. 86 EIGHTY-SIX, Vinland Saga S2).
        if (
            not results
            and query.is_episode
            and query.season is not None
            and query.season > 1
            and query.episode is not None
            and params.get("imdb_id")
            and query.series_title
        ):
            title_params: dict = {
                "query": query.series_title,
                "season_number": 1,
                "episode_number": query.episode,
            }
            if params.get("languages"):
                title_params["languages"] = params["languages"]
            logger.debug(
                "OpenSubtitles: IMDB+season-1 found nothing — retrying with title '%s' S01E%02d",
                query.series_title,
                query.episode,
            )
            results = self._fetch_and_parse(title_params, query)
            if results:
                logger.info(
                    "OpenSubtitles: title fallback found %d results for '%s' S01E%02d",
                    len(results),
                    query.series_title,
                    query.episode,
                )

        logger.info("OpenSubtitles: found %d results", len(results))
        if results:
            logger.debug(
                "OpenSubtitles: top result - %s (score: %d, format: %s, language: %s)",
                results[0].filename,
                results[0].score,
                results[0].format.value,
                results[0].language,
            )
        return results

    # _fetch_and_parse lives on _OpenSubtitlesFetchMixin (see opensubtitles_fetch.py).

    def download(self, result: SubtitleResult) -> bytes:
        if not self.session:
            raise ProviderError("OpenSubtitles not initialized")

        file_id = result.provider_data.get("file_id")
        if not file_id:
            raise ValueError("No file_id in provider_data")

        # Request download link
        resp = self.session.post(
            f"{API_BASE}/download",
            json={
                "file_id": file_id,
            },
        )

        if resp.status_code == 406:
            # 406 = daily download quota exhausted
            body = {}
            with contextlib.suppress(Exception):
                body = resp.json()
            remaining = body.get("remaining", "0")
            reset_time = body.get("reset_time_utc") or body.get("reset_time", "unknown")
            logger.warning(
                "OpenSubtitles: download quota exhausted (remaining=%s, resets=%s). "
                "Suppressing further downloads until reset.",
                remaining,
                reset_time,
            )
            raise ProviderRateLimitError(
                f"OpenSubtitles download quota exhausted (resets: {reset_time})"
            )

        if resp.status_code != 200:
            raise ProviderError(f"OpenSubtitles download request failed: HTTP {resp.status_code}")

        data = resp.json()
        download_link = data.get("link")
        if not download_link:
            raise ProviderError("No download link in response")

        # The /download response returns the actual file_name with extension (e.g. "Movie.de.ass").
        # The /subtitles search API omits the format field entirely for most entries, so this
        # is the only reliable place to detect the real format before saving.
        # P2: Sanitize provider-returned filename to prevent path traversal
        actual_filename = _secure_filename(data.get("file_name", ""))
        if actual_filename:
            ext = os.path.splitext(actual_filename)[1].lower().lstrip(".")
            if ext in _FORMAT_MAP:
                result.format = _FORMAT_MAP[ext]
                logger.debug(
                    "OpenSubtitles: format resolved from download filename: %s -> %s",
                    actual_filename,
                    result.format.value,
                )

        # P1: Validate download URL against allowed domains before fetching
        url_ok, url_err = validate_download_url(download_link, self.name)
        if not url_ok:
            raise ProviderError(f"OpenSubtitles download URL rejected: {url_err}")

        # Download the actual file (P5: 50 MB streaming cap)
        content = _stream_download(self.session, download_link, timeout=15)
        result.content = content
        logger.info("OpenSubtitles: downloaded %s (%d bytes)", result.filename, len(content))
        return content
