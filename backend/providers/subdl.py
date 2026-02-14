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
            logger.debug("SubDL: no API key configured, skipping")
            return

        self.session = create_session(
            max_retries=2,
            backoff_factor=1.0,
            timeout=20,
            user_agent="Sublarr/1.0",
        )

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
            return []

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
                logger.debug("SubDL: insufficient search criteria")
                return []
            params["film_name"] = search_term

        results = []
        try:
            resp = self.session.get(API_BASE, params=params)
            if resp.status_code != 200:
                logger.warning("SubDL search failed: HTTP %d", resp.status_code)
                return []

            data = resp.json()
            if not data.get("status"):
                logger.debug("SubDL: API returned status=false")
                return []

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
                    },
                )
                results.append(result)

        except Exception as e:
            logger.error("SubDL search error: %s", e)

        logger.info("SubDL: found %d results", len(results))
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

        # Build a minimal query for file selection
        query = VideoQuery(
            episode=None,  # Will use metadata if available
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
