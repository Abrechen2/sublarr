"""Subscene subtitle provider.

Subscene is a large community subtitle database supporting 60+ languages.
No authentication required for searching and downloading.

Base URL: https://subscene.com
Auth:     None required
Rate:     10 req / 60 s (conservative — site blocks aggressive scrapers)
License:  GPL-3.0
"""

import io
import logging
import zipfile

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

_BASE_URL = "https://subscene.com"
_SEARCH_URL = f"{_BASE_URL}/subtitles/searchbytitle"
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Subscene language filter names as used in the URL and page HTML
# Map ISO 639-1 → Subscene language filter keyword
_LANG_NAMES = {
    "ar": "arabic",
    "da": "danish",
    "nl": "dutch",
    "en": "english",
    "fa": "farsi_persian",
    "fi": "finnish",
    "fr": "french",
    "de": "german",
    "el": "greek",
    "he": "hebrew",
    "hi": "hindi",
    "hu": "hungarian",
    "id": "indonesian",
    "it": "italian",
    "ja": "japanese",
    "ko": "korean",
    "ms": "malay",
    "no": "norwegian",
    "pl": "polish",
    "pt": "portuguese",
    "ro": "romanian",
    "ru": "russian",
    "es": "spanish",
    "sv": "swedish",
    "th": "thai",
    "tr": "turkish",
    "uk": "ukrainian",
    "vi": "vietnamese",
    "zh": "chinese_simplified",
    "zh-hans": "chinese_simplified",
    "zh-hant": "chinese_traditional",
    "hr": "croatian",
    "cs": "czech",
    "sk": "slovak",
    "bg": "bulgarian",
    "sr": "serbian",
    "sl": "slovenian",
    "bs": "bosnian",
    "mk": "macedonian",
    "sq": "albanian",
    "lt": "lithuanian",
    "lv": "latvian",
    "et": "estonian",
    "hy": "armenian",
    "ka": "georgian",
    "is": "icelandic",
    "bn": "bengali",
    "ur": "urdu",
    "ta": "tamil",
    "te": "telugu",
    "ml": "malayalam",
    "af": "afrikaans",
    "ca": "catalan",
    "eu": "basque",
    "gl": "galician",
}


@register_provider
class SubsceneProvider(SubtitleProvider):
    """Subscene subtitle provider.

    Large community-driven database supporting 60+ languages.
    Uses HTML scraping with BeautifulSoup4. Gracefully returns an empty
    list if beautifulsoup4 is not installed.
    """

    name = "subscene"
    languages = set(_LANG_NAMES.keys())
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
            backoff_factor=1.5,
            timeout=self.timeout,
            user_agent=_BROWSER_UA,
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
        """POST to Subscene search and return list of {url, title} dicts."""
        try:
            resp = self.session.post(
                _SEARCH_URL,
                data={"query": title},
                headers={"Referer": _BASE_URL},
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                logger.debug("Subscene: search returned HTTP %d", resp.status_code)
                return []
            soup = BeautifulSoup(resp.text, "html.parser")
            results = []
            # Results are in <div class="title"><a href="/subtitles/...">
            for a in soup.select("div.title a[href^='/subtitles/']"):
                href = a.get("href", "")
                text = a.get_text(strip=True)
                if href and text:
                    results.append({"url": f"{_BASE_URL}{href}", "title": text})
            return results
        except Exception as e:
            logger.debug("Subscene: search error: %s", e)
            return []

    def _get_subtitles_for_lang(self, page_url: str, lang_name: str) -> list[dict]:
        """Fetch the subtitle listing page and extract entries for a language."""
        try:
            resp = self.session.get(
                page_url,
                params={"l": lang_name},
                headers={"Referer": _BASE_URL},
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                return []
            soup = BeautifulSoup(resp.text, "html.parser")
            entries = []
            # Subtitle rows: <div class="a1"><a href="/subtitles/.../{id}">
            for row in soup.select("td.a1"):
                a = row.find("a")
                if not a:
                    continue
                href = a.get("href", "")
                spans = a.find_all("span")
                lang_span = spans[0].get_text(strip=True) if spans else ""
                name_span = spans[1].get_text(strip=True) if len(spans) > 1 else ""
                if not href:
                    continue
                entries.append(
                    {
                        "url": f"{_BASE_URL}{href}",
                        "lang": lang_span,
                        "name": name_span,
                    }
                )
            return entries
        except Exception as e:
            logger.debug("Subscene: listing error for %s: %s", page_url, e)
            return []

    def _get_download_url(self, subtitle_page_url: str) -> str | None:
        """Follow the subtitle detail page to find the actual download link."""
        try:
            resp = self.session.get(
                subtitle_page_url,
                headers={"Referer": _BASE_URL},
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                return None
            soup = BeautifulSoup(resp.text, "html.parser")
            # Download link: <a id="downloadButton" href="/subtitle/download/...">
            a = soup.find("a", id="downloadButton") or soup.select_one(
                "a[href*='/subtitle/download']"
            )
            if a:
                href = a.get("href", "")
                return f"{_BASE_URL}{href}" if href.startswith("/") else href
        except Exception as e:
            logger.debug("Subscene: detail page error: %s", e)
        return None

    def search(self, query: VideoQuery) -> list[SubtitleResult]:
        if not self.session:
            return []
        if not _HAS_BS4:
            logger.warning("Subscene: beautifulsoup4 not installed")
            return []

        search_title = query.series_title or query.title
        if not search_title:
            return []

        logger.debug("Subscene: searching '%s' (languages: %s)", search_title, query.languages)

        title_results = self._search_titles(search_title)
        if not title_results:
            logger.debug("Subscene: no title matches for '%s'", search_title)
            return []

        # Pick the best-matching title (first result, case-insensitive prefix match preferred)
        best_url = None
        for tr in title_results:
            if search_title.lower() in tr["title"].lower():
                best_url = tr["url"]
                break
        if not best_url:
            best_url = title_results[0]["url"]

        results = []
        search_langs = query.languages or ["en"]

        for lang_code in search_langs:
            lang_name = _LANG_NAMES.get(lang_code)
            if not lang_name:
                continue
            entries = self._get_subtitles_for_lang(best_url, lang_name)
            for entry in entries[:10]:  # cap per language to limit requests
                subtitle_id = entry["url"].rstrip("/").split("/")[-1]
                results.append(
                    SubtitleResult(
                        provider_name=self.name,
                        subtitle_id=subtitle_id,
                        language=lang_code,
                        format=SubtitleFormat.SRT,
                        filename=entry["name"] + ".srt",
                        download_url=entry["url"],  # detail page; resolved in download()
                        release_info=entry["name"],
                        matches={"series"} if query.series_title else set(),
                        provider_data={"detail_url": entry["url"]},
                    )
                )

        logger.info("Subscene: found %d results", len(results))
        return results

    def download(self, result: SubtitleResult) -> bytes:
        if not self.session:
            raise RuntimeError("Subscene not initialized")

        detail_url = (result.provider_data or {}).get("detail_url") or result.download_url
        dl_url = self._get_download_url(detail_url)
        if not dl_url:
            raise RuntimeError(f"Subscene: no download URL on {detail_url}")

        resp = self.session.get(dl_url, headers={"Referer": detail_url}, timeout=self.timeout)
        if resp.status_code != 200:
            raise RuntimeError(f"Subscene download failed: HTTP {resp.status_code}")

        content = resp.content

        # Extract from ZIP if needed
        if content[:2] == b"PK":
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as zf:
                    names = zf.namelist()
                    # Pick first subtitle file
                    for name in names:
                        if name.lower().endswith((".srt", ".ass", ".ssa", ".vtt", ".sub")):
                            content = zf.read(name)
                            result.filename = name
                            ext = name.rsplit(".", 1)[-1].lower()
                            result.format = {
                                "ass": SubtitleFormat.ASS,
                                "ssa": SubtitleFormat.SSA,
                                "vtt": SubtitleFormat.VTT,
                            }.get(ext, SubtitleFormat.SRT)
                            break
            except Exception as e:
                logger.warning("Subscene: ZIP extraction failed: %s", e)

        result.content = content
        logger.info("Subscene: downloaded %s (%d bytes)", result.filename, len(content))
        return content
