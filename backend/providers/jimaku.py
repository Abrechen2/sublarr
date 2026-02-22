"""Jimaku (jimaku.cc) subtitle provider — anime-focused.

Jimaku is the spiritual successor to Kitsunekko, focused on Japanese
anime subtitles. Supports AniList ID lookup and ZIP/RAR archive handling.

Architecture adapted from Bazarr's subliminal_patch jimaku provider (GPL-3.0).
API: https://jimaku.cc/api/docs
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

API_BASE = "https://jimaku.cc/api"

# Supported archive and subtitle extensions
_SUBTITLE_EXTENSIONS = {".ass", ".srt", ".ssa", ".vtt"}
_ARCHIVE_EXTENSIONS = {".zip", ".rar"}

_FORMAT_MAP = {
    ".ass": SubtitleFormat.ASS,
    ".ssa": SubtitleFormat.SSA,
    ".srt": SubtitleFormat.SRT,
    ".vtt": SubtitleFormat.VTT,
}


def _extract_from_zip(archive_content: bytes, query: VideoQuery) -> list[tuple[str, bytes]]:
    """Extract subtitle files from a ZIP archive.

    Returns list of (filename, content) tuples, filtered to best matches.
    """
    results = []
    try:
        with zipfile.ZipFile(io.BytesIO(archive_content)) as zf:
            for name in zf.namelist():
                ext = os.path.splitext(name)[1].lower()
                if ext not in _SUBTITLE_EXTENSIONS:
                    continue
                # Skip directories
                if name.endswith("/"):
                    continue
                content = zf.read(name)
                results.append((os.path.basename(name), content))
    except zipfile.BadZipFile:
        logger.warning("Jimaku: bad ZIP archive")
    return results


def _extract_from_rar(archive_content: bytes, query: VideoQuery) -> list[tuple[str, bytes]]:
    """Extract subtitle files from a RAR archive."""
    results = []
    try:
        import rarfile
        with rarfile.RarFile(io.BytesIO(archive_content)) as rf:
            for name in rf.namelist():
                ext = os.path.splitext(name)[1].lower()
                if ext not in _SUBTITLE_EXTENSIONS:
                    continue
                content = rf.read(name)
                results.append((os.path.basename(name), content))
    except ImportError:
        logger.warning("Jimaku: rarfile not installed, cannot extract RAR archives")
    except Exception as e:
        logger.warning("Jimaku: RAR extraction failed: %s", e)
    return results


def _score_subtitle_file(filename: str, query: VideoQuery) -> int:
    """Score a subtitle file name for relevance to the query.

    When query.absolute_episode is set it takes priority over season/episode
    for file scoring (Jimaku anime content often uses absolute numbering).
    """
    score = 0
    name_lower = filename.lower()

    # Format preference: ASS > SRT
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".ass":
        score += 100
    elif ext == ".srt":
        score += 50

    # Prefer AniDB absolute episode when available
    effective_episode = (
        query.absolute_episode
        if query.absolute_episode is not None
        else query.episode
    )

    # Episode number match
    if effective_episode is not None:
        ep_str = f"{effective_episode:02d}"
        # Match patterns like E01, EP01, _01_, - 01
        ep_patterns = [
            f"e{ep_str}", f"ep{ep_str}", f"_{ep_str}_", f"- {ep_str}",
            f" {ep_str} ", f"_{ep_str}.", f" {ep_str}.",
        ]
        for pattern in ep_patterns:
            if pattern in name_lower:
                score += 200
                break

    # Season match (skip when using absolute episode — absolute = no seasons)
    if query.absolute_episode is None and query.season is not None:
        s_str = f"s{query.season:02d}"
        if s_str in name_lower:
            score += 50

    return score


@register_provider
class JimakuProvider(SubtitleProvider):
    """Jimaku anime subtitle provider."""

    name = "jimaku"
    languages = {"ja", "en"}  # Primarily Japanese subtitles

    # Plugin system attributes
    config_fields = [
        {"key": "jimaku_api_key", "label": "API Key", "type": "password", "required": True},
    ]
    rate_limit = (100, 60)
    timeout = 30
    max_retries = 2

    def __init__(self, api_key: str = "", **kwargs):
        super().__init__(**kwargs)
        self.api_key = api_key
        self.session = None

    def initialize(self):
        if not self.api_key:
            logger.warning("Jimaku: no API key configured, provider will be disabled")
            return

        logger.debug("Jimaku: initializing with API key (length: %d)", len(self.api_key))
        self.session = create_session(
            max_retries=2,
            backoff_factor=2.0,
            timeout=20,
            user_agent="Sublarr/1.0",
        )
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
        })
        logger.debug("Jimaku: session created successfully")

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
            # Simple API test — search for a known anime
            resp = self.session.get(f"{API_BASE}/entries/search", params={"query": "test"})
            if resp.status_code == 200:
                return True, "OK"
            if resp.status_code == 401:
                return False, "Invalid API key"
            return False, f"HTTP {resp.status_code}"
        except Exception as e:
            return False, str(e)

    def search(self, query: VideoQuery) -> list[SubtitleResult]:
        if not self.session or not self.api_key:
            logger.warning("Jimaku: cannot search - session=%s, api_key=%s",
                          self.session is not None, bool(self.api_key))
            return []

        logger.debug("Jimaku: searching for %s (languages: %s)",
                    query.display_name, query.languages)

        # Prefer AniDB absolute episode when available — Jimaku uses AniDB IDs
        # and anime releases typically use absolute numbering in filenames.
        effective_episode = (
            query.absolute_episode
            if query.absolute_episode is not None
            else query.episode
        )
        if query.absolute_episode is not None:
            logger.debug(
                "Jimaku: using AniDB absolute episode %d (S%02dE%02d original)",
                query.absolute_episode,
                query.season or 0,
                query.episode or 0,
            )

        results = []

        # Search by AniList ID (most accurate for anime)
        entries = []
        if query.anilist_id:
            logger.debug("Jimaku: searching by AniList ID: %d", query.anilist_id)
            entries = self._search_by_anilist(query.anilist_id)

        # Fallback: search by name
        if not entries:
            search_term = query.series_title or query.title
            if search_term:
                logger.debug("Jimaku: searching by name: %s", search_term)
                entries = self._search_by_name(search_term)
            else:
                logger.warning("Jimaku: insufficient search criteria - no AniList ID and no title")

        if not entries:
            logger.debug("Jimaku: no entries found")
            return []
        
        logger.debug("Jimaku: found %d entries", len(entries))

        # For each entry, get available subtitle files
        for entry in entries[:5]:  # Limit to top 5 entries
            entry_id = entry.get("id")
            if not entry_id:
                continue

            files = self._get_entry_files(entry_id, query)
            for filename, download_url, is_archive in files:
                ext = os.path.splitext(filename)[1].lower()
                fmt = _FORMAT_MAP.get(ext, SubtitleFormat.UNKNOWN)

                # Detect language from filename
                lang = self._detect_language(filename)

                # Check if language matches query
                if query.languages and lang not in query.languages:
                    continue

                matches = set()
                if query.series_title and query.series_title.lower() in entry.get("name", "").lower():
                    matches.add("series")
                if query.anilist_id and entry.get("anilist_id") == query.anilist_id:
                    matches.add("series")

                result = SubtitleResult(
                    provider_name=self.name,
                    subtitle_id=f"{entry_id}:{filename}",
                    language=lang,
                    format=fmt,
                    filename=filename,
                    download_url=download_url,
                    release_info=entry.get("name", ""),
                    matches=matches,
                    provider_data={
                        "entry_id": entry_id,
                        "is_archive": is_archive,
                        "entry_name": entry.get("name", ""),
                        # Use absolute episode as effective episode for archive scoring
                        "query_episode": effective_episode,
                        "query_season": query.season if query.absolute_episode is None else None,
                        "query_series_title": query.series_title,
                    },
                )
                results.append(result)

        logger.info("Jimaku: found %d results", len(results))
        if results:
            logger.debug("Jimaku: top result - %s (score: %d, format: %s, language: %s)",
                        results[0].filename, results[0].score, results[0].format.value, results[0].language)
        return results

    def _search_by_anilist(self, anilist_id: int) -> list[dict]:
        """Search entries by AniList ID."""
        try:
            logger.debug("Jimaku: API request - AniList ID %d", anilist_id)
            resp = self.session.get(f"{API_BASE}/entries/search", params={
                "anilist_id": anilist_id,
            })
            logger.debug("Jimaku: API response status: %d", resp.status_code)
            if resp.status_code == 401 or resp.status_code == 403:
                error_msg = f"Jimaku authentication failed: HTTP {resp.status_code}"
                logger.error(error_msg)
                raise ProviderAuthError(error_msg)
            
            if resp.status_code == 429:
                error_msg = f"Jimaku rate limit exceeded: HTTP {resp.status_code}"
                logger.warning(error_msg)
                raise ProviderRateLimitError(error_msg)
            
            if resp.status_code == 200:
                data = resp.json()
                entries = data if isinstance(data, list) else [data]
                logger.debug("Jimaku: found %d entries by AniList ID", len(entries))
                return entries
            else:
                logger.warning("Jimaku AniList search failed: HTTP %d, response: %s", 
                             resp.status_code, resp.text[:200])
        except Exception as e:
            logger.warning("Jimaku AniList search failed: %s", e, exc_info=True)
        return []

    def _search_by_name(self, name: str) -> list[dict]:
        """Search entries by name."""
        try:
            logger.debug("Jimaku: API request - name: %s", name)
            resp = self.session.get(f"{API_BASE}/entries/search", params={
                "query": name,
            })
            logger.debug("Jimaku: API response status: %d", resp.status_code)
            if resp.status_code == 401 or resp.status_code == 403:
                error_msg = f"Jimaku authentication failed: HTTP {resp.status_code}"
                logger.error(error_msg)
                raise ProviderAuthError(error_msg)
            
            if resp.status_code == 429:
                error_msg = f"Jimaku rate limit exceeded: HTTP {resp.status_code}"
                logger.warning(error_msg)
                raise ProviderRateLimitError(error_msg)
            
            if resp.status_code == 200:
                data = resp.json()
                entries = data if isinstance(data, list) else [data]
                logger.debug("Jimaku: found %d entries by name", len(entries))
                return entries
            else:
                logger.warning("Jimaku name search failed: HTTP %d, response: %s", 
                             resp.status_code, resp.text[:200])
        except Exception as e:
            logger.warning("Jimaku name search failed: %s", e, exc_info=True)
        return []

    def _get_entry_files(self, entry_id: int, query: VideoQuery) -> list[tuple[str, str, bool]]:
        """Get available subtitle files for an entry.

        Returns list of (filename, download_url, is_archive) tuples.
        """
        try:
            resp = self.session.get(f"{API_BASE}/entries/{entry_id}/files")
            if resp.status_code != 200:
                return []

            files = resp.json() if isinstance(resp.json(), list) else []
            result = []
            for f in files:
                filename = f.get("name", "")
                url = f.get("url", "")
                ext = os.path.splitext(filename)[1].lower()

                if ext in _SUBTITLE_EXTENSIONS:
                    result.append((filename, url, False))
                elif ext in _ARCHIVE_EXTENSIONS:
                    result.append((filename, url, True))
                # Skip .7z and other unsupported archives

            return result
        except Exception as e:
            logger.warning("Jimaku get files failed: %s", e)
            return []

    def _detect_language(self, filename: str) -> str:
        """Detect language from filename patterns."""
        name_lower = filename.lower()

        # Common patterns (check in order of specificity)
        lang_patterns = {
            "ja": [".ja.", ".jpn.", ".japanese.", "_ja_", "_jpn_", "[ja]", "[jpn]"],
            "en": [".en.", ".eng.", ".english.", "_en_", "_eng_", "[en]", "[eng]"],
            "de": [".de.", ".deu.", ".ger.", ".german.", "_de_", "_deu_", "[de]", "[deu]", "[ger]", ".german"],
            "fr": [".fr.", ".fra.", ".fre.", ".french.", "_fr_", "[fr]", "[fra]"],
            "es": [".es.", ".spa.", ".spanish.", "_es_", "[es]", "[spa]"],
            "zh": [".zh.", ".chi.", ".chinese.", "_zh_", "[zh]", "[chi]"],
        }

        for lang, patterns in lang_patterns.items():
            if any(tag in name_lower for tag in patterns):
                return lang

        # Jimaku defaults to Japanese (most content is Japanese audio with English/Japanese subs)
        return "ja"

    def download(self, result: SubtitleResult) -> bytes:
        if not self.session:
            raise RuntimeError("Jimaku not initialized")

        url = result.download_url
        if not url:
            raise ValueError("No download URL")

        resp = self.session.get(url)
        if resp.status_code != 200:
            raise RuntimeError(f"Jimaku download failed: HTTP {resp.status_code}")

        content = resp.content
        is_archive = result.provider_data.get("is_archive", False)

        if is_archive:
            # Extract best matching subtitle from archive
            ext = os.path.splitext(result.filename)[1].lower()
            query = VideoQuery(
                series_title=result.provider_data.get("entry_name", ""),
                episode=result.provider_data.get("query_episode"),
                season=result.provider_data.get("query_season"),
            )

            if ext == ".zip":
                extracted = _extract_from_zip(content, query)
            elif ext == ".rar":
                extracted = _extract_from_rar(content, query)
            else:
                raise RuntimeError(f"Unsupported archive format: {ext}")

            if not extracted:
                raise RuntimeError("No subtitle files found in archive")

            # Score and pick best
            scored = [(name, data, _score_subtitle_file(name, query)) for name, data in extracted]
            scored.sort(key=lambda x: x[2], reverse=True)

            best_name, best_content, _ = scored[0]
            # Update result metadata
            result.filename = best_name
            ext = os.path.splitext(best_name)[1].lower()
            result.format = _FORMAT_MAP.get(ext, SubtitleFormat.UNKNOWN)
            content = best_content

        result.content = content
        logger.info("Jimaku: downloaded %s (%d bytes)", result.filename, len(content))
        return content
