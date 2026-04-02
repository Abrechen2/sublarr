"""OpenSubtitles.com REST API v2 provider.

Uses the new REST API (not the legacy XML-RPC). Requires an API key
from opensubtitles.com. Supports ASS format filtering.

API docs: https://opensubtitles.stoplight.io/docs/opensubtitles-api/
License: GPL-3.0
"""

import contextlib
import logging
import os

from werkzeug.utils import secure_filename as _secure_filename

from providers import _stream_download, register_provider
from providers.base import (
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
    SubtitleFormat,
    SubtitleProvider,
    SubtitleResult,
    VideoQuery,
)
from providers.http_session import create_session
from security_utils import validate_download_url

logger = logging.getLogger(__name__)

API_BASE = "https://api.opensubtitles.com/api/v1"

# Map common format strings to SubtitleFormat
_FORMAT_MAP = {
    "srt": SubtitleFormat.SRT,
    "ass": SubtitleFormat.ASS,
    "ssa": SubtitleFormat.SSA,
    "vtt": SubtitleFormat.VTT,
}

# Uploader rank to trust-bonus mapping (0-20 scale)
_UPLOADER_RANK_BONUS: dict[str, float] = {
    "administrator": 20.0,
    "platinum": 20.0,
    "gold": 15.0,
    "silver": 10.0,
    "bronze": 5.0,
    "trusted": 5.0,
}


def _compute_opensubtitles_hash(filepath: str) -> str:
    """Compute OpenSubtitles-style file hash.

    Based on first and last 64KB of the file + file size.
    """
    block_size = 65536
    file_size = os.path.getsize(filepath)

    if file_size < block_size * 2:
        return ""

    hash_val = file_size

    try:
        with open(filepath, "rb") as f:
            # First 64KB
            for _ in range(block_size // 8):
                buf = f.read(8)
                hash_val += int.from_bytes(buf, byteorder="little", signed=False)
                hash_val &= 0xFFFFFFFFFFFFFFFF

            # Last 64KB
            f.seek(-block_size, 2)
            for _ in range(block_size // 8):
                buf = f.read(8)
                hash_val += int.from_bytes(buf, byteorder="little", signed=False)
                hash_val &= 0xFFFFFFFFFFFFFFFF

        return f"{hash_val:016x}"
    except Exception:
        return ""


@register_provider
class OpenSubtitlesProvider(SubtitleProvider):
    """OpenSubtitles.com REST API v2 provider."""

    name = "opensubtitles"
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

    def terminate(self):
        if self.session:
            # Logout if we have a token
            if self._token:
                with contextlib.suppress(Exception):
                    self.session.delete(f"{API_BASE}/logout")
            self.session.close()
            self.session = None

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

    def _fetch_and_parse(self, params: dict, query: VideoQuery) -> list[SubtitleResult]:
        """Execute one OpenSubtitles /subtitles request and parse the response into results."""
        results: list[SubtitleResult] = []
        try:
            resp = self.session.get(f"{API_BASE}/subtitles", params=params)
            logger.debug("OpenSubtitles: API response status: %d", resp.status_code)

            if resp.status_code in (401, 403):
                error_msg = f"OpenSubtitles authentication failed: HTTP {resp.status_code}"
                logger.error(error_msg)
                raise ProviderAuthError(error_msg)

            if resp.status_code == 429:
                error_msg = f"OpenSubtitles rate limit exceeded: HTTP {resp.status_code}"
                logger.warning(error_msg)
                raise ProviderRateLimitError(error_msg)

            if resp.status_code != 200:
                logger.warning(
                    "OpenSubtitles search failed: HTTP %d, response: %s",
                    resp.status_code,
                    resp.text[:200],
                )
                return []

            data = resp.json()
            logger.debug("OpenSubtitles: API returned %d items", len(data.get("data", [])))
            for item in data.get("data", []):
                attrs = item.get("attributes", {})
                files = attrs.get("files", [])
                lang = attrs.get("language", "")
                release = attrs.get("release", "")
                hi = attrs.get("hearing_impaired", False)
                fps = attrs.get("fps", 0)
                feature = attrs.get("feature_details", {})

                uploader_info = attrs.get("uploader", {}) or {}
                uploader_name = uploader_info.get("name", "") or ""
                uploader_rank = (uploader_info.get("rank", "") or "").lower()
                uploader_trust = _UPLOADER_RANK_BONUS.get(uploader_rank, 0.0)

                is_forced = bool(attrs.get("foreign_parts_only", False))
                if query.forced_only and not is_forced:
                    continue
                if not query.forced_only and is_forced:
                    continue

                for f in files:
                    file_id = f.get("file_id")
                    # P2: Sanitize provider-returned filename to prevent path traversal
                    filename = _secure_filename(f.get("file_name", ""))

                    fmt = SubtitleFormat.UNKNOWN
                    ext = os.path.splitext(filename)[1].lower().lstrip(".")
                    if ext in _FORMAT_MAP:
                        fmt = _FORMAT_MAP[ext]
                    if fmt == SubtitleFormat.UNKNOWN:
                        api_fmt = attrs.get("format", "").lower()
                        fmt = _FORMAT_MAP.get(api_fmt, SubtitleFormat.UNKNOWN)

                    matches = set()
                    if params.get("moviehash") and attrs.get("moviehash_match"):
                        matches.add("hash")
                    if query.is_episode:
                        feat_season = feature.get("season_number")
                        feat_episode = feature.get("episode_number")
                        if feat_season == query.season:
                            matches.add("season")
                        if feat_episode == query.episode:
                            matches.add("episode")
                        # Season-1 collapse fallback: credit "episode" match when the
                        # API response episode number equals our absolute episode (covers
                        # edge cases where AniDB absolute happens to match OS episode).
                        if (
                            query.absolute_episode is not None
                            and feat_episode == query.absolute_episode
                        ):
                            matches.add("episode")
                        if (
                            query.series_title
                            and query.series_title.lower()
                            in (feature.get("title", "") or "").lower()
                        ):
                            matches.add("series")
                    else:
                        if (
                            query.title
                            and query.title.lower() in (feature.get("title", "") or "").lower()
                        ):
                            matches.add("title")
                    if query.year and feature.get("year") == query.year:
                        matches.add("year")
                    if query.release_group and query.release_group.lower() in release.lower():
                        matches.add("release_group")

                    results.append(
                        SubtitleResult(
                            provider_name=self.name,
                            subtitle_id=str(file_id),
                            language=lang,
                            format=fmt,
                            filename=filename,
                            release_info=release,
                            hearing_impaired=hi,
                            forced=is_forced,
                            fps=fps if fps else None,
                            matches=matches,
                            provider_data={"file_id": file_id, "foreign_parts_only": is_forced},
                            uploader_name=uploader_name,
                            uploader_trust=uploader_trust,
                        )
                    )

        except (ProviderAuthError, ProviderRateLimitError):
            raise
        except Exception as e:
            logger.error("OpenSubtitles search error: %s", e, exc_info=True)

        return results

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
