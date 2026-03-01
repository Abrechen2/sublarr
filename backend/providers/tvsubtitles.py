"""TVSubtitles subtitle provider.

TVSubtitles is a long-running subtitle aggregator specialising in TV series.
Supports many European and Asian languages. No authentication required.

Base URL: https://www.tvsubtitles.net
Auth:     None required
Rate:     15 req / 60 s
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

_BASE_URL = "https://www.tvsubtitles.net"
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# TVSubtitles language names in HTML (lowercase, as used in class/text)
_LANG_NAMES = {
    "ar": "arabic",
    "bg": "bulgarian",
    "cs": "czech",
    "da": "danish",
    "nl": "dutch",
    "en": "english",
    "fi": "finnish",
    "fr": "french",
    "de": "german",
    "el": "greek",
    "he": "hebrew",
    "hr": "croatian",
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
    "sr": "serbian",
    "sk": "slovak",
    "sl": "slovenian",
    "es": "spanish",
    "sv": "swedish",
    "th": "thai",
    "tr": "turkish",
    "uk": "ukrainian",
    "vi": "vietnamese",
    "zh": "chinese",
    "zh-hans": "chinese",
    "zh-hant": "chinese",
}


@register_provider
class TVSubtitlesProvider(SubtitleProvider):
    """TVSubtitles subtitle provider.

    Specialises in TV series subtitles with broad language support.
    Uses HTML scraping via BeautifulSoup4.
    """

    name = "tvsubtitles"
    languages = set(_LANG_NAMES.keys())
    config_fields = []
    rate_limit = (15, 60)
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

    def _find_show(self, title: str) -> dict | None:
        """Search for a show by title, return {id, name} or None."""
        try:
            resp = self.session.post(
                f"{_BASE_URL}/search.php",
                data={"q": title},
                headers={"Referer": _BASE_URL},
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                return None
            soup = BeautifulSoup(resp.text, "html.parser")
            # Results: <ul id="r" class="left"> with <a href="/tvshow-{id}.html">
            for a in soup.select("ul#r a[href*='tvshow-']"):
                href = a.get("href", "")
                name = a.get_text(strip=True)
                if href and name and title.lower() in name.lower():
                    show_id = href.replace("/tvshow-", "").replace(".html", "").strip("/")
                    return {"id": show_id, "name": name, "url": f"{_BASE_URL}{href}"}
            # Fallback: first result
            first = soup.select_one("ul#r a[href*='tvshow-']")
            if first:
                href = first.get("href", "")
                name = first.get_text(strip=True)
                show_id = href.replace("/tvshow-", "").replace(".html", "").strip("/")
                return {"id": show_id, "name": name, "url": f"{_BASE_URL}{href}"}
        except Exception as e:
            logger.debug("TVSubtitles: show search error: %s", e)
        return None

    def _get_episode_subtitles(
        self, show_id: str, season: int, episode: int, lang_name: str
    ) -> list[dict]:
        """Fetch subtitle entries for a specific episode and language."""
        try:
            # Try episode page: /episode-{show_id}-{season}x{episode}.html
            ep_url = f"{_BASE_URL}/episode-{show_id}-{season}x{episode}.html"
            resp = self.session.get(ep_url, timeout=self.timeout)
            if resp.status_code != 200:
                return []
            soup = BeautifulSoup(resp.text, "html.parser")
            entries = []
            for row in soup.select("table tr"):
                cells = row.find_all("td")
                if len(cells) < 3:
                    continue
                lang_cell = cells[0].get_text(strip=True).lower()
                if lang_name not in lang_cell:
                    continue
                dl_link = row.find("a", href=lambda h: h and "download" in h)
                if not dl_link:
                    continue
                href = dl_link.get("href", "")
                release = cells[1].get_text(strip=True) if len(cells) > 1 else ""
                entries.append(
                    {
                        "url": f"{_BASE_URL}{href}" if href.startswith("/") else href,
                        "release": release,
                    }
                )
            return entries
        except Exception as e:
            logger.debug("TVSubtitles: episode fetch error: %s", e)
            return []

    def search(self, query: VideoQuery) -> list[SubtitleResult]:
        if not self.session:
            return []
        if not _HAS_BS4:
            logger.warning("TVSubtitles: beautifulsoup4 not installed")
            return []

        # TV shows only
        if query.is_movie or not query.is_episode:
            return []

        search_title = query.series_title or query.title
        if not search_title:
            return []

        logger.debug(
            "TVSubtitles: searching '%s' S%02dE%02d",
            search_title,
            query.season or 0,
            query.episode or 0,
        )

        show = self._find_show(search_title)
        if not show:
            logger.debug("TVSubtitles: show not found for '%s'", search_title)
            return []

        results = []
        search_langs = query.languages or ["en"]

        for lang_code in search_langs:
            lang_name = _LANG_NAMES.get(lang_code)
            if not lang_name:
                continue
            entries = self._get_episode_subtitles(
                show["id"], query.season or 1, query.episode or 1, lang_name
            )
            for entry in entries[:5]:
                subtitle_id = entry["url"].rstrip("/").split("/")[-1]
                results.append(
                    SubtitleResult(
                        provider_name=self.name,
                        subtitle_id=subtitle_id,
                        language=lang_code,
                        format=SubtitleFormat.SRT,
                        filename=f"{entry['release']}.srt"
                        if entry["release"]
                        else f"{subtitle_id}.srt",
                        download_url=entry["url"],
                        release_info=entry["release"],
                        matches={"series", "season", "episode"},
                        provider_data={"show_name": show["name"]},
                    )
                )

        logger.info("TVSubtitles: found %d results", len(results))
        return results

    def download(self, result: SubtitleResult) -> bytes:
        if not self.session:
            raise RuntimeError("TVSubtitles not initialized")

        resp = self.session.get(
            result.download_url,
            headers={"Referer": _BASE_URL},
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"TVSubtitles download failed: HTTP {resp.status_code}")

        content = resp.content

        # Extract from ZIP if needed
        if content[:2] == b"PK":
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as zf:
                    for name in zf.namelist():
                        if name.lower().endswith((".srt", ".ass", ".ssa", ".vtt")):
                            content = zf.read(name)
                            result.filename = name
                            break
            except Exception as e:
                logger.warning("TVSubtitles: ZIP extraction failed: %s", e)

        result.content = content
        logger.info("TVSubtitles: downloaded %s (%d bytes)", result.filename, len(content))
        return content
