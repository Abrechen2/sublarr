"""BetaSeries subtitle provider — French TV & movies.

BetaSeries (betaseries.com) offers a REST API for French and multilingual
subtitle lookup for TV series and movies. Requires a free API key.

API Docs: https://www.betaseries.com/api/
API Base: https://api.betaseries.com
Auth:     API Key (X-BetaSeries-Key header)
Rate:     30 req / 60 s
License:  GPL-3.0
"""

import logging

from providers import register_provider
from providers.base import (
    ProviderAuthError,
    SubtitleFormat,
    SubtitleProvider,
    SubtitleResult,
    VideoQuery,
)
from providers.http_session import create_session

logger = logging.getLogger(__name__)

_API_BASE = "https://api.betaseries.com"
_API_VERSION = "3.0"

# ISO 639-1 → BetaSeries language code
_LANG_MAP = {
    "fr": "VF",
    "en": "VO",
    "de": "DE",
    "es": "ES",
    "it": "IT",
    "pt": "PT",
}


def _format_from_url(url: str) -> SubtitleFormat:
    url_lower = url.lower()
    if ".ass" in url_lower:
        return SubtitleFormat.ASS
    if ".ssa" in url_lower:
        return SubtitleFormat.SSA
    if ".vtt" in url_lower:
        return SubtitleFormat.VTT
    return SubtitleFormat.SRT


@register_provider
class BetaSeriesProvider(SubtitleProvider):
    """BetaSeries subtitle provider.

    Focused on French TV series and movies. Requires a free API key.
    Register at https://www.betaseries.com/api/
    """

    name = "betaseries"
    languages = set(_LANG_MAP.keys())
    config_fields = [
        {
            "key": "betaseries_api_key",
            "label": "BetaSeries API Key",
            "type": "password",
            "required": True,
            "help": "Free API key from betaseries.com/api",
        }
    ]
    rate_limit = (30, 60)
    timeout = 15
    max_retries = 2

    def __init__(self, api_key: str = "", **kwargs):
        super().__init__(**kwargs)
        self.api_key = api_key
        self.session = None

    def initialize(self):
        self.session = create_session(
            max_retries=2,
            backoff_factor=1.0,
            timeout=self.timeout,
        )
        if self.api_key:
            self.session.headers.update({
                "X-BetaSeries-Key": self.api_key,
                "X-BetaSeries-Version": _API_VERSION,
                "Accept": "application/json",
            })

    def terminate(self):
        if self.session:
            self.session.close()
            self.session = None

    def health_check(self) -> tuple[bool, str]:
        if not self.session:
            return False, "Not initialized"
        if not self.api_key:
            return False, "API key not configured"
        try:
            resp = self.session.get(f"{_API_BASE}/shows/list", params={"limit": 1}, timeout=8)
            if resp.status_code == 200:
                return True, "OK"
            if resp.status_code in (401, 403):
                raise ProviderAuthError("Invalid BetaSeries API key")
            return False, f"HTTP {resp.status_code}"
        except ProviderAuthError:
            raise
        except Exception as e:
            return False, str(e)

    def _search_show(self, title: str) -> str | None:
        """Search for a show by title; return BetaSeries show ID or None."""
        try:
            resp = self.session.get(
                f"{_API_BASE}/search/shows",
                params={"title": title, "limit": 5},
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                return None
            shows = resp.json().get("shows") or []
            return str(shows[0].get("id") or "") if shows else None
        except Exception as e:
            logger.debug("BetaSeries: show search error: %s", e)
            return None

    def search(self, query: VideoQuery) -> list[SubtitleResult]:
        if not self.session:
            return []
        if not self.api_key:
            logger.debug("BetaSeries: no API key configured")
            return []

        search_langs = query.languages or ["fr"]
        valid_langs = [lc for lc in search_langs if lc in _LANG_MAP]
        if not valid_langs:
            return []

        results = []

        if query.is_episode and query.series_title and query.season and query.episode:
            show_id = self._search_show(query.series_title or query.title)
            if not show_id:
                return []
            try:
                resp = self.session.get(
                    f"{_API_BASE}/subtitles/show/{show_id}",
                    params={"season": query.season, "episode": query.episode},
                    timeout=self.timeout,
                )
                if resp.status_code != 200:
                    return []
                subs = resp.json().get("subtitles") or []
            except Exception as e:
                logger.debug("BetaSeries: episode subtitle error: %s", e)
                return []

            for sub in subs:
                sub_lang = (sub.get("language") or "").upper()
                matched = next((lc for lc in valid_langs if _LANG_MAP[lc] == sub_lang), None)
                if not matched:
                    continue
                dl_url = sub.get("url") or ""
                if not dl_url:
                    continue
                sub_id = str(sub.get("id") or dl_url.split("/")[-1])
                results.append(SubtitleResult(
                    provider_name=self.name,
                    subtitle_id=sub_id,
                    language=matched,
                    format=_format_from_url(dl_url),
                    filename=f"{sub_id}.srt",
                    download_url=dl_url,
                    release_info=sub.get("source") or "",
                    matches={"series", "season", "episode"},
                ))

        elif not query.is_episode and query.title:
            try:
                resp = self.session.get(
                    f"{_API_BASE}/subtitles/movie",
                    params={"title": query.title},
                    timeout=self.timeout,
                )
                if resp.status_code != 200:
                    return []
                subs = resp.json().get("subtitles") or []
            except Exception as e:
                logger.debug("BetaSeries: movie subtitle error: %s", e)
                return []

            for sub in subs:
                sub_lang = (sub.get("language") or "").upper()
                matched = next((lc for lc in valid_langs if _LANG_MAP[lc] == sub_lang), None)
                if not matched:
                    continue
                dl_url = sub.get("url") or ""
                if not dl_url:
                    continue
                sub_id = str(sub.get("id") or dl_url.split("/")[-1])
                results.append(SubtitleResult(
                    provider_name=self.name,
                    subtitle_id=sub_id,
                    language=matched,
                    format=_format_from_url(dl_url),
                    filename=f"{sub_id}.srt",
                    download_url=dl_url,
                    release_info=sub.get("source") or "",
                    matches={"title"},
                ))

        logger.info("BetaSeries: found %d results", len(results))
        return results

    def download(self, result: SubtitleResult) -> bytes:
        if not self.session:
            raise RuntimeError("BetaSeries not initialized")
        try:
            resp = self.session.get(result.download_url, timeout=self.timeout)
            if resp.status_code != 200:
                raise RuntimeError(f"BetaSeries download failed: HTTP {resp.status_code}")
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"BetaSeries download error: {e}") from e
        content = resp.content
        result.content = content
        logger.info("BetaSeries: downloaded %s (%d bytes)", result.filename, len(content))
        return content
