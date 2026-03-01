"""Addic7ed subtitle provider.

Addic7ed is a community-driven subtitle site specialising in TV series with
episode-exact subtitle matching. Optional credentials increase the download limit.

NOTE: The existing `gestdown` provider already proxies Addic7ed content through
a stable REST API (api.gestdown.info). This provider adds direct scraping for
shows or episodes not covered by the Gestdown proxy.

Base URL: https://www.addic7ed.com
Auth:     Optional (username/password — free account)
Rate:     10 req / 60 s (site blocks aggressive scrapers)
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

_BASE_URL = "https://www.addic7ed.com"
_LOGIN_URL = f"{_BASE_URL}/dologin.php"
_SEARCH_URL = f"{_BASE_URL}/search.php"
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Addic7ed language names as they appear on the site
_LANG_NAMES = {
    "ar": "Arabic",
    "bg": "Bulgarian",
    "ca": "Catalan",
    "zh": "Chinese (Simplified)",
    "zh-hans": "Chinese (Simplified)",
    "zh-hant": "Chinese (Traditional)",
    "hr": "Croatian",
    "cs": "Czech",
    "da": "Danish",
    "nl": "Dutch",
    "en": "English",
    "fi": "Finnish",
    "fr": "French",
    "de": "German",
    "el": "Greek",
    "he": "Hebrew",
    "hu": "Hungarian",
    "id": "Indonesian",
    "it": "Italian",
    "ja": "Japanese",
    "ko": "Korean",
    "ms": "Malay",
    "no": "Norwegian",
    "pl": "Polish",
    "pt": "Portuguese",
    "ro": "Romanian",
    "ru": "Russian",
    "sr": "Serbian",
    "sk": "Slovak",
    "sl": "Slovenian",
    "es": "Spanish",
    "sv": "Swedish",
    "th": "Thai",
    "tr": "Turkish",
    "uk": "Ukrainian",
    "vi": "Vietnamese",
}


@register_provider
class Addic7edProvider(SubtitleProvider):
    """Addic7ed subtitle provider.

    Scrapes addic7ed.com directly for TV series subtitles.
    Optional login credentials increase the per-day download limit.
    Requires beautifulsoup4.
    """

    name = "addic7ed"
    languages = set(_LANG_NAMES.keys())
    config_fields = [
        {
            "key": "addic7ed_username",
            "label": "Username",
            "type": "text",
            "required": False,
            "description": "Optionaler Addic7ed-Account (erhöht das Tageslimit)",
        },
        {"key": "addic7ed_password", "label": "Password", "type": "password", "required": False},
    ]
    rate_limit = (10, 60)
    timeout = 20
    max_retries = 2

    def __init__(self, username: str = "", password: str = "", **kwargs):
        super().__init__(**kwargs)
        self.username = username
        self.password = password
        self.session = None
        self._logged_in = False

    def initialize(self):
        self.session = create_session(
            max_retries=2,
            backoff_factor=1.5,
            timeout=self.timeout,
            user_agent=_BROWSER_UA,
        )
        self.session.headers.update(
            {
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": _BASE_URL,
            }
        )

        if self.username and self.password:
            self._login()

    def terminate(self):
        if self.session:
            self.session.close()
            self.session = None
        self._logged_in = False

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

    def _login(self):
        try:
            resp = self.session.post(
                _LOGIN_URL,
                data={"username": self.username, "password": self.password, "Submit": "Log in"},
                timeout=self.timeout,
            )
            if resp.status_code == 200 and "logout" in resp.text.lower():
                self._logged_in = True
                logger.debug("Addic7ed: logged in as %s", self.username)
            else:
                logger.warning("Addic7ed: login failed for %s", self.username)
        except Exception as e:
            logger.warning("Addic7ed: login error: %s", e)

    def _search_shows(self, title: str) -> list[dict]:
        """Search for shows by title, return list of {url, name} dicts."""
        try:
            resp = self.session.get(
                _SEARCH_URL,
                params={"search": title, "Submit": "Search"},
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                return []
            soup = BeautifulSoup(resp.text, "html.parser")
            results = []
            # Search results: <div class="tabel95"> with show links
            for a in soup.select("div.tabel95 a[href*='/show/'], table a[href*='/show/']"):
                href = a.get("href", "")
                name = a.get_text(strip=True)
                if href and name:
                    url = href if href.startswith("http") else f"{_BASE_URL}/{href.lstrip('/')}"
                    results.append({"url": url, "name": name})
            return results
        except Exception as e:
            logger.debug("Addic7ed: show search error: %s", e)
            return []

    def _get_episode_subtitles(self, show_url: str, season: int, episode: int) -> list[dict]:
        """Get subtitles for a specific episode from the show page."""
        try:
            # Addic7ed episode URL pattern: /serie/SHOW_NAME/SEASON/EPISODE/0
            # Or via season page for the show
            show_name = show_url.rstrip("/").split("/")[-1]
            ep_url = f"{_BASE_URL}/serie/{show_name}/{season}/{episode}/0"
            resp = self.session.get(ep_url, timeout=self.timeout)
            if resp.status_code != 200:
                # Try via show URL directly
                resp = self.session.get(show_url, timeout=self.timeout)
                if resp.status_code != 200:
                    return []
            soup = BeautifulSoup(resp.text, "html.parser")
            entries = []
            # Subtitle rows: <tr class="epeven"> or <tr class="epodd">
            for row in soup.select("tr.epeven, tr.epodd"):
                cells = row.find_all("td")
                if len(cells) < 5:
                    continue
                lang_cell = cells[0].get_text(strip=True)
                release_cell = cells[1].get_text(strip=True) if len(cells) > 1 else ""
                dl_link = row.find(
                    "a", href=lambda h: h and "/updated/" in h or "/original/" in h if h else False
                )
                if not dl_link:
                    dl_link = row.find(
                        "a", string=lambda t: t and "download" in t.lower() if t else False
                    )
                if not dl_link:
                    continue
                href = dl_link.get("href", "")
                download_url = (
                    href if href.startswith("http") else f"{_BASE_URL}/{href.lstrip('/')}"
                )
                entries.append(
                    {
                        "language": lang_cell,
                        "release": release_cell,
                        "url": download_url,
                    }
                )
            return entries
        except Exception as e:
            logger.debug("Addic7ed: episode subtitle fetch error: %s", e)
            return []

    def search(self, query: VideoQuery) -> list[SubtitleResult]:
        if not self.session:
            return []
        if not _HAS_BS4:
            logger.warning("Addic7ed: beautifulsoup4 not installed")
            return []
        if query.is_movie or not query.is_episode:
            return []

        search_title = query.series_title or query.title
        if not search_title:
            return []

        logger.debug(
            "Addic7ed: searching '%s' S%02dE%02d",
            search_title,
            query.season or 0,
            query.episode or 0,
        )

        shows = self._search_shows(search_title)
        if not shows:
            logger.debug("Addic7ed: no shows found for '%s'", search_title)
            return []

        # Pick best match
        best_show = next((s for s in shows if search_title.lower() in s["name"].lower()), shows[0])

        all_entries = self._get_episode_subtitles(
            best_show["url"], query.season or 1, query.episode or 1
        )

        results = []
        search_langs = query.languages or ["en"]

        for lang_code in search_langs:
            lang_name_target = _LANG_NAMES.get(lang_code, "").lower()
            for entry in all_entries:
                if lang_name_target and lang_name_target not in entry["language"].lower():
                    continue
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
                        provider_data={"show_name": best_show["name"]},
                    )
                )

        logger.info("Addic7ed: found %d results", len(results))
        return results

    def download(self, result: SubtitleResult) -> bytes:
        if not self.session:
            raise RuntimeError("Addic7ed not initialized")

        resp = self.session.get(
            result.download_url,
            headers={"Referer": _BASE_URL},
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Addic7ed download failed: HTTP {resp.status_code}")

        content = resp.content

        if content[:2] == b"PK":
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as zf:
                    for name in zf.namelist():
                        if name.lower().endswith((".srt", ".ass", ".ssa", ".vtt")):
                            content = zf.read(name)
                            result.filename = name
                            break
            except Exception as e:
                logger.warning("Addic7ed: ZIP extraction failed: %s", e)

        result.content = content
        logger.info("Addic7ed: downloaded %s (%d bytes)", result.filename, len(content))
        return content
