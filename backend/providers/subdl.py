"""SubDL subtitle provider — Subscene successor.

SubDL provides broad subtitle coverage with a REST API. Supports
search by IMDB/TMDB ID and text queries. Downloads are ZIP archives.

API docs: https://subdl.com/api-doc
Rate limit: 2000 downloads/day
License: GPL-3.0
"""

import io
import os
import re
import zipfile
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

API_BASE = "https://api.subdl.com/api/v1/subtitles"
DOWNLOAD_BASE = "https://dl.subdl.com/subtitle"

_SUBTITLE_EXTENSIONS = {".ass", ".srt", ".ssa", ".vtt"}

_FORMAT_MAP = {
    ".ass": SubtitleFormat.ASS,
    ".ssa": SubtitleFormat.SSA,
    ".srt": SubtitleFormat.SRT,
    ".vtt": SubtitleFormat.VTT,
}

# Regex to extract release group from release name (e.g. "[SubGroup] Title" or "Title-SubGroup")
_RELEASE_GROUP_RE = re.compile(
    r"^\[([^\]]+)\]|[-.]([A-Za-z0-9]+)$"
)

# Episode number extraction from release name
_EPISODE_RE = re.compile(
    r"(?:S\d{1,2}E|E|EP|Episode[.\s_]?)(\d{1,3})\b", re.IGNORECASE
)


def _extract_from_zip(archive_content: bytes) -> list[tuple[str, bytes]]:
    """Extract subtitle files from a ZIP archive.

    Returns list of (filename, content) tuples.
    """
    results = []
    try:
        with zipfile.ZipFile(io.BytesIO(archive_content)) as zf:
            for name in zf.namelist():
                ext = os.path.splitext(name)[1].lower()
                if ext not in _SUBTITLE_EXTENSIONS:
                    continue
                if name.endswith("/"):
                    continue
                content = zf.read(name)
                results.append((os.path.basename(name), content))
    except zipfile.BadZipFile:
        logger.warning("SubDL: bad ZIP archive")
    return results


def _pick_best_subtitle(files: list[tuple[str, bytes]], query: VideoQuery) -> Optional[tuple[str, bytes]]:
    """Pick the best subtitle file from an extracted archive.

    Prefers ASS over SRT, and matches episode number if available.
    """
    if not files:
        return None

    scored = []
    for filename, content in files:
        score = 0
        ext = os.path.splitext(filename)[1].lower()

        # Format preference
        if ext == ".ass":
            score += 100
        elif ext == ".srt":
            score += 50

        # Episode number match
        if query.episode is not None:
            ep_str = f"{query.episode:02d}"
            name_lower = filename.lower()
            ep_patterns = [
                f"e{ep_str}", f"ep{ep_str}", f"_{ep_str}_", f"- {ep_str}",
                f" {ep_str} ", f"_{ep_str}.", f" {ep_str}.",
            ]
            for pattern in ep_patterns:
                if pattern in name_lower:
                    score += 200
                    break

        scored.append((filename, content, score))

    scored.sort(key=lambda x: x[2], reverse=True)
    return scored[0][0], scored[0][1]


def _parse_release_group(release_name: str) -> str:
    """Extract release group from a release name."""
    m = _RELEASE_GROUP_RE.search(release_name)
    if m:
        return m.group(1) or m.group(2) or ""
    return ""


@register_provider
class SubDLProvider(SubtitleProvider):
    """SubDL subtitle provider (Subscene successor)."""

    name = "subdl"
    languages = {
        "en", "de", "fr", "es", "it", "pt", "ru", "ja", "zh", "ko",
        "ar", "nl", "pl", "sv", "da", "no", "fi", "cs", "hu", "tr",
        "th", "vi", "id", "hi", "ms", "ro", "bg", "hr", "el", "he",
        "uk", "sk", "sl", "sr", "lt", "lv", "et", "fa", "bn", "ta",
        "te", "ml", "kn", "mr", "gu", "ur", "my", "km", "lo",
    }

    def __init__(self, api_key: str = "", **kwargs):
        super().__init__(**kwargs)
        self.api_key = api_key
        self.session = None

    def initialize(self):
        if not self.api_key:
            logger.warning("SubDL: no API key configured, provider will be disabled")
            return

        logger.debug("SubDL: initializing with API key (length: %d)", len(self.api_key))
        self.session = create_session(
            max_retries=2,
            backoff_factor=1.0,
            timeout=20,
            user_agent="Sublarr/1.0",
        )
        logger.debug("SubDL: session created successfully")

    def terminate(self):
        if self.session:
            self.session.close()
            self.session = None

    def health_check(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "API key not configured"
        if not self.session:
            return False, "Not initialized"
        try:
            resp = self.session.get(API_BASE, params={
                "api_key": self.api_key,
                "film_name": "test",
                "subs_per_page": 1,
            })
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status"):
                    return True, "OK"
                return False, data.get("error", "Unknown error")
            if resp.status_code == 401:
                return False, "Invalid API key"
            return False, f"HTTP {resp.status_code}"
        except Exception as e:
            return False, str(e)

    def search(self, query: VideoQuery) -> list[SubtitleResult]:
        if not self.session or not self.api_key:
            logger.warning("SubDL: cannot search - session=%s, api_key=%s", 
                          self.session is not None, bool(self.api_key))
            return []

        logger.debug("SubDL: searching for %s (languages: %s)", 
                    query.display_name, query.languages)
        params = {
            "api_key": self.api_key,
            "subs_per_page": 30,
        }

        # Language filter
        if query.languages:
            params["languages"] = ",".join(query.languages)

        # Search by IMDB ID (most accurate)
        if query.imdb_id:
            params["imdb_id"] = query.imdb_id

        # Type filter
        if query.is_episode:
            params["type"] = "tv"
            if query.season is not None:
                params["season_number"] = query.season
            if query.episode is not None:
                params["episode_number"] = query.episode
        elif query.is_movie:
            params["type"] = "movie"

        # Fallback to text search if no IMDB ID
        if not query.imdb_id:
            search_term = query.series_title or query.title
            if not search_term:
                logger.warning("SubDL: insufficient search criteria - no IMDB ID and no title")
                return []
            params["film_name"] = search_term

        logger.debug("SubDL: API request params: %s", {k: v for k, v in params.items() if k != "api_key"})
        results = []
        try:
            resp = self.session.get(API_BASE, params=params)
            logger.debug("SubDL: API response status: %d", resp.status_code)
            
            if resp.status_code == 401 or resp.status_code == 403:
                error_msg = f"SubDL authentication failed: HTTP {resp.status_code}"
                logger.error(error_msg)
                raise ProviderAuthError(error_msg)
            
            if resp.status_code == 429:
                error_msg = f"SubDL rate limit exceeded: HTTP {resp.status_code}"
                logger.warning(error_msg)
                raise ProviderRateLimitError(error_msg)
            
            if resp.status_code != 200:
                logger.warning("SubDL search failed: HTTP %d, response: %s", 
                              resp.status_code, resp.text[:200])
                return []

            data = resp.json()
            if not data.get("status"):
                error_msg = data.get("error", "Unknown error")
                logger.warning("SubDL: API returned status=false, error: %s", error_msg)
                return []
            
            logger.debug("SubDL: API returned %d subtitles", len(data.get("subtitles", [])))

            for sub in data.get("subtitles", []):
                sd_id = sub.get("sd_id", "")
                release_name = sub.get("release_name", "")
                subtitle_name = sub.get("name", "")
                lang = sub.get("lang", "")
                sub_season = sub.get("season")
                sub_episode = sub.get("episode")

                # Detect format from subtitle name
                fmt = SubtitleFormat.UNKNOWN
                ext = os.path.splitext(subtitle_name)[1].lower()
                fmt = _FORMAT_MAP.get(ext, SubtitleFormat.UNKNOWN)

                # Build matches for scoring
                matches = set()

                # IMDB match → series match
                if query.imdb_id and params.get("imdb_id"):
                    matches.add("series" if query.is_episode else "title")

                # Season/Episode match (only if SubDL returns non-zero values)
                if query.is_episode:
                    if sub_season and sub_season > 0 and sub_season == query.season:
                        matches.add("season")
                    if sub_episode and sub_episode > 0 and sub_episode == query.episode:
                        matches.add("episode")
                    elif query.episode is not None:
                        # Fallback: parse episode from release_name
                        ep_match = _EPISODE_RE.search(release_name)
                        if ep_match and int(ep_match.group(1)) == query.episode:
                            matches.add("episode")

                # Year match (for movies)
                if query.year and sub.get("year") == query.year:
                    matches.add("year")

                # Release group match
                sub_group = _parse_release_group(release_name)
                if sub_group and query.release_group:
                    if sub_group.lower() == query.release_group.lower():
                        matches.add("release_group")

                download_url = f"{DOWNLOAD_BASE}/{sd_id}.zip" if sd_id else ""

                result = SubtitleResult(
                    provider_name=self.name,
                    subtitle_id=str(sd_id),
                    language=lang,
                    format=fmt,
                    filename=subtitle_name,
                    download_url=download_url,
                    release_info=release_name,
                    matches=matches,
                    provider_data={
                        "sd_id": sd_id,
                        "query_episode": query.episode,
                        "query_season": query.season,
                    },
                )
                results.append(result)

        except Exception as e:
            logger.error("SubDL search error: %s", e, exc_info=True)

        logger.info("SubDL: found %d results", len(results))
        if results:
            logger.debug("SubDL: top result - %s (score: %d, format: %s, language: %s)",
                        results[0].filename, results[0].score, results[0].format.value, results[0].language)
        return results

    def download(self, result: SubtitleResult) -> bytes:
        if not self.session:
            raise RuntimeError("SubDL not initialized")

        sd_id = result.provider_data.get("sd_id")
        if not sd_id:
            raise ValueError("No sd_id in provider_data")

        url = f"{DOWNLOAD_BASE}/{sd_id}.zip"
        resp = self.session.get(url)
        if resp.status_code != 200:
            raise RuntimeError(f"SubDL download failed: HTTP {resp.status_code}")

        archive_content = resp.content

        # Extract subtitle files from ZIP
        extracted = _extract_from_zip(archive_content)
        if not extracted:
            raise RuntimeError("No subtitle files found in SubDL ZIP archive")

        # Build query with episode context for correct archive file selection
        query = VideoQuery(
            episode=result.provider_data.get("query_episode"),
            season=result.provider_data.get("query_season"),
        )

        # Pick the best file
        best = _pick_best_subtitle(extracted, query)
        if not best:
            raise RuntimeError("Could not select best subtitle from archive")

        best_name, best_content = best

        # Update result metadata with actual file info
        result.filename = best_name
        ext = os.path.splitext(best_name)[1].lower()
        result.format = _FORMAT_MAP.get(ext, SubtitleFormat.UNKNOWN)

        result.content = best_content
        logger.info("SubDL: downloaded %s (%d bytes)", result.filename, len(best_content))
        return best_content
