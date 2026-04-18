"""Pure helpers + constants for LegendasDivxProvider.

Extracted from providers/legendasdivx.py. Covers module-level values
that don't depend on the provider instance:

- URL endpoints (BASE_URL / LOGIN_URL / SEARCH_URL)
- Daily-search-limit thresholds
- Format tables (_SUBTITLE_EXTENSIONS / _FORMAT_MAP)
- Browser UA string
- Availability probes for bs4 / guessit
- Parsing helpers (_can_use_lxml, _parse_episode_info,
  _detect_format_from_filename)
"""

import logging
import os
import re

from providers.base import SubtitleFormat

logger = logging.getLogger(__name__)


# Conditional imports with graceful fallback
try:
    from bs4 import BeautifulSoup  # noqa: F401 — import checked via _HAS_BS4

    _HAS_BS4 = True
except ImportError:
    _HAS_BS4 = False
    logger.warning("LegendasDivx: beautifulsoup4 not installed, provider will be non-functional")

try:
    import guessit as _guessit_module

    _HAS_GUESSIT = True
except ImportError:
    _HAS_GUESSIT = False
    logger.debug("LegendasDivx: guessit not installed, using regex fallback for release parsing")


BASE_URL = "https://www.legendasdivx.pt"
LOGIN_URL = f"{BASE_URL}/forum/ucp.php"
SEARCH_URL = f"{BASE_URL}/modules.php"

# Daily search limit (site enforces 145, we use 140 as safety margin)
DAILY_SEARCH_LIMIT = 140
SITE_DAILY_LIMIT = 145

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


def _can_use_lxml() -> bool:
    """Check if lxml parser is available for BeautifulSoup."""
    try:
        import lxml  # noqa: F401

        return True
    except ImportError:
        return False


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
