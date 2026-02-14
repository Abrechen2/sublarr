"""AnimeTosho subtitle provider — extracts subtitles from anime releases.

AnimeTosho automatically mirrors anime torrents and extracts embedded
subtitles. Great source for high-quality fansub ASS files.

Architecture adapted from Bazarr's subliminal_patch animetosho provider (GPL-3.0).
API: https://feed.animetosho.org/
"""

import io
import os
import re
import lzma
import zipfile
import logging

from providers.base import (
    SubtitleProvider,
    SubtitleResult,
    SubtitleFormat,
    VideoQuery,
)
from providers import register_provider
from providers.http_session import create_session

logger = logging.getLogger(__name__)

FEED_API = "https://feed.animetosho.org/json"

_SUBTITLE_EXTENSIONS = {".ass", ".srt", ".ssa"}
_FORMAT_MAP = {
    ".ass": SubtitleFormat.ASS,
    ".ssa": SubtitleFormat.SSA,
    ".srt": SubtitleFormat.SRT,
}


def _decompress_xz(data: bytes) -> bytes:
    """Decompress XZ/LZMA compressed data."""
    try:
        return lzma.decompress(data)
    except lzma.LZMAError as e:
        logger.warning("AnimeTosho: XZ decompression failed: %s", e)
        raise


def _extract_episode_number(text: str) -> int | None:
    """Try to extract episode number from a release name."""
    # Common patterns: " - 01 ", " E01 ", " EP01 ", "_01_", " 01v2 "
    patterns = [
        r'[\s_]-[\s_](\d{2,3})(?:v\d)?[\s_\[\(.]',  # " - 01 " or " - 01v2 "
        r'[Ee][Pp]?(\d{2,3})(?:v\d)?[\s_\[\(.]',  # E01, EP01
        r'[\s_](\d{2,3})(?:v\d)?[\s_]?(?:\[|\(|\.(?:mkv|mp4))',  # " 01 [" or " 01."
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                continue
    return None


@register_provider
class AnimeToshoProvider(SubtitleProvider):
    """AnimeTosho subtitle provider."""

    name = "animetosho"
    languages = {
        "en", "ja", "de", "fr", "es", "it", "pt", "ru", "zh", "ko",
        "ar", "nl", "pl", "sv", "cs", "hu", "tr",
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.session = None

    def initialize(self):
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
            resp = self.session.get(FEED_API, params={"q": "test", "num": 1})
            if resp.status_code == 200:
                return True, "OK"
            return False, f"HTTP {resp.status_code}"
        except Exception as e:
            return False, str(e)

    def search(self, query: VideoQuery) -> list[SubtitleResult]:
        if not self.session:
            return []

        results = []

        # Build search query
        search_term = ""
        if query.is_episode:
            search_term = query.series_title or query.title
            if query.episode is not None:
                # AnimeTosho works best with episode number in search
                search_term += f" {query.episode:02d}"
        elif query.is_movie:
            search_term = query.title

        if not search_term:
            return []

        # Search AnimeTosho feed API
        try:
            params = {
                "q": search_term,
                "num": 30,  # Max results
                "aids": 0,  # Use 0 for server caching
            }

            # AniDB ID provides more accurate results
            if query.anidb_id:
                params["aid"] = query.anidb_id

            resp = self.session.get(FEED_API, params=params)
            if resp.status_code != 200:
                logger.warning("AnimeTosho search failed: HTTP %d", resp.status_code)
                return []

            entries = resp.json()
            if not isinstance(entries, list):
                return []

            for entry in entries:
                entry_results = self._process_entry(entry, query)
                results.extend(entry_results)

        except Exception as e:
            logger.error("AnimeTosho search error: %s", e)

        logger.info("AnimeTosho: found %d subtitle results", len(results))
        return results

    def _process_entry(self, entry: dict, query: VideoQuery) -> list[SubtitleResult]:
        """Process a single AnimeTosho entry and extract subtitle info."""
        results = []

        title = entry.get("title", "")
        entry_id = entry.get("id", 0)

        # Check for subtitle attachments
        files = entry.get("files", [])
        if not files:
            return []

        # Try to match episode number
        entry_episode = _extract_episode_number(title)
        episode_match = (
            query.episode is not None
            and entry_episode is not None
            and entry_episode == query.episode
        )

        for f in files:
            filename = f.get("name", "")
            ext = os.path.splitext(filename)[1].lower()

            if ext not in _SUBTITLE_EXTENSIONS:
                continue

            # Build download URL
            # AnimeTosho stores subtitles as attachments, often XZ-compressed
            download_url = f.get("url", "")
            if not download_url:
                continue

            fmt = _FORMAT_MAP.get(ext, SubtitleFormat.UNKNOWN)

            # Detect language from filename
            lang = self._detect_language(filename, title)

            # Check if language matches query
            if query.languages and lang not in query.languages:
                continue

            # Build matches
            matches = set()
            series_title = query.series_title or query.title
            if series_title and series_title.lower() in title.lower():
                matches.add("series")
            if episode_match:
                matches.add("episode")
            if query.anidb_id:
                matches.add("series")  # AniDB match is a strong signal
            if query.release_group and query.release_group.lower() in title.lower():
                matches.add("release_group")
            # Check resolution
            for res in ["1080p", "720p", "480p", "2160p"]:
                if res in title:
                    if query.resolution == res:
                        matches.add("resolution")
                    break

            result = SubtitleResult(
                provider_name=self.name,
                subtitle_id=f"{entry_id}:{filename}",
                language=lang,
                format=fmt,
                filename=filename,
                download_url=download_url,
                release_info=title,
                matches=matches,
                provider_data={
                    "entry_id": entry_id,
                    "entry_title": title,
                    "is_xz": download_url.endswith(".xz"),
                },
            )
            results.append(result)

        return results

    def _detect_language(self, filename: str, release_title: str = "") -> str:
        """Detect language from subtitle filename and release context."""
        name_lower = filename.lower()
        title_lower = release_title.lower()

        # Explicit language tags in filename (check filename first, then title)
        lang_patterns = {
            "ja": [".ja.", ".jpn.", ".japanese.", "_ja_", "_jpn_", "[ja]", "[jpn]"],
            "en": [".en.", ".eng.", ".english.", "_en_", "_eng_", "[en]", "[eng]"],
            "de": [".de.", ".deu.", ".ger.", ".german.", "_de_", "_deu_", "[de]", "[deu]", "[ger]", ".german"],
            "fr": [".fr.", ".fra.", ".fre.", ".french.", "_fr_", "[fr]", "[fra]"],
            "es": [".es.", ".spa.", ".spanish.", "_es_", "[es]", "[spa]"],
            "zh": [".zh.", ".chi.", ".chinese.", "_zh_", "[zh]", "[chi]"],
        }

        # Check filename first
        for lang, patterns in lang_patterns.items():
            if any(p in name_lower for p in patterns):
                return lang

        # Check release title for language tags
        for lang, patterns in lang_patterns.items():
            if any(p in title_lower for p in patterns):
                return lang

        # Check for common German fansub groups
        german_groups = ["kametsu", "anime4you", "anime-loads", "animebase", "animefreakz"]
        if any(group in title_lower for group in german_groups):
            return "de"

        # Check for common English fansub groups
        english_groups = [
            "subsplease", "erai-raws", "horriblesubs", "judas",
            "sallysubs", "yameii", "ember", "yor", "commie",
            "gg", "coal", "doki", "fumetsu", "utw", "asenshi"
        ]
        if any(group in title_lower for group in english_groups):
            return "en"

        # Default assumption for AnimeTosho (most fansubs are English)
        return "en"

    def download(self, result: SubtitleResult) -> bytes:
        if not self.session:
            raise RuntimeError("AnimeTosho not initialized")

        url = result.download_url
        if not url:
            raise ValueError("No download URL")

        resp = self.session.get(url)
        if resp.status_code != 200:
            raise RuntimeError(f"AnimeTosho download failed: HTTP {resp.status_code}")

        content = resp.content

        # Handle XZ compression
        if result.provider_data.get("is_xz") or url.endswith(".xz"):
            content = _decompress_xz(content)

        # Handle ZIP if the downloaded file is actually a ZIP
        if content[:4] == b'PK\x03\x04':
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as zf:
                    for name in zf.namelist():
                        ext = os.path.splitext(name)[1].lower()
                        if ext in _SUBTITLE_EXTENSIONS:
                            content = zf.read(name)
                            result.filename = os.path.basename(name)
                            result.format = _FORMAT_MAP.get(ext, SubtitleFormat.UNKNOWN)
                            break
            except zipfile.BadZipFile:
                pass  # Not a ZIP, use content as-is

        result.content = content
        logger.info("AnimeTosho: downloaded %s (%d bytes)", result.filename, len(content))
        return content
