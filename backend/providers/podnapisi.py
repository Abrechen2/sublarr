"""Podnapisi subtitle provider -- XML API for European language subtitles.

Podnapisi.net offers broad subtitle coverage with a focus on European
languages, especially Slavic languages. Uses an XML search API and
returns subtitles as ZIP archives.

API Base: https://www.podnapisi.net
Auth: None required
Rate limit: Conservative 30 req/60s
License: GPL-3.0
"""

import io
import logging
import os
import zipfile

from providers import register_provider
from providers.base import (
    ProviderRateLimitError,
    SubtitleFormat,
    SubtitleProvider,
    SubtitleResult,
    VideoQuery,
)
from providers.http_session import create_session

logger = logging.getLogger(__name__)

API_BASE = "https://www.podnapisi.net"

_SUBTITLE_EXTENSIONS = {".ass", ".srt", ".ssa", ".vtt", ".sub"}
_FORMAT_MAP = {
    ".ass": SubtitleFormat.ASS,
    ".ssa": SubtitleFormat.SSA,
    ".srt": SubtitleFormat.SRT,
    ".vtt": SubtitleFormat.VTT,
}

# Podnapisi uses numeric language codes.
# Mapping from ISO 639-1 to Podnapisi language IDs.
_LANG_TO_PODNAPISI = {
    "en": 2,    # English
    "de": 14,   # German
    "fr": 8,    # French
    "es": 28,   # Spanish
    "it": 9,    # Italian
    "pt": 26,   # Portuguese
    "sl": 1,    # Slovenian
    "hr": 38,   # Croatian
    "sr": 36,   # Serbian
    "bs": 42,   # Bosnian
    "cs": 7,    # Czech
    "sk": 37,   # Slovak
    "pl": 23,   # Polish
    "hu": 20,   # Hungarian
    "ro": 13,   # Romanian
    "bg": 33,   # Bulgarian
    "tr": 30,   # Turkish
    "el": 16,   # Greek
    "nl": 15,   # Dutch
    "sv": 25,   # Swedish
    "da": 24,   # Danish
    "no": 22,   # Norwegian
    "fi": 17,   # Finnish
    "ru": 27,   # Russian
    "ar": 12,   # Arabic
    "zh": 17,   # Chinese (simplified)
    "ja": 11,   # Japanese
    "ko": 4,    # Korean
    "he": 18,   # Hebrew
    "uk": 40,   # Ukrainian
    "et": 34,   # Estonian
    "lv": 39,   # Latvian
    "lt": 21,   # Lithuanian
    "fa": 52,   # Persian
    "vi": 45,   # Vietnamese
    "id": 47,   # Indonesian
    "th": 44,   # Thai
    "mk": 35,   # Macedonian
    "sq": 41,   # Albanian
    "ca": 53,   # Catalan
    "eu": 54,   # Basque
    "gl": 55,   # Galician
}

# Reverse mapping: Podnapisi ID -> ISO 639-1 code
_PODNAPISI_TO_LANG = {v: k for k, v in _LANG_TO_PODNAPISI.items()}


def _parse_xml(content: bytes):
    """Parse XML content, preferring lxml for performance.

    Falls back to stdlib xml.etree.ElementTree if lxml is not available.
    """
    try:
        from lxml import etree
        return etree.fromstring(content)
    except ImportError:
        logger.debug("Podnapisi: lxml not available, using stdlib xml.etree (performance may be degraded)")
        import xml.etree.ElementTree as ET
        return ET.fromstring(content)


def _extract_from_zip(archive_content: bytes) -> tuple[str, bytes] | None:
    """Extract the first subtitle file from a ZIP archive.

    Returns (filename, content) or None if no subtitle file found.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(archive_content)) as zf:
            for name in zf.namelist():
                if name.endswith("/"):
                    continue
                ext = os.path.splitext(name)[1].lower()
                if ext in _SUBTITLE_EXTENSIONS:
                    content = zf.read(name)
                    return os.path.basename(name), content
    except zipfile.BadZipFile:
        logger.warning("Podnapisi: bad ZIP archive")
    return None


@register_provider
class PodnapisiProvider(SubtitleProvider):
    """Podnapisi subtitle provider (XML API).

    Searches the Podnapisi.net database via their XML search endpoint.
    European language focus with broad coverage.
    """

    name = "podnapisi"
    languages = {
        "en", "de", "fr", "es", "it", "pt", "sl", "hr", "sr", "bs",
        "cs", "sk", "pl", "hu", "ro", "bg", "tr", "el", "nl", "sv",
        "da", "no", "fi", "ru", "ar", "zh", "ja", "ko", "he", "uk",
        "et", "lv", "lt", "fa", "vi", "id", "th", "mk", "sq", "ca",
        "eu", "gl",
    }

    # Plugin system attributes
    config_fields = []  # no auth required
    rate_limit = (30, 60)
    timeout = 15
    max_retries = 2

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.session = None

    def initialize(self):
        logger.debug("Podnapisi: initializing (no API key required)")
        self.session = create_session(
            max_retries=2,
            backoff_factor=1.0,
            timeout=15,
            user_agent="Sublarr/1.0",
        )
        logger.debug("Podnapisi: session created successfully")

    def terminate(self):
        if self.session:
            self.session.close()
            self.session = None

    def health_check(self) -> tuple[bool, str]:
        if not self.session:
            return False, "Not initialized"
        try:
            resp = self.session.get(
                f"{API_BASE}/subtitles/search/old",
                params={"sXML": 1, "sK": "test", "sJ": 1},
            )
            if resp.status_code == 200 and resp.content:
                # Verify we got XML back
                try:
                    _parse_xml(resp.content)
                    return True, "OK"
                except Exception:
                    return False, "Invalid XML response"
            return False, f"HTTP {resp.status_code}"
        except Exception as e:
            return False, str(e)

    def search(self, query: VideoQuery) -> list[SubtitleResult]:
        if not self.session:
            logger.warning("Podnapisi: cannot search - session is None")
            return []

        logger.debug("Podnapisi: searching for %s (languages: %s)",
                     query.display_name, query.languages)

        # Build search keyword
        search_term = query.series_title or query.title
        if not search_term:
            logger.warning("Podnapisi: no search term available")
            return []

        # Build query params
        params = {
            "sXML": 1,     # XML response format
            "sK": search_term,
        }

        # Season/Episode
        if query.season is not None:
            params["sTS"] = query.season
        if query.episode is not None:
            params["sTE"] = query.episode

        # Year
        if query.year:
            params["sY"] = query.year

        # Language filter -- Podnapisi supports multiple language codes
        if query.languages:
            lang_ids = []
            for lang_code in query.languages:
                pod_id = _LANG_TO_PODNAPISI.get(lang_code)
                if pod_id is not None:
                    lang_ids.append(str(pod_id))
            if lang_ids:
                params["sL"] = ",".join(lang_ids)

        results = []
        try:
            resp = self.session.get(f"{API_BASE}/subtitles/search/old", params=params)

            if resp.status_code == 429:
                raise ProviderRateLimitError("Podnapisi rate limit exceeded")

            if resp.status_code != 200:
                logger.warning("Podnapisi search failed: HTTP %d", resp.status_code)
                return []

            if not resp.content:
                logger.debug("Podnapisi: empty response")
                return []

            # Parse XML response
            try:
                root = _parse_xml(resp.content)
            except Exception as e:
                logger.error("Podnapisi: failed to parse XML response: %s", e)
                return []

            # Find subtitle entries
            # Podnapisi XML structure: <results><subtitle>...</subtitle></results>
            # or may use namespaces
            subtitles = root.findall(".//subtitle")
            if not subtitles:
                # Try without namespace
                subtitles = root.findall("subtitle")

            logger.debug("Podnapisi: found %d subtitle entries in XML", len(subtitles))

            for sub_elem in subtitles:
                try:
                    result = self._parse_subtitle_element(sub_elem, query)
                    if result:
                        results.append(result)
                except Exception as e:
                    logger.debug("Podnapisi: error parsing subtitle element: %s", e)

        except ProviderRateLimitError:
            raise
        except Exception as e:
            logger.error("Podnapisi search error: %s", e, exc_info=True)

        logger.info("Podnapisi: found %d subtitle results", len(results))
        if results:
            logger.debug("Podnapisi: top result - %s (format: %s, language: %s)",
                        results[0].filename, results[0].format.value, results[0].language)
        return results

    def _parse_subtitle_element(self, elem, query: VideoQuery) -> SubtitleResult | None:
        """Parse a single <subtitle> XML element into a SubtitleResult."""
        # Extract fields from XML element
        pid = self._get_text(elem, "pid")
        if not pid:
            # Try 'id' as fallback
            pid = self._get_text(elem, "id")
        if not pid:
            return None

        release = self._get_text(elem, "release") or ""
        title = self._get_text(elem, "title") or ""
        lang_code_str = self._get_text(elem, "language") or ""
        flags = self._get_text(elem, "flags") or ""
        downloads_str = self._get_text(elem, "downloads") or "0"

        # Map Podnapisi language code to ISO 639-1
        # Podnapisi may return either the numeric ID or a 2-letter code
        lang_iso = ""
        try:
            lang_id = int(lang_code_str)
            lang_iso = _PODNAPISI_TO_LANG.get(lang_id, "")
        except (ValueError, TypeError):
            # Might already be an ISO code
            if len(lang_code_str) == 2:
                lang_iso = lang_code_str.lower()

        if not lang_iso:
            lang_iso = "en"  # Default if language detection fails

        # Filter by requested languages
        if query.languages and lang_iso not in query.languages:
            return None

        # Detect format from release info
        fmt = SubtitleFormat.SRT  # Default for Podnapisi
        if release:
            ext = os.path.splitext(release)[1].lower()
            fmt = _FORMAT_MAP.get(ext, SubtitleFormat.SRT)

        # Build download URL
        download_url = f"{API_BASE}/subtitles/{pid}/download"

        # Build matches
        matches = set()
        search_title = (query.series_title or query.title or "").lower()

        # Title/series match
        if search_title:
            combined_text = f"{release} {title}".lower()
            if search_title in combined_text or any(
                word in combined_text for word in search_title.split() if len(word) > 2
            ):
                matches.add("series" if query.is_episode else "title")

        # Season match
        if query.season is not None:
            # We searched with sTS, so if results came back they likely match
            matches.add("season")

        # Episode match
        if query.episode is not None:
            matches.add("episode")

        # Year match
        if query.year:
            year_str = str(query.year)
            if year_str in release or year_str in title:
                matches.add("year")

        # Hearing impaired detection from flags
        hearing_impaired = "n" in flags.lower() or "hearing" in flags.lower()

        # Parse download count for provider_data
        try:
            download_count = int(downloads_str)
        except (ValueError, TypeError):
            download_count = 0

        filename = release if release else f"{pid}.srt"

        return SubtitleResult(
            provider_name=self.name,
            subtitle_id=str(pid),
            language=lang_iso,
            format=fmt,
            filename=filename,
            download_url=download_url,
            release_info=release,
            matches=matches,
            hearing_impaired=hearing_impaired,
            provider_data={
                "pid": pid,
                "title": title,
                "downloads": download_count,
            },
        )

    @staticmethod
    def _get_text(elem, tag: str) -> str | None:
        """Safely get text content of a child element."""
        child = elem.find(tag)
        if child is not None and child.text:
            return child.text.strip()
        return None

    def download(self, result: SubtitleResult) -> bytes:
        if not self.session:
            raise RuntimeError("Podnapisi not initialized")

        url = result.download_url
        if not url:
            pid = result.provider_data.get("pid") or result.subtitle_id
            url = f"{API_BASE}/subtitles/{pid}/download"

        resp = self.session.get(url, allow_redirects=True)

        if resp.status_code == 429:
            raise ProviderRateLimitError("Podnapisi download rate limited")

        if resp.status_code != 200:
            raise RuntimeError(f"Podnapisi download failed: HTTP {resp.status_code}")

        content = resp.content

        # Podnapisi returns ZIP archives -- extract the first subtitle file
        if content[:4] == b'PK\x03\x04':
            extracted = _extract_from_zip(content)
            if extracted:
                filename, sub_content = extracted
                result.filename = filename
                ext = os.path.splitext(filename)[1].lower()
                result.format = _FORMAT_MAP.get(ext, SubtitleFormat.SRT)
                content = sub_content
            else:
                raise RuntimeError("No subtitle file found in Podnapisi ZIP archive")
        else:
            # Not a ZIP -- treat as raw subtitle file
            logger.debug("Podnapisi: download was not a ZIP, using raw content")

        result.content = content
        logger.info("Podnapisi: downloaded %s (%d bytes)", result.filename, len(content))
        return content
