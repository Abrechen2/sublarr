"""Gestdown subtitle provider -- REST API proxy for Addic7ed content.

Gestdown provides a stable REST API that proxies Addic7ed subtitles,
avoiding Addic7ed's anti-scraping measures. TV shows only (no movies).
Covers both PROV-01 (Addic7ed) and PROV-03 (Gestdown) requirements.

API Base: https://api.gestdown.info
Auth: None required
Rate limit: Conservative 30 req/60s
License: GPL-3.0
"""

import os
import time
import logging
from typing import Optional

from providers.base import (
    SubtitleProvider,
    SubtitleResult,
    SubtitleFormat,
    VideoQuery,
    ProviderRateLimitError,
)
from providers import register_provider
from providers.http_session import create_session

logger = logging.getLogger(__name__)

API_BASE = "https://api.gestdown.info"

_FORMAT_MAP = {
    ".ass": SubtitleFormat.ASS,
    ".ssa": SubtitleFormat.SSA,
    ".srt": SubtitleFormat.SRT,
    ".vtt": SubtitleFormat.VTT,
}


@register_provider
class GestdownProvider(SubtitleProvider):
    """Gestdown subtitle provider (Addic7ed proxy via REST API).

    Searches Addic7ed content through Gestdown's stable REST API.
    TV shows only -- movies are not supported by this provider.
    """

    name = "gestdown"
    languages = {
        "en", "de", "fr", "es", "it", "pt", "nl", "pl", "sv", "da",
        "no", "fi", "cs", "hu", "tr", "ro", "el", "he", "ar", "zh",
        "ja", "ko", "ru", "bg", "hr", "sr", "sk", "sl", "ca", "eu",
        "gl", "uk", "et", "lv", "lt", "fa", "id", "ms", "th", "vi",
    }

    # Plugin system attributes
    config_fields = []  # no auth required
    rate_limit = (30, 60)
    timeout = 15
    max_retries = 2

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.session = None
        self._language_cache: Optional[dict[str, int]] = None

    def initialize(self):
        logger.debug("Gestdown: initializing (no API key required)")
        self.session = create_session(
            max_retries=2,
            backoff_factor=1.0,
            timeout=15,
            user_agent="Sublarr/1.0",
        )
        logger.debug("Gestdown: session created successfully")

    def terminate(self):
        if self.session:
            self.session.close()
            self.session = None
        self._language_cache = None

    def health_check(self) -> tuple[bool, str]:
        if not self.session:
            return False, "Not initialized"
        try:
            resp = self.session.get(f"{API_BASE}/shows/search/test")
            if resp.status_code == 200:
                return True, "OK"
            return False, f"HTTP {resp.status_code}"
        except Exception as e:
            return False, str(e)

    def _get_language_map(self) -> dict[str, int]:
        """Fetch and cache Gestdown's language ID mapping.

        Maps ISO 639-1 codes to Gestdown's internal language IDs.
        Falls back to a hardcoded common subset if the API call fails.
        """
        if self._language_cache is not None:
            return self._language_cache

        # Hardcoded fallback for the most common languages
        # These are Gestdown's internal IDs matching Addic7ed's system
        fallback = {
            "en": 1, "fr": 8, "es": 4, "de": 11, "it": 7,
            "pt": 10, "nl": 17, "ro": 26, "pl": 23, "cs": 14,
            "hu": 20, "tr": 16, "el": 15, "ar": 38, "he": 22,
            "zh": 24, "ja": 35, "ko": 37, "ru": 19, "sv": 18,
            "da": 29, "no": 25, "fi": 31, "bg": 35, "hr": 38,
            "sr": 36, "sk": 33, "sl": 42, "ca": 34, "eu": 39,
        }

        if not self.session:
            self._language_cache = fallback
            return fallback

        try:
            resp = self.session.get(f"{API_BASE}/languages")
            if resp.status_code == 200:
                data = resp.json()
                lang_map = {}
                # API returns a list of language objects with id and name
                for lang_obj in data if isinstance(data, list) else data.get("languages", data.get("items", [])):
                    lang_id = lang_obj.get("id")
                    lang_name = (lang_obj.get("name") or "").lower()
                    # Map language names to ISO 639-1 codes
                    name_to_iso = {
                        "english": "en", "french": "fr", "spanish": "es",
                        "german": "de", "italian": "it", "portuguese": "pt",
                        "dutch": "nl", "romanian": "ro", "polish": "pl",
                        "czech": "cs", "hungarian": "hu", "turkish": "tr",
                        "greek": "el", "arabic": "ar", "hebrew": "he",
                        "chinese": "zh", "japanese": "ja", "korean": "ko",
                        "russian": "ru", "swedish": "sv", "danish": "da",
                        "norwegian": "no", "finnish": "fi", "bulgarian": "bg",
                        "croatian": "hr", "serbian": "sr", "slovak": "sk",
                        "slovenian": "sl", "catalan": "ca", "basque": "eu",
                        "galician": "gl", "ukrainian": "uk", "estonian": "et",
                        "latvian": "lv", "lithuanian": "lt", "persian": "fa",
                        "indonesian": "id", "malay": "ms", "thai": "th",
                        "vietnamese": "vi",
                    }
                    iso_code = name_to_iso.get(lang_name)
                    if iso_code and lang_id is not None:
                        lang_map[iso_code] = lang_id
                if lang_map:
                    self._language_cache = lang_map
                    logger.debug("Gestdown: cached %d language mappings from API", len(lang_map))
                    return lang_map
        except Exception as e:
            logger.debug("Gestdown: failed to fetch languages, using fallback: %s", e)

        self._language_cache = fallback
        return fallback

    def _find_show(self, query: VideoQuery) -> Optional[dict]:
        """Look up a show by TVDB ID or name search.

        Returns the show dict with at least an 'id' (UUID) field, or None.
        """
        if not self.session:
            return None

        # Try TVDB ID lookup first (most accurate)
        if query.tvdb_id:
            try:
                resp = self.session.get(f"{API_BASE}/shows/external/tvdb/{query.tvdb_id}")
                if resp.status_code == 200:
                    data = resp.json()
                    # API may return the show directly or nested
                    show = data if "id" in data else data.get("show")
                    if show and show.get("id"):
                        logger.debug("Gestdown: found show by TVDB ID %d: %s",
                                    query.tvdb_id, show.get("name", "unknown"))
                        return show
                elif resp.status_code == 429:
                    raise ProviderRateLimitError("Gestdown rate limit exceeded")
            except ProviderRateLimitError:
                raise
            except Exception as e:
                logger.debug("Gestdown: TVDB ID lookup failed: %s", e)

        # Fallback: search by name
        series_title = query.series_title or query.title
        if not series_title:
            return None

        try:
            resp = self.session.get(f"{API_BASE}/shows/search/{series_title}")
            if resp.status_code == 200:
                data = resp.json()
                shows = data if isinstance(data, list) else data.get("shows", [])
                if shows:
                    # Pick the first match
                    show = shows[0]
                    logger.debug("Gestdown: found show by name search '%s': %s",
                                series_title, show.get("name", "unknown"))
                    return show
            elif resp.status_code == 429:
                raise ProviderRateLimitError("Gestdown rate limit exceeded")
        except ProviderRateLimitError:
            raise
        except Exception as e:
            logger.debug("Gestdown: name search failed: %s", e)

        return None

    def search(self, query: VideoQuery) -> list[SubtitleResult]:
        if not self.session:
            logger.warning("Gestdown: cannot search - session is None")
            return []

        # Gestdown only supports TV shows, not movies
        if query.is_movie:
            logger.debug("Gestdown: skipping movie query (TV shows only)")
            return []

        if not query.is_episode:
            logger.debug("Gestdown: skipping non-episode query")
            return []

        logger.debug("Gestdown: searching for %s (languages: %s)",
                     query.display_name, query.languages)

        # Step 1: Find the show
        show = self._find_show(query)
        if not show:
            logger.debug("Gestdown: show not found for '%s'",
                        query.series_title or query.title)
            return []

        show_id = show.get("id")
        if not show_id:
            return []

        # Step 2: Get subtitles for each requested language
        results = []
        lang_map = self._get_language_map()

        search_languages = query.languages if query.languages else ["en"]

        for lang_code in search_languages:
            gestdown_lang_id = lang_map.get(lang_code)
            if gestdown_lang_id is None:
                logger.debug("Gestdown: no language mapping for '%s', skipping", lang_code)
                continue

            try:
                url = (f"{API_BASE}/subtitles/get/{show_id}"
                       f"/{query.season}/{query.episode}/{gestdown_lang_id}")
                resp = self.session.get(url)

                if resp.status_code == 429:
                    raise ProviderRateLimitError("Gestdown rate limit exceeded")

                if resp.status_code == 423:
                    # Locked/retry -- wait 1s and retry once
                    logger.debug("Gestdown: HTTP 423 (locked), retrying after 1s")
                    time.sleep(1)
                    resp = self.session.get(url)

                if resp.status_code != 200:
                    logger.debug("Gestdown: subtitle fetch returned HTTP %d for %s S%02dE%02d lang=%s",
                                resp.status_code, show.get("name", "?"),
                                query.season, query.episode, lang_code)
                    continue

                data = resp.json()
                subtitles = data if isinstance(data, list) else data.get("subtitles", data.get("matchingSubtitles", []))

                for sub in subtitles:
                    # Filter: only completed subtitles
                    if not sub.get("completed", True):
                        continue

                    sub_id = sub.get("subtitleId") or sub.get("id") or ""
                    download_url = sub.get("downloadUri") or sub.get("download_url") or ""
                    filename = sub.get("fileName") or sub.get("filename") or f"{sub_id}.srt"
                    version = sub.get("version") or sub.get("release") or ""

                    # Detect format from filename extension
                    ext = os.path.splitext(filename)[1].lower()
                    fmt = _FORMAT_MAP.get(ext, SubtitleFormat.SRT)

                    # Build matches
                    matches = {"series", "season", "episode"}

                    # Check release group match
                    if query.release_group and version:
                        if query.release_group.lower() in version.lower():
                            matches.add("release_group")

                    result = SubtitleResult(
                        provider_name=self.name,
                        subtitle_id=str(sub_id),
                        language=lang_code,
                        format=fmt,
                        filename=filename,
                        download_url=download_url,
                        release_info=version,
                        matches=matches,
                        hearing_impaired=sub.get("hearingImpaired", False),
                        provider_data={
                            "show_id": show_id,
                            "show_name": show.get("name", ""),
                        },
                    )
                    results.append(result)

            except ProviderRateLimitError:
                raise
            except Exception as e:
                logger.error("Gestdown: error fetching subtitles for lang %s: %s",
                           lang_code, e, exc_info=True)

        logger.info("Gestdown: found %d subtitle results", len(results))
        if results:
            logger.debug("Gestdown: top result - %s (format: %s, language: %s)",
                        results[0].filename, results[0].format.value, results[0].language)
        return results

    def download(self, result: SubtitleResult) -> bytes:
        if not self.session:
            raise RuntimeError("Gestdown not initialized")

        url = result.download_url
        if not url:
            raise ValueError("No download URL")

        # Ensure absolute URL
        if url.startswith("/"):
            url = f"{API_BASE}{url}"

        resp = self.session.get(url, allow_redirects=True)

        if resp.status_code == 429:
            raise ProviderRateLimitError("Gestdown download rate limited")

        if resp.status_code != 200:
            raise RuntimeError(f"Gestdown download failed: HTTP {resp.status_code}")

        content = resp.content
        result.content = content
        logger.info("Gestdown: downloaded %s (%d bytes)", result.filename, len(content))
        return content
