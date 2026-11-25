"""Titrari (titrari.ro) subtitle provider — Romanian subtitles.

HTML scraping provider for Romanian subtitles from titrari.ro.
No authentication required — uses browser-like User-Agent for access.

Handles HTML table parsing with BeautifulSoup and extracts subtitles
from RAR/ZIP archives.

License: GPL-3.0
"""

import logging
import os
import re
from typing import ClassVar

from archive_utils import extract_subtitles_from_rar, extract_subtitles_from_zip
from providers import _stream_download, register_provider
from providers.base import (
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
    SubtitleFormat,
    SubtitleProvider,
    SubtitleResult,
    VideoQuery,
)
from providers.http_session import create_session
from security_utils import validate_download_url

logger = logging.getLogger(__name__)

# Conditional imports with graceful fallback
try:
    from bs4 import BeautifulSoup

    _HAS_BS4 = True
except ImportError:
    _HAS_BS4 = False
    logger.warning("Titrari: beautifulsoup4 not installed, provider will be non-functional")

try:
    import guessit as _guessit_module

    _HAS_GUESSIT = True
except ImportError:
    _HAS_GUESSIT = False
    logger.debug("Titrari: guessit not installed, using regex fallback for release parsing")


from providers.titrari_parsing import (  # noqa: E402 — after the optional imports
    BASE_URL,
    SEARCH_URL,
    parse_entries,
    pick_episode_member,
    search_params,
    season_covered,
)

_SUBTITLE_EXTENSIONS = {".srt", ".ass", ".ssa", ".sub", ".vtt"}
_FORMAT_MAP = {
    ".ass": SubtitleFormat.ASS,
    ".ssa": SubtitleFormat.SSA,
    ".srt": SubtitleFormat.SRT,
    ".vtt": SubtitleFormat.VTT,
    ".sub": SubtitleFormat.UNKNOWN,
}

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def _parse_episode_info(text: str) -> dict:
    """Parse season/episode info from a release name using guessit or regex fallback."""
    if _HAS_GUESSIT:
        try:
            info = _guessit_module.guessit(text)
            return {
                "season": info.get("season"),
                "episode": info.get("episode"),
                "title": info.get("title", ""),
                "release_group": info.get("release_group", ""),
                "source": info.get("source", ""),
                "resolution": str(info.get("screen_size", "")),
            }
        except Exception:
            logger.debug("Could not parse release info from the subtitle title", exc_info=True)

    # Regex fallback
    result = {
        "season": None,
        "episode": None,
        "title": "",
        "release_group": "",
        "source": "",
        "resolution": "",
    }

    # S01E02 pattern
    m = re.search(r"[Ss](\d{1,2})[Ee](\d{1,3})", text)
    if m:
        result["season"] = int(m.group(1))
        result["episode"] = int(m.group(2))

    # Resolution
    m = re.search(r"(1080p|720p|480p|2160p|4[Kk])", text)
    if m:
        result["resolution"] = m.group(1)

    # Release group (last bracket group)
    m = re.search(r"[-\s](\w+)$", text.strip())
    if m:
        result["release_group"] = m.group(1)

    return result


def _detect_format_from_filename(filename: str) -> SubtitleFormat:
    """Detect subtitle format from filename extension."""
    ext = os.path.splitext(filename)[1].lower()
    return _FORMAT_MAP.get(ext, SubtitleFormat.SRT)


@register_provider
class TitrariProvider(SubtitleProvider):
    """Titrari subtitle provider — Romanian subtitles via HTML scraping."""

    name = "titrari"

    # HTML scraper, no official limit — stay polite to avoid IP bans.
    rate_limits: ClassVar[dict[str, dict[str, int]]] = {
        "free": {"second": 1, "hour": 30, "day": 300},
    }
    languages = {"ro"}

    # Plugin system attributes
    config_fields = []  # no auth required
    rate_limit = (10, 60)  # polite scraping: 10 requests per minute
    timeout = 20
    max_retries = 2

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.session = None

    def initialize(self):
        """Initialize HTTP session with browser-like headers."""
        logger.debug("Titrari: initializing (no auth required)")
        self.session = create_session(
            max_retries=2,
            backoff_factor=1.0,
            timeout=20,
            user_agent=_BROWSER_UA,
        )
        self.session.headers.update(
            {
                "Accept-Language": "ro-RO,ro;q=0.9,en;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )
        logger.debug("Titrari: session created successfully")

    def terminate(self):
        """Close HTTP session."""
        if self.session:
            self.session.close()
            self.session = None

    def health_check(self) -> tuple[bool, str]:
        """Check if titrari.ro is reachable and has expected structure."""
        if not self.session:
            return False, "Not initialized"
        try:
            resp = self.session.get(BASE_URL, timeout=10)
            if resp.status_code == 200:
                if _HAS_BS4:
                    soup = BeautifulSoup(resp.text, "lxml" if _can_use_lxml() else "html.parser")
                    # Check for search form presence
                    if soup.find("form") or soup.find("input"):
                        return True, "OK"
                    return True, "OK (structure unclear)"
                return True, "OK (no HTML parsing available)"
            if resp.status_code == 403:
                return False, "Blocked (HTTP 403)"
            return False, f"HTTP {resp.status_code}"
        except Exception as e:
            return False, str(e)

    def search(self, query: VideoQuery) -> list[SubtitleResult]:
        """Search titrari.ro for Romanian subtitles matching the query."""
        if not _HAS_BS4:
            logger.warning("Titrari: beautifulsoup4 not available, cannot search")
            return []

        if not self.session:
            logger.warning("Titrari: cannot search - session is None")
            return []

        # Only search for Romanian
        if query.languages and "ro" not in query.languages:
            return []

        # Build search term
        # The site matches the bare title only; series come as season packs.
        search_term = (
            ((query.series_title or query.title) if query.is_episode else query.title)
            or query.title
            or query.series_title
        )
        if not search_term:
            logger.warning("Titrari: no search term available")
            return []

        logger.debug("Titrari: searching for '%s'", search_term)

        try:
            resp = self.session.get(
                SEARCH_URL,
                params=search_params(search_term),
            )

            if resp.status_code == 403:
                raise ProviderError("Titrari: access blocked (HTTP 403) — IP may be banned")
            if resp.status_code != 200:
                logger.warning("Titrari: search failed with HTTP %d", resp.status_code)
                return []

            return self._parse_search_results(resp.text, query)

        except (ProviderRateLimitError, ProviderAuthError):
            # Re-raise: the coordinator's rate-limit handler + Phase 3 learning
            # need to see these. Swallowing them here hides the 429 from the
            # budget manager and keeps us hammering the endpoint.
            raise
        except ProviderError:
            raise
        except Exception as e:
            logger.error("Titrari: search error: %s", e, exc_info=True)
            return []

    def _parse_search_results(self, html: str, query: VideoQuery) -> list[SubtitleResult]:
        """Turn a search page into results, one per download link."""
        parser = "lxml" if _can_use_lxml() else "html.parser"
        entries = parse_entries(BeautifulSoup(html, parser))
        results = [self._result_from_entry(entry, query) for entry in entries]
        logger.info("Titrari: found %d results", len(results))
        return results

    def _result_from_entry(self, entry, query: VideoQuery) -> SubtitleResult:
        release_name = entry.release_info
        lowered = release_name.lower()
        fmt = SubtitleFormat.SRT
        for ext_str in (".ass", ".ssa", ".srt", ".sub"):
            if ext_str in lowered:
                fmt = _FORMAT_MAP.get(ext_str, SubtitleFormat.SRT)
                break

        matches = set()
        parsed = _parse_episode_info(release_name)
        title = entry.title.lower()
        if query.is_episode:
            series_title = query.series_title or query.title
            if series_title and series_title.lower() in title:
                matches.add("series")
            if season_covered(entry.title, query.season) or parsed.get("season") == query.season:
                matches.add("season")
            if parsed.get("episode") == query.episode and parsed.get("season") == query.season:
                matches.add("episode")
        elif query.is_movie:
            if query.title and query.title.lower() in title:
                matches.add("title")
            if query.year and str(query.year) in entry.title:
                matches.add("year")
        if query.release_group and query.release_group.lower() in lowered:
            matches.add("release_group")
        if query.resolution and parsed.get("resolution") == query.resolution:
            matches.add("resolution")

        return SubtitleResult(
            provider_name=self.name,
            subtitle_id=f"titrari:{entry.subtitle_id}",
            language="ro",
            format=fmt,
            filename=release_name[:100],
            download_url=entry.download_url,
            release_info=release_name,
            matches=matches,
            provider_data={
                "is_detail_page": False,
                "season": query.season if query.is_episode else None,
                "episode": query.episode if query.is_episode else None,
            },
        )

    def download(self, result: SubtitleResult) -> bytes:
        """Download a subtitle from titrari.ro, extracting it from a ZIP/RAR archive.

        For an episode the archive is usually a season pack: the member for the
        requested episode is taken, never simply the first file.
        """
        if not self.session:
            raise RuntimeError("Titrari not initialized")

        url = result.download_url
        if not url:
            raise ValueError("No download URL")

        url_ok, url_err = validate_download_url(url, self.name)
        if not url_ok:
            raise ProviderError(f"Titrari download URL rejected: {url_err}")

        try:
            # P5: 50 MB streaming cap
            # get.php redirects to the listing page unless the request comes from the site.
            content = _stream_download(
                self.session,
                url,
                timeout=self.timeout,
                headers={"Referer": f"{BASE_URL}/"},
                provider_name=self.name,
            )
        except Exception as e:
            raise RuntimeError(f"Titrari download failed: {e}") from e

        entries = None
        if content[:4] == b"PK\x03\x04":
            entries = extract_subtitles_from_zip(content)
        elif content[:4] == b"Rar!":
            try:
                entries = extract_subtitles_from_rar(content)
            except ImportError as e:
                raise ProviderError("Titrari: rarfile not installed, cannot extract RAR") from e
        elif content.lstrip()[:15].lower().startswith((b"<!doctype html", b"<html")):
            raise ProviderError("Titrari: got an HTML page instead of a subtitle")

        if entries is not None:
            season = result.provider_data.get("season")
            episode = result.provider_data.get("episode")
            extracted = pick_episode_member(entries, season, episode)
            if extracted is None:
                wanted = f" for S{season:02d}E{episode:02d}" if season and episode else ""
                raise ProviderError(f"Titrari: archive has no matching subtitle{wanted}")
            filename, content = extracted
            result.filename = filename
            result.format = _detect_format_from_filename(filename)

        result.content = content
        logger.info("Titrari: downloaded %s (%d bytes)", result.filename, len(content))
        return content


def _can_use_lxml() -> bool:
    """Check if lxml parser is available for BeautifulSoup."""
    try:
        import lxml  # noqa: F401

        return True
    except ImportError:
        return False
