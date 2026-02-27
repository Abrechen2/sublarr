"""Kitsunekko subtitle provider -- scrapes directory listings for Japanese anime subs.

Kitsunekko.net hosts a large collection of Japanese anime subtitles contributed
by fansub groups. The site provides a directory-listing interface where subtitle
files (.ass, .srt, .zip) are organized by series name.

Site: https://kitsunekko.net
No authentication required.
License: GPL-3.0
"""

import io
import logging
import os
import re
import zipfile
from urllib.parse import quote, urljoin

from providers import register_provider
from providers.base import (
    ProviderError,
    SubtitleFormat,
    SubtitleProvider,
    SubtitleResult,
    VideoQuery,
)
from providers.http_session import create_session

logger = logging.getLogger(__name__)

# Conditional BeautifulSoup import
try:
    from bs4 import BeautifulSoup

    _BS4_AVAILABLE = True
except ImportError:
    _BS4_AVAILABLE = False
    logger.warning(
        "Kitsunekko: beautifulsoup4 not installed -- provider will be non-functional. "
        "Install with: pip install beautifulsoup4"
    )

BASE_URL = "https://kitsunekko.net"
DIRLIST_URL = f"{BASE_URL}/dirlist.php"

_SUBTITLE_EXTENSIONS = {".ass", ".srt", ".ssa", ".zip"}
_FORMAT_MAP = {
    ".ass": SubtitleFormat.ASS,
    ".ssa": SubtitleFormat.SSA,
    ".srt": SubtitleFormat.SRT,
}

# Reuse episode number extraction patterns (similar to animetosho)
_EPISODE_PATTERNS = [
    r"[\s_]-[\s_](\d{2,3})(?:v\d)?[\s_\[\(.]",  # " - 01 " or " - 01v2 "
    r"[Ee][Pp]?(\d{2,3})(?:v\d)?[\s_\[\(.]",  # E01, EP01
    r"[\s_](\d{2,3})(?:v\d)?[\s_]?(?:\[|\(|\.(?:ass|srt|ssa|zip))",  # " 01." file ext
    r"[\s_](\d{2,3})(?:v\d)?$",  # trailing episode number
]


def _extract_episode_number(text: str) -> int | None:
    """Try to extract episode number from a filename."""
    for pattern in _EPISODE_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                continue
    return None


def _normalize_series_title(title: str) -> str:
    """Normalize a series title for URL path construction.

    Kitsunekko uses directory names that may vary in formatting.
    Try a simple approach: preserve the title as-is but URL-encode it.
    """
    return title.strip()


@register_provider
class KitsunekkoProvider(SubtitleProvider):
    """Kitsunekko subtitle provider -- scrapes HTML directory listings for Japanese anime subs."""

    name = "kitsunekko"
    languages = {"ja"}

    # Plugin system attributes
    config_fields = []  # no auth needed
    rate_limit = (10, 60)  # polite scraping: 10 requests per minute
    timeout = 20
    max_retries = 2

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.session = None

    def initialize(self):
        logger.debug("Kitsunekko: initializing (no API key required)")
        self.session = create_session(
            max_retries=2,
            backoff_factor=1.0,
            timeout=20,
            user_agent="Sublarr/1.0",
        )

    def terminate(self):
        if self.session:
            self.session.close()
            self.session = None

    def health_check(self) -> tuple[bool, str]:
        if not self.session:
            return False, "Not initialized"
        try:
            resp = self.session.get(BASE_URL, timeout=10)
            if resp.status_code == 200:
                return True, "OK"
            return False, f"HTTP {resp.status_code}"
        except Exception as e:
            return False, str(e)

    def search(self, query: VideoQuery) -> list[SubtitleResult]:
        if not self.session:
            logger.warning("Kitsunekko: cannot search -- session is None")
            return []

        if not _BS4_AVAILABLE:
            logger.warning("Kitsunekko: beautifulsoup4 not installed, skipping search")
            return []

        # Only search for Japanese language
        if query.languages and "ja" not in query.languages:
            logger.debug("Kitsunekko: skipping -- 'ja' not in requested languages %s", query.languages)
            return []

        series_title = query.series_title or query.title
        if not series_title:
            logger.warning("Kitsunekko: no series title to search for")
            return []

        logger.debug("Kitsunekko: searching for '%s'", series_title)

        # Try multiple title variations
        title_variations = self._generate_title_variations(series_title)
        results = []

        for title_variant in title_variations:
            variant_results = self._search_directory(title_variant, query)
            if variant_results:
                results.extend(variant_results)
                break  # Found results, no need to try other variations

        logger.info("Kitsunekko: found %d subtitle results for '%s'", len(results), series_title)
        return results

    def _generate_title_variations(self, title: str) -> list[str]:
        """Generate title variations to try against Kitsunekko directory names."""
        variations = [title]

        # Try with spaces replaced by underscores and vice versa
        if " " in title:
            variations.append(title.replace(" ", "_"))
        if "_" in title:
            variations.append(title.replace("_", " "))

        # Try lowercase
        lower = title.lower()
        if lower != title:
            variations.append(lower)

        return variations

    def _search_directory(self, series_title: str, query: VideoQuery) -> list[SubtitleResult]:
        """Fetch and parse a Kitsunekko directory listing for subtitle files."""
        encoded_title = quote(series_title, safe="")
        dir_path = f"subtitles/japanese/{encoded_title}/"
        url = f"{DIRLIST_URL}?dir={dir_path}"

        try:
            resp = self.session.get(url, timeout=self.timeout)
            if resp.status_code == 404:
                logger.debug("Kitsunekko: directory not found for '%s'", series_title)
                return []
            if resp.status_code == 403:
                logger.warning("Kitsunekko: access denied (403) for '%s'", series_title)
                return []
            if resp.status_code != 200:
                logger.warning("Kitsunekko: HTTP %d for '%s'", resp.status_code, series_title)
                return []
        except Exception as e:
            logger.warning("Kitsunekko: request failed for '%s': %s", series_title, e)
            return []

        return self._parse_directory_listing(resp.text, dir_path, query)

    def _parse_directory_listing(
        self, html: str, dir_path: str, query: VideoQuery
    ) -> list[SubtitleResult]:
        """Parse an HTML directory listing page and extract subtitle file links."""
        results = []

        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception as e:
            logger.warning("Kitsunekko: HTML parse error: %s", e)
            return []

        # Find all links in the directory listing
        links = soup.find_all("a", href=True)
        if not links:
            logger.debug("Kitsunekko: no links found in directory listing")
            return []

        for link in links:
            href = link.get("href", "")
            if not href:
                continue

            # Get filename from the link
            filename = href.rsplit("/", 1)[-1] if "/" in href else href
            if not filename:
                continue

            # Check file extension
            _, ext = os.path.splitext(filename.lower())
            if ext not in _SUBTITLE_EXTENSIONS:
                continue

            # Try to match episode number
            file_episode = _extract_episode_number(filename)

            # Filter by episode if query has season/episode
            if query.episode is not None and file_episode is not None:
                if file_episode != query.episode:
                    continue

            # Build download URL
            if href.startswith("http"):
                download_url = href
            else:
                download_url = urljoin(BASE_URL + "/", href)

            # Determine format
            if ext == ".zip":
                # ZIP archives -- format determined after extraction
                fmt = SubtitleFormat.ASS  # Assume ASS (common for Japanese subs)
            else:
                fmt = _FORMAT_MAP.get(ext, SubtitleFormat.UNKNOWN)

            # Build matches
            matches = {"series"}  # Matched by directory name
            if query.episode is not None and file_episode is not None and file_episode == query.episode:
                matches.add("episode")

            result = SubtitleResult(
                provider_name=self.name,
                subtitle_id=f"kitsunekko:{dir_path}{filename}",
                language="ja",
                format=fmt,
                filename=filename,
                download_url=download_url,
                matches=matches,
                provider_data={
                    "dir_path": dir_path,
                    "is_zip": ext == ".zip",
                },
            )
            results.append(result)

        return results

    def download(self, result: SubtitleResult) -> bytes:
        if not self.session:
            raise ProviderError("Kitsunekko not initialized")

        url = result.download_url
        if not url:
            raise ValueError("No download URL")

        try:
            resp = self.session.get(url, timeout=self.timeout)
            if resp.status_code != 200:
                raise ProviderError(f"Kitsunekko download failed: HTTP {resp.status_code}")
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError(f"Kitsunekko download error: {e}") from e

        content = resp.content

        # Handle ZIP archives: extract first subtitle file
        if result.provider_data.get("is_zip") or content[:4] == b"PK\x03\x04":
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as zf:
                    # Prefer .ass files, then .srt, then .ssa
                    subtitle_files = []
                    for name in zf.namelist():
                        file_ext = os.path.splitext(name)[1].lower()
                        if file_ext in {".ass", ".srt", ".ssa"}:
                            # Priority: .ass=0 (highest), .srt=1, .ssa=2
                            priority = {".ass": 0, ".srt": 1, ".ssa": 2}.get(file_ext, 3)
                            subtitle_files.append((priority, name, file_ext))

                    if subtitle_files:
                        subtitle_files.sort()
                        _, best_name, best_ext = subtitle_files[0]
                        content = zf.read(best_name)
                        result.filename = os.path.basename(best_name)
                        result.format = _FORMAT_MAP.get(best_ext, SubtitleFormat.UNKNOWN)
                    else:
                        logger.warning("Kitsunekko: ZIP contains no subtitle files")
            except zipfile.BadZipFile:
                logger.debug("Kitsunekko: content is not a valid ZIP, using as-is")

        result.content = content
        logger.info("Kitsunekko: downloaded %s (%d bytes)", result.filename, len(content))
        return content
