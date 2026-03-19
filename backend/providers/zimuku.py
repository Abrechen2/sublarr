"""Zimuku subtitle provider — Chinese subtitles.

Zimuku.net is the primary source for Chinese subtitles (Simplified and
Traditional). Uses HTML scraping with BeautifulSoup4. Only supports
Chinese language variants.

Base URL: https://zimuku.net
Auth:     None required
Rate:     10 req / 60 s (conservative — Cloudflare protection)
License:  GPL-3.0
"""

import logging

from archive_utils import extract_subtitles_from_rar, extract_subtitles_from_zip

try:
    from bs4 import BeautifulSoup
    _HAS_BS4 = True
except ImportError:
    _HAS_BS4 = False

from providers import register_provider
from providers.base import (
    SubtitleFormat,
    SubtitleProvider,
    SubtitleResult,
    VideoQuery,
)
from providers.http_session import create_session

logger = logging.getLogger(__name__)

_BASE_URL = "https://zimuku.net"
_SEARCH_URL = f"{_BASE_URL}/search"
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_CHINESE_LANGS = {"zh", "zh-hans", "zh-hant"}

_FORMAT_MAP = {
    ".ass": SubtitleFormat.ASS,
    ".ssa": SubtitleFormat.SSA,
    ".srt": SubtitleFormat.SRT,
    ".vtt": SubtitleFormat.VTT,
}


def _detect_lang(filename: str) -> str:
    """Detect simplified vs traditional Chinese from subtitle filename."""
    name_lower = filename.lower()
    if any(k in name_lower for k in ("繁", "cht", "traditional", "tw", "hk")):
        return "zh-hant"
    return "zh-hans"


@register_provider
class ZimukuProvider(SubtitleProvider):
    """Zimuku Chinese subtitle provider.

    Supports Simplified and Traditional Chinese. Uses HTML scraping.
    Returns empty list gracefully if bs4 is not installed.
    """

    name = "zimuku"
    languages = _CHINESE_LANGS
    config_fields = []
    rate_limit = (10, 60)
    timeout = 20
    max_retries = 2

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.session = None

    def initialize(self):
        self.session = create_session(
            max_retries=2,
            backoff_factor=2.0,
            timeout=self.timeout,
            user_agent=_BROWSER_UA,
        )
        self.session.headers.update({
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": _BASE_URL,
        })

    def terminate(self):
        if self.session:
            self.session.close()
            self.session = None

    def health_check(self) -> tuple[bool, str]:
        if not self.session:
            return False, "Not initialized"
        if not _HAS_BS4:
            return False, "beautifulsoup4 not installed"
        try:
            resp = self.session.get(_BASE_URL, timeout=10)
            if resp.status_code in (200, 301, 302):
                return True, "OK"
            # 403 from Cloudflare is expected without full browser
            if resp.status_code == 403:
                return True, "Cloudflare active (downloads may work)"
            return False, f"HTTP {resp.status_code}"
        except Exception as e:
            return False, str(e)

    def _search_titles(self, title: str) -> list[dict]:
        """Search zimuku for a title; return list of {url, name} dicts."""
        try:
            resp = self.session.get(
                _SEARCH_URL,
                params={"q": title},
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                logger.debug("Zimuku: search returned HTTP %d", resp.status_code)
                return []
            soup = BeautifulSoup(resp.text, "html.parser")
            results = []
            # Result items: <div class="item"> with <a href="/subs/{id}">
            for a in soup.select("div.item a[href*='/subs/']"):
                href = a.get("href", "")
                name = a.get_text(strip=True)
                if href and name:
                    url = f"{_BASE_URL}{href}" if href.startswith("/") else href
                    results.append({"url": url, "name": name})
            return results
        except Exception as e:
            logger.debug("Zimuku: search error: %s", e)
            return []

    def _get_download_links(self, detail_url: str) -> list[dict]:
        """Scrape a subtitle detail page for download links."""
        try:
            resp = self.session.get(detail_url, timeout=self.timeout)
            if resp.status_code != 200:
                return []
            soup = BeautifulSoup(resp.text, "html.parser")
            links = []
            for a in soup.select("a[href*='/dld/']"):
                href = a.get("href", "")
                name = a.get_text(strip=True) or href.split("/")[-1]
                if href:
                    url = f"{_BASE_URL}{href}" if href.startswith("/") else href
                    links.append({"url": url, "name": name})
            return links
        except Exception as e:
            logger.debug("Zimuku: detail page error: %s", e)
            return []

    def search(self, query: VideoQuery) -> list[SubtitleResult]:
        if not self.session:
            return []
        if not _HAS_BS4:
            logger.warning("Zimuku: beautifulsoup4 not installed")
            return []

        # Only handle Chinese language requests
        search_langs = query.languages or []
        has_chinese = any(lc in _CHINESE_LANGS for lc in search_langs)
        if not has_chinese:
            return []

        search_title = query.series_title or query.title
        if not search_title:
            return []

        logger.debug("Zimuku: searching '%s'", search_title)

        title_results = self._search_titles(search_title)
        if not title_results:
            return []

        best = title_results[0]
        dl_links = self._get_download_links(best["url"])

        results = []
        for link in dl_links[:6]:
            lang = _detect_lang(link["name"])
            # Only include if user requested this variant or generic zh
            if lang not in search_langs and "zh" not in search_langs:
                continue
            results.append(
                SubtitleResult(
                    provider_name=self.name,
                    subtitle_id=link["url"].rstrip("/").split("/")[-1],
                    language=lang,
                    format=SubtitleFormat.SRT,
                    filename=link["name"],
                    download_url=link["url"],
                    release_info=best["name"],
                    matches={"series"} if query.series_title else {"title"},
                    provider_data={"detail_url": best["url"]},
                )
            )

        logger.info("Zimuku: found %d results", len(results))
        return results

    def download(self, result: SubtitleResult) -> bytes:
        if not self.session:
            raise RuntimeError("Zimuku not initialized")

        referer = _BASE_URL
        if result.provider_data:
            referer = result.provider_data.get("detail_url", _BASE_URL)

        try:
            resp = self.session.get(
                result.download_url,
                headers={"Referer": referer},
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"Zimuku download failed: HTTP {resp.status_code}")
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"Zimuku download error: {e}") from e

        content = resp.content

        # ZIP archive
        if content[:2] == b"PK":
            try:
                entries = extract_subtitles_from_zip(content)
                if entries:
                    name, content = entries[0]
                    result.filename = name
                    ext = f".{name.lower().rsplit('.', 1)[-1]}" if "." in name else ""
                    result.format = _FORMAT_MAP.get(ext, SubtitleFormat.SRT)
                    result.language = _detect_lang(name)
            except Exception as e:
                raise RuntimeError(f"Zimuku: archive extraction failed: {e}") from e

        # RAR archive
        elif content[:4] == b"Rar!":
            try:
                entries = extract_subtitles_from_rar(content)
                if entries:
                    name, content = entries[0]
                    result.filename = name
                    ext = f".{name.lower().rsplit('.', 1)[-1]}" if "." in name else ""
                    result.format = _FORMAT_MAP.get(ext, SubtitleFormat.SRT)
                    result.language = _detect_lang(name)
                else:
                    raise RuntimeError("Zimuku: no subtitles found in RAR archive")
            except RuntimeError:
                raise
            except Exception as e:
                raise RuntimeError(f"Zimuku: RAR extraction failed: {e}") from e

        result.content = content
        logger.info("Zimuku: downloaded %s (%d bytes)", result.filename, len(content))
        return content
