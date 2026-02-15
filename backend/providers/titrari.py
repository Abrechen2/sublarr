"""Titrari (titrari.ro) subtitle provider — Romanian subtitles.

HTML scraping provider for Romanian subtitles from titrari.ro.
No authentication required — uses browser-like User-Agent for access.

Handles HTML table parsing with BeautifulSoup and extracts subtitles
from RAR/ZIP archives.

License: GPL-3.0
"""

import io
import os
import re
import logging
import zipfile
from typing import Optional
from urllib.parse import quote_plus, urljoin

from providers.base import (
    SubtitleProvider,
    SubtitleResult,
    SubtitleFormat,
    VideoQuery,
    ProviderError,
)
from providers import register_provider
from providers.http_session import create_session

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

try:
    import rarfile
    _HAS_RARFILE = True
except ImportError:
    _HAS_RARFILE = False
    logger.debug("Titrari: rarfile not installed, RAR archives will not be extractable")

BASE_URL = "https://www.titrari.ro"
SEARCH_URL = f"{BASE_URL}/index.php"

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
            pass

    # Regex fallback
    result = {"season": None, "episode": None, "title": "", "release_group": "", "source": "", "resolution": ""}

    # S01E02 pattern
    m = re.search(r'[Ss](\d{1,2})[Ee](\d{1,3})', text)
    if m:
        result["season"] = int(m.group(1))
        result["episode"] = int(m.group(2))

    # Resolution
    m = re.search(r'(1080p|720p|480p|2160p|4[Kk])', text)
    if m:
        result["resolution"] = m.group(1)

    # Release group (last bracket group)
    m = re.search(r'[-\s](\w+)$', text.strip())
    if m:
        result["release_group"] = m.group(1)

    return result


def _detect_format_from_filename(filename: str) -> SubtitleFormat:
    """Detect subtitle format from filename extension."""
    ext = os.path.splitext(filename)[1].lower()
    return _FORMAT_MAP.get(ext, SubtitleFormat.SRT)


def _extract_subtitle_from_archive(content: bytes) -> Optional[tuple[str, bytes]]:
    """Extract the first subtitle file from a ZIP or RAR archive.

    Returns (filename, content) or None if no subtitle found.
    """
    # ZIP detection
    if content[:4] == b'PK\x03\x04':
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                for name in zf.namelist():
                    ext = os.path.splitext(name)[1].lower()
                    if ext in _SUBTITLE_EXTENSIONS:
                        return (os.path.basename(name), zf.read(name))
        except zipfile.BadZipFile:
            logger.warning("Titrari: bad ZIP archive")
        return None

    # RAR detection
    if content[:4] == b'Rar!':
        if not _HAS_RARFILE:
            logger.warning("Titrari: RAR archive detected but rarfile not installed")
            return None
        try:
            with rarfile.RarFile(io.BytesIO(content)) as rf:
                for name in rf.namelist():
                    ext = os.path.splitext(name)[1].lower()
                    if ext in _SUBTITLE_EXTENSIONS:
                        return (os.path.basename(name), rf.read(name))
        except Exception as e:
            logger.warning("Titrari: RAR extraction failed: %s", e)
        return None

    # Not an archive — return None (caller will treat content as raw subtitle)
    return None


@register_provider
class TitrariProvider(SubtitleProvider):
    """Titrari subtitle provider — Romanian subtitles via HTML scraping."""

    name = "titrari"
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
        self.session.headers.update({
            "Accept-Language": "ro-RO,ro;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
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
        if query.is_episode:
            search_term = f"{query.series_title or query.title} S{query.season:02d}E{query.episode:02d}"
        elif query.is_movie:
            search_term = query.title
            if query.year:
                search_term += f" {query.year}"
        else:
            search_term = query.title or query.series_title
            if not search_term:
                logger.warning("Titrari: no search term available")
                return []

        logger.debug("Titrari: searching for '%s'", search_term)

        try:
            resp = self.session.get(SEARCH_URL, params={
                "page": "cautare",
                "titlufilm": search_term,
            })

            if resp.status_code == 403:
                raise ProviderError("Titrari: access blocked (HTTP 403) — IP may be banned")
            if resp.status_code != 200:
                logger.warning("Titrari: search failed with HTTP %d", resp.status_code)
                return []

            return self._parse_search_results(resp.text, query)

        except ProviderError:
            raise
        except Exception as e:
            logger.error("Titrari: search error: %s", e, exc_info=True)
            return []

    def _parse_search_results(self, html: str, query: VideoQuery) -> list[SubtitleResult]:
        """Parse HTML search results page into SubtitleResult objects."""
        results = []
        parser = "lxml" if _can_use_lxml() else "html.parser"
        soup = BeautifulSoup(html, parser)

        # Titrari renders results in HTML tables
        # Look for result rows — try multiple selectors for resilience
        rows = soup.find_all("tr")
        if not rows:
            # Try div-based layout as fallback
            rows = soup.find_all("div", class_=re.compile(r"result|subtitle|entry", re.I))

        if not rows:
            logger.debug("Titrari: no result rows found in HTML")
            return []

        for row in rows:
            try:
                result = self._parse_result_row(row, query)
                if result:
                    results.append(result)
            except Exception as e:
                logger.warning("Titrari: failed to parse result row: %s", e)
                continue

        logger.info("Titrari: found %d results", len(results))
        return results

    def _parse_result_row(self, row, query: VideoQuery) -> Optional[SubtitleResult]:
        """Parse a single result row into a SubtitleResult.

        Returns None if the row is not a valid subtitle result.
        """
        # Extract all links in the row
        links = row.find_all("a", href=True)
        if not links:
            return None

        # Look for a download link
        download_url = ""
        detail_url = ""
        release_name = ""

        for link in links:
            href = link.get("href", "")
            text = link.get_text(strip=True)

            # Download links typically contain 'download' or end with archive extensions
            if "download" in href.lower() or any(href.lower().endswith(ext) for ext in [".zip", ".rar", ".srt"]):
                download_url = urljoin(BASE_URL, href)
            elif href and text and len(text) > 3:
                # Likely a subtitle title/detail link
                detail_url = urljoin(BASE_URL, href)
                if not release_name:
                    release_name = text

        # If no download URL found, use the detail URL (we'll resolve it during download)
        if not download_url and not detail_url:
            return None

        effective_url = download_url or detail_url

        # Get the full text content for release name matching
        row_text = row.get_text(" ", strip=True)
        if not release_name:
            release_name = row_text[:200]  # cap at reasonable length

        # Skip header/navigation rows
        if len(release_name) < 3 or release_name.lower() in ("titlu", "titlul", "descarca", "download"):
            return None

        # Detect format from filename or default to SRT
        fmt = SubtitleFormat.SRT
        for ext_str in [".ass", ".ssa", ".srt", ".sub"]:
            if ext_str in release_name.lower():
                fmt = _FORMAT_MAP.get(ext_str, SubtitleFormat.SRT)
                break

        # Build matches
        matches = set()
        parsed = _parse_episode_info(release_name)

        if query.is_episode:
            series_title = query.series_title or query.title
            if series_title and series_title.lower() in release_name.lower():
                matches.add("series")
            if parsed.get("season") == query.season:
                matches.add("season")
            if parsed.get("episode") == query.episode:
                matches.add("episode")
        elif query.is_movie:
            if query.title and query.title.lower() in release_name.lower():
                matches.add("title")
            if query.year and str(query.year) in release_name:
                matches.add("year")

        if query.release_group and query.release_group.lower() in release_name.lower():
            matches.add("release_group")
        if query.resolution and parsed.get("resolution") == query.resolution:
            matches.add("resolution")

        # Generate a unique subtitle ID from the URL
        subtitle_id = effective_url.split("/")[-1] if "/" in effective_url else effective_url

        return SubtitleResult(
            provider_name=self.name,
            subtitle_id=f"titrari:{subtitle_id}",
            language="ro",
            format=fmt,
            filename=release_name[:100],
            download_url=effective_url,
            release_info=release_name,
            matches=matches,
            provider_data={
                "is_detail_page": not download_url,
                "detail_url": detail_url,
            },
        )

    def download(self, result: SubtitleResult) -> bytes:
        """Download a subtitle from titrari.ro.

        Handles both direct downloads and detail page resolution,
        plus RAR/ZIP archive extraction.
        """
        if not self.session:
            raise RuntimeError("Titrari not initialized")

        url = result.download_url
        if not url:
            raise ValueError("No download URL")

        # If the URL points to a detail page, fetch it and find the actual download link
        if result.provider_data.get("is_detail_page"):
            url = self._resolve_download_url(url)
            if not url:
                raise ProviderError("Titrari: could not find download link on detail page")

        resp = self.session.get(url)
        if resp.status_code == 403:
            raise ProviderError("Titrari: download blocked (HTTP 403)")
        if resp.status_code != 200:
            raise RuntimeError(f"Titrari download failed: HTTP {resp.status_code}")

        content = resp.content

        # Try to extract from archive
        extracted = _extract_subtitle_from_archive(content)
        if extracted:
            filename, content = extracted
            result.filename = filename
            result.format = _detect_format_from_filename(filename)

        result.content = content
        logger.info("Titrari: downloaded %s (%d bytes)", result.filename, len(content))
        return content

    def _resolve_download_url(self, detail_url: str) -> Optional[str]:
        """Fetch a detail page and extract the actual download link."""
        if not _HAS_BS4:
            return None

        try:
            resp = self.session.get(detail_url)
            if resp.status_code != 200:
                return None

            parser = "lxml" if _can_use_lxml() else "html.parser"
            soup = BeautifulSoup(resp.text, parser)

            # Look for download links on the detail page
            for link in soup.find_all("a", href=True):
                href = link.get("href", "")
                text = (link.get_text(strip=True) or "").lower()
                if "download" in href.lower() or "descarca" in text.lower():
                    return urljoin(BASE_URL, href)

            # Fallback: look for links to archive files
            for link in soup.find_all("a", href=True):
                href = link.get("href", "")
                if any(href.lower().endswith(ext) for ext in [".zip", ".rar", ".srt", ".ass"]):
                    return urljoin(BASE_URL, href)

        except Exception as e:
            logger.warning("Titrari: failed to resolve download URL: %s", e)

        return None


def _can_use_lxml() -> bool:
    """Check if lxml parser is available for BeautifulSoup."""
    try:
        import lxml  # noqa: F401
        return True
    except ImportError:
        return False
