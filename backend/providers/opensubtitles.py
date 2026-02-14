"""OpenSubtitles.com REST API v2 provider.

Uses the new REST API (not the legacy XML-RPC). Requires an API key
from opensubtitles.com. Supports ASS format filtering.

API docs: https://opensubtitles.stoplight.io/docs/opensubtitles-api/
License: GPL-3.0
"""

import os
import logging
from typing import Optional

from providers.base import (
    SubtitleProvider,
    SubtitleResult,
    SubtitleFormat,
    VideoQuery,
    ProviderAuthError,
    ProviderRateLimitError,
)
from providers import register_provider
from providers.http_session import create_session

logger = logging.getLogger(__name__)

API_BASE = "https://api.opensubtitles.com/api/v1"

# Map common format strings to SubtitleFormat
_FORMAT_MAP = {
    "srt": SubtitleFormat.SRT,
    "ass": SubtitleFormat.ASS,
    "ssa": SubtitleFormat.SSA,
    "vtt": SubtitleFormat.VTT,
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
        "en", "de", "fr", "es", "it", "pt", "ru", "ja", "zh", "ko",
        "ar", "nl", "pl", "sv", "da", "no", "fi", "cs", "hu", "tr",
        "th", "vi", "id", "hi",
    }

    def __init__(self, api_key: str = "", username: str = "", password: str = "", **kwargs):
        super().__init__(**kwargs)
        self.api_key = api_key
        self.username = username
        self.password = password
        self.session = None
        self._token: Optional[str] = None

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
        self.session.headers.update({
            "Api-Key": self.api_key,
            "Content-Type": "application/json",
        })

        # Login if credentials provided (gives higher download limits)
        if self.username and self.password:
            logger.debug("OpenSubtitles: attempting login with username")
            self._login()
        else:
            logger.debug("OpenSubtitles: initialized without user login (using API key only)")

    def _login(self):
        """Authenticate to get a user token (higher rate limits)."""
        try:
            resp = self.session.post(f"{API_BASE}/login", json={
                "username": self.username,
                "password": self.password,
            })
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
                try:
                    self.session.delete(f"{API_BASE}/logout")
                except Exception:
                    pass
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
            logger.warning("OpenSubtitles: cannot search - session=%s, api_key=%s", 
                          self.session is not None, bool(self.api_key))
            return []

        logger.debug("OpenSubtitles: searching for %s (languages: %s)", 
                    query.display_name, query.languages)
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
        try:
            resp = self.session.get(f"{API_BASE}/subtitles", params=params)
            logger.debug("OpenSubtitles: API response status: %d", resp.status_code)
            
            if resp.status_code == 401 or resp.status_code == 403:
                error_msg = f"OpenSubtitles authentication failed: HTTP {resp.status_code}"
                logger.error(error_msg)
                raise ProviderAuthError(error_msg)
            
            if resp.status_code == 429:
                error_msg = f"OpenSubtitles rate limit exceeded: HTTP {resp.status_code}"
                logger.warning(error_msg)
                raise ProviderRateLimitError(error_msg)
            
            if resp.status_code != 200:
                logger.warning("OpenSubtitles search failed: HTTP %d, response: %s", 
                              resp.status_code, resp.text[:200])
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

                for f in files:
                    file_id = f.get("file_id")
                    filename = f.get("file_name", "")

                    # Detect format from filename
                    fmt = SubtitleFormat.UNKNOWN
                    ext = os.path.splitext(filename)[1].lower().lstrip(".")
                    fmt = _FORMAT_MAP.get(ext, SubtitleFormat.UNKNOWN)

                    # Build matches
                    matches = set()
                    if params.get("moviehash") and attrs.get("moviehash_match"):
                        matches.add("hash")
                    if query.is_episode:
                        if feature.get("season_number") == query.season:
                            matches.add("season")
                        if feature.get("episode_number") == query.episode:
                            matches.add("episode")
                        if query.series_title and query.series_title.lower() in (feature.get("title", "") or "").lower():
                            matches.add("series")
                    else:
                        if query.title and query.title.lower() in (feature.get("title", "") or "").lower():
                            matches.add("title")
                    if query.year and feature.get("year") == query.year:
                        matches.add("year")
                    if query.release_group and query.release_group.lower() in release.lower():
                        matches.add("release_group")

                    result = SubtitleResult(
                        provider_name=self.name,
                        subtitle_id=str(file_id),
                        language=lang,
                        format=fmt,
                        filename=filename,
                        release_info=release,
                        hearing_impaired=hi,
                        fps=fps if fps else None,
                        matches=matches,
                        provider_data={"file_id": file_id},
                    )
                    results.append(result)

        except Exception as e:
            logger.error("OpenSubtitles search error: %s", e, exc_info=True)

        logger.info("OpenSubtitles: found %d results", len(results))
        if results:
            logger.debug("OpenSubtitles: top result - %s (score: %d, format: %s, language: %s)",
                        results[0].filename, results[0].score, results[0].format.value, results[0].language)
        return results

    def download(self, result: SubtitleResult) -> bytes:
        if not self.session:
            raise RuntimeError("OpenSubtitles not initialized")

        file_id = result.provider_data.get("file_id")
        if not file_id:
            raise ValueError("No file_id in provider_data")

        # Request download link
        resp = self.session.post(f"{API_BASE}/download", json={
            "file_id": file_id,
        })

        if resp.status_code != 200:
            raise RuntimeError(f"OpenSubtitles download request failed: HTTP {resp.status_code}")

        data = resp.json()
        download_link = data.get("link")
        if not download_link:
            raise RuntimeError("No download link in response")

        # Download the actual file
        dl_resp = self.session.get(download_link)
        if dl_resp.status_code != 200:
            raise RuntimeError(f"OpenSubtitles file download failed: HTTP {dl_resp.status_code}")

        content = dl_resp.content
        result.content = content
        logger.info("OpenSubtitles: downloaded %s (%d bytes)", result.filename, len(content))
        return content
