"""Subf2m subtitle provider — HTML scraping, no auth, BeautifulSoup4 required."""

import logging

from archive_utils import extract_subtitles_from_zip

try:
    from bs4 import BeautifulSoup
    _HAS_BS4 = True
except ImportError:
    _HAS_BS4 = False

from providers import register_provider
from providers.base import SubtitleFormat, SubtitleProvider, SubtitleResult, VideoQuery
from providers.http_session import create_session

logger = logging.getLogger(__name__)

_BASE_URL = "https://subf2m.co"
_SEARCH_URL = f"{_BASE_URL}/subtitles/searchbytitle"
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_LANG_SLUG = {
    "en": "english", "de": "german", "fr": "french", "es": "spanish",
    "it": "italian", "pt": "portuguese", "nl": "dutch", "pl": "polish",
    "ro": "romanian", "cs": "czech", "sk": "slovak", "hu": "hungarian",
    "hr": "croatian", "sr": "serbian", "bg": "bulgarian", "ru": "russian",
    "uk": "ukrainian", "tr": "turkish", "ar": "arabic", "fa": "farsi_persian",
    "zh": "chinese-simplified", "zh-hans": "chinese-simplified",
    "zh-hant": "chinese-traditional", "ja": "japanese", "ko": "korean",
    "vi": "vietnamese", "id": "indonesian", "he": "hebrew", "el": "greek",
    "sv": "swedish", "da": "danish", "no": "norwegian", "fi": "finnish",
    "th": "thai", "hi": "hindi",
}

_FORMAT_MAP = {
    ".ass": SubtitleFormat.ASS, ".ssa": SubtitleFormat.SSA,
    ".srt": SubtitleFormat.SRT, ".vtt": SubtitleFormat.VTT,
}


@register_provider
class Subf2mProvider(SubtitleProvider):
    name = "subf2m"
    languages = set(_LANG_SLUG.keys())
    config_fields = []
    rate_limit = (12, 60)
    timeout = 20
    max_retries = 2

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.session = None

    def initialize(self):
        self.session = create_session(
            max_retries=2, backoff_factor=1.5, timeout=self.timeout, user_agent=_BROWSER_UA,
        )
        self.session.headers.update({"Accept-Language": "en-US,en;q=0.9"})

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
            return (True, "OK") if resp.status_code == 200 else (False, f"HTTP {resp.status_code}")
        except Exception as e:
            return False, str(e)

    def _search_titles(self, title: str) -> list[dict]:
        try:
            resp = self.session.post(
                _SEARCH_URL, data={"query": title, "l": ""},
                headers={"Referer": _BASE_URL}, timeout=self.timeout,
            )
            if resp.status_code != 200:
                return []
            soup = BeautifulSoup(resp.text, "html.parser")
            results = []
            for a in soup.select("ul.title a[href^='/subtitles/']"):
                href = a.get("href", "")
                name = a.get_text(strip=True)
                if href and name:
                    results.append({"url": f"{_BASE_URL}{href}", "name": name})
            return results
        except Exception as e:
            logger.debug("Subf2m: title search error: %s", e)
            return []

    def _get_subtitle_entries(self, title_url: str, lang_slug: str) -> list[dict]:
        lang_url = f"{title_url}/{lang_slug}"
        try:
            resp = self.session.get(lang_url, headers={"Referer": _BASE_URL}, timeout=self.timeout)
            if resp.status_code != 200:
                return []
            soup = BeautifulSoup(resp.text, "html.parser")
            entries = []
            for li in soup.select("li.item"):
                a = li.find("a", href=lambda h: h and "/subtitles/" in h)
                if not a:
                    continue
                href = a.get("href", "")
                name = a.get_text(strip=True)
                if href:
                    entries.append({
                        "url": f"{_BASE_URL}{href}" if href.startswith("/") else href,
                        "name": name,
                    })
            return entries
        except Exception as e:
            logger.debug("Subf2m: subtitle listing error: %s", e)
            return []

    def _get_download_url(self, subtitle_page_url: str) -> str | None:
        try:
            resp = self.session.get(subtitle_page_url, headers={"Referer": _BASE_URL}, timeout=self.timeout)
            if resp.status_code != 200:
                return None
            soup = BeautifulSoup(resp.text, "html.parser")
            a = soup.find("a", {"id": "downloadButton"}) or soup.select_one("a[href*='/subtitle/download']")
            if a:
                href = a.get("href", "")
                return f"{_BASE_URL}{href}" if href.startswith("/") else href
        except Exception as e:
            logger.debug("Subf2m: detail page error: %s", e)
        return None

    def search(self, query: VideoQuery) -> list[SubtitleResult]:
        if not self.session:
            return []
        if not _HAS_BS4:
            logger.warning("Subf2m: beautifulsoup4 not installed")
            return []

        search_title = query.series_title or query.title
        if not search_title:
            return []

        title_results = self._search_titles(search_title)
        if not title_results:
            return []

        best_url = next(
            (tr["url"] for tr in title_results if search_title.lower() in tr["name"].lower()),
            title_results[0]["url"],
        )

        results = []
        for lang_code in (query.languages or ["en"]):
            slug = _LANG_SLUG.get(lang_code)
            if not slug:
                continue
            for entry in self._get_subtitle_entries(best_url, slug)[:8]:
                sub_id = entry["url"].rstrip("/").split("/")[-1]
                results.append(SubtitleResult(
                    provider_name=self.name,
                    subtitle_id=sub_id,
                    language=lang_code,
                    format=SubtitleFormat.SRT,
                    filename=f"{entry['name']}.srt",
                    download_url=entry["url"],
                    release_info=entry["name"],
                    matches={"series"} if query.series_title else {"title"},
                    provider_data={"detail_url": entry["url"]},
                ))

        return results

    def download(self, result: SubtitleResult) -> bytes:
        if not self.session:
            raise RuntimeError("Subf2m not initialized")

        detail_url = (result.provider_data or {}).get("detail_url") or result.download_url
        dl_url = self._get_download_url(detail_url)
        if not dl_url:
            raise RuntimeError(f"Subf2m: no download URL found at {detail_url}")

        try:
            resp = self.session.get(dl_url, headers={"Referer": detail_url}, timeout=self.timeout)
            if resp.status_code != 200:
                raise RuntimeError(f"Subf2m download failed: HTTP {resp.status_code}")
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"Subf2m download error: {e}") from e

        content = resp.content
        if content[:2] == b"PK":
            try:
                entries = extract_subtitles_from_zip(content)
                if entries:
                    name, content = entries[0]
                    result.filename = name
                    ext = f".{name.lower().rsplit('.', 1)[-1]}" if "." in name else ""
                    result.format = _FORMAT_MAP.get(ext, SubtitleFormat.SRT)
            except Exception as e:
                raise RuntimeError(f"Subf2m: archive error: {e}") from e

        result.content = content
        return content
