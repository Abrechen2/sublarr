"""TVSubtitles subtitle provider.

TVSubtitles is a long-running subtitle aggregator specialising in TV series.
Supports many European and Asian languages. No authentication required.

Base URL: https://www.tvsubtitles.net
Auth:     None required
Rate:     15 req / 60 s
License:  GPL-3.0
"""

import logging
import re
import urllib.parse
from typing import ClassVar

from archive_utils import extract_subtitles_from_zip

try:
    from bs4 import BeautifulSoup

    _HAS_BS4 = True
except ImportError:
    _HAS_BS4 = False

from providers import _stream_download, register_provider
from providers.base import (
    ProviderError,
    SubtitleFormat,
    SubtitleProvider,
    SubtitleResult,
    VideoQuery,
)
from providers.http_session import create_session
from security_utils import validate_download_url

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.tvsubtitles.net"
_SUBTITLE_ID_RE = re.compile(r"subtitle-(\d+)")
_INTERSTITIAL_RE = re.compile(r"/download-\d+\.html$")
# The wait page builds its target as: var s1='..'; ... document.location = s1+s2+..;
_JS_FRAGMENT_RE = re.compile(r"""var\s+(\w+)\s*=\s*'([^']*)'""")
_JS_LOCATION_RE = re.compile(r"document\.location\s*=\s*([\w\s+]+);")
_FORMAT_MAP = {
    "srt": SubtitleFormat.SRT,
    "ass": SubtitleFormat.ASS,
    "ssa": SubtitleFormat.SSA,
    "vtt": SubtitleFormat.VTT,
}
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

    # HTML scraper — upstream tolerates ~15 req/60s, budget below that.
    rate_limits: ClassVar[dict[str, dict[str, int]]] = {
        "free": {"second": 1, "hour": 40, "day": 400},
    }
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
                f"{_BASE_URL}/search1.php",
                data={"qs": title},
                headers={"Referer": _BASE_URL},
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                # A dead endpoint is not an empty library — say so, or this
                # provider reports "no results" for every search forever.
                raise ProviderError(f"TVSubtitles search endpoint returned HTTP {resp.status_code}")
            soup = BeautifulSoup(resp.text, "html.parser")
            # Results are <a href="/tvshow-{id}.html"> links. They used to sit
            # in <ul id="r">; that wrapper is gone, so match the links alone.
            for a in soup.select("a[href*='tvshow-']"):
                href = a.get("href", "")
                name = a.get_text(strip=True)
                if href and name and title.lower() in name.lower():
                    show_id = href.replace("/tvshow-", "").replace(".html", "").strip("/")
                    return {"id": show_id, "name": name, "url": f"{_BASE_URL}{href}"}
            # Fallback: first result
            first = soup.select_one("a[href*='tvshow-']")
            if first:
                href = first.get("href", "")
                name = first.get_text(strip=True)
                show_id = href.replace("/tvshow-", "").replace(".html", "").strip("/")
                return {"id": show_id, "name": name, "url": f"{_BASE_URL}{href}"}
        except ProviderError:
            raise
        except Exception as e:
            logger.debug("TVSubtitles: show search error: %s", e)
        return None

    def _find_episode_page(self, show_id: str, season: int, episode: int) -> str | None:
        """Locate an episode's page via the season listing.

        Episodes used to be addressable as ``episode-{show}-{s}x{e}.html``.
        That 404s — they now carry an opaque internal id, and the season page
        is the only place that maps ``1x01`` onto it.
        """
        season_url = f"{_BASE_URL}/tvshow-{show_id}-{season}.html"
        resp = self.session.get(season_url, timeout=self.timeout)
        if resp.status_code != 200:
            raise ProviderError(f"TVSubtitles season page returned HTTP {resp.status_code}")

        soup = BeautifulSoup(resp.text, "html.parser")
        wanted = f"{season}x{episode:02d}"
        for row in soup.select("tr"):
            cells = row.find_all("td")
            if not cells or cells[0].get_text(strip=True) != wanted:
                continue
            link = row.find("a", href=lambda h: h and h.startswith("episode-"))
            if link:
                return f"{_BASE_URL}/{link.get('href').lstrip('/')}"
        return None

    def _get_episode_subtitles(
        self, show_id: str, season: int, episode: int, lang_code: str
    ) -> list[dict]:
        """Fetch subtitle entries for one episode in one language."""
        try:
            episode_url = self._find_episode_page(show_id, season, episode)
            if not episode_url:
                return []

            resp = self.session.get(episode_url, timeout=self.timeout)
            if resp.status_code != 200:
                raise ProviderError(f"TVSubtitles episode page returned HTTP {resp.status_code}")

            soup = BeautifulSoup(resp.text, "html.parser")
            entries = []
            # One <a href="/subtitle-{id}.html"> per subtitle, carrying its
            # language as a flag image: images/flags/{code}.gif
            for link in soup.select("a[href*='subtitle-']"):
                flag = link.select_one("img[src*='flags/']")
                if not flag:
                    continue
                entry_lang = flag.get("src", "").rsplit("/", 1)[-1].rsplit(".", 1)[0].lower()
                if entry_lang != lang_code.lower():
                    continue

                sub_id = _SUBTITLE_ID_RE.search(link.get("href", "") or "")
                if not sub_id:
                    continue

                entries.append(
                    {
                        # The download page is the subtitle id under another name.
                        "url": f"{_BASE_URL}/download-{sub_id.group(1)}.html",
                        "release": " ".join(link.stripped_strings).strip(),
                    }
                )
            return entries
        except ProviderError:
            raise
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
            if lang_code not in _LANG_NAMES:
                continue
            entries = self._get_episode_subtitles(
                show["id"], query.season or 1, query.episode or 1, lang_code
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

    def _resolve_download_url(self, page_url: str) -> str:
        """Read the real archive path off the interstitial wait page.

        ``download-{id}.html`` returns a page, not the file: a script splits the
        path into fragments, concatenates them and navigates there. Reassemble
        it in the order the concatenation names, rather than following a link
        that is not in the markup.
        """
        resp = self.session.get(page_url, timeout=self.timeout, headers={"Referer": _BASE_URL})
        if resp.status_code != 200:
            raise ProviderError(f"TVSubtitles download page returned HTTP {resp.status_code}")

        fragments = dict(_JS_FRAGMENT_RE.findall(resp.text))
        target = _JS_LOCATION_RE.search(resp.text)
        if not fragments or not target:
            raise ProviderError("TVSubtitles download page carried no resolvable archive path")

        path = "".join(fragments.get(name.strip(), "") for name in target.group(1).split("+"))
        if not path:
            raise ProviderError("TVSubtitles download page carried no resolvable archive path")

        return f"{_BASE_URL}/{urllib.parse.quote(path)}"

    def download(self, result: SubtitleResult) -> bytes:
        if not self.session:
            raise RuntimeError("TVSubtitles not initialized")

        download_url = result.download_url or ""
        # Only the interstitial itself gets unwrapped. A direct archive link
        # can contain "download-" too, and running it through the wait-page
        # parser could only ever fail on it.
        if _INTERSTITIAL_RE.search(download_url):
            download_url = self._resolve_download_url(download_url)

        # P1: Validate download URL against allowlist
        url_ok, url_err = validate_download_url(download_url, self.name)
        if not url_ok:
            raise ProviderError(f"TVSubtitles download URL rejected: {url_err}")

        try:
            # P5: 50 MB streaming cap
            content = _stream_download(
                self.session,
                download_url,
                timeout=self.timeout,
                headers={"Referer": _BASE_URL},
                provider_name=self.name,
            )
        except Exception as e:
            raise RuntimeError(f"TVSubtitles download failed: {e}") from e

        # Extract from ZIP if needed
        if content[:2] == b"PK":
            try:
                entries = extract_subtitles_from_zip(content)
                if entries:
                    name, content = entries[0]
                    result.filename = name
                    ext = name.lower().rsplit(".", 1)[-1] if "." in name else ""
                    if ext in _FORMAT_MAP:
                        result.format = _FORMAT_MAP[ext]
            except ValueError as e:
                raise RuntimeError(f"TVSubtitles: archive security check failed: {e}") from e

        result.content = content
        logger.info("TVSubtitles: downloaded %s (%d bytes)", result.filename, len(content))
        return content
