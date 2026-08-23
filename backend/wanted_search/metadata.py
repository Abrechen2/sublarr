"""Wanted search metadata — retry computation, filename parsing, query building."""

import logging
import os
import re
from datetime import UTC, datetime, timedelta

from config import get_settings
from providers.base import VideoQuery

logger = logging.getLogger(__name__)


def _compute_retry_after(search_count: int, settings) -> datetime | None:
    """Compute retry_after datetime using exponential backoff.

    Formula: delay = min(base_hours × 2^(search_count-1), cap_hours)
    - search_count=1 → 1h, =2 → 2h, =3 → 4h, =4 → 8h, ... capped at 168h (7 days)
    """
    if not getattr(settings, "wanted_adaptive_backoff_enabled", True):
        return None
    base = getattr(settings, "wanted_backoff_base_hours", 1.0)
    cap = getattr(settings, "wanted_backoff_cap_hours", 168)
    delay_hours = min(base * (2 ** max(search_count - 1, 0)), cap)
    return datetime.now(UTC) + timedelta(hours=delay_hours)


# Episode patterns for filename parsing (ordered by specificity)
_EPISODE_PATTERNS = [
    re.compile(r"[Ss](\d+)[Ee](\d+)"),  # S01E02
    re.compile(r"(\d+)x(\d+)"),  # 1x02
    re.compile(r"[Ee](?:pisode)?\s*(\d+)", re.I),  # E02, Episode 02
    re.compile(r" - (\d{2,3})(?:\s|\.|\[|$)"),  # " - 02" (anime absolute)
]


def _parse_filename_for_metadata(file_path: str) -> dict:
    """Parse filename to extract series title, season, episode, year.

    Tries guessit first if available (via standalone.parser), then falls back
    to regex patterns. Standalone items typically have metadata from DB, so
    this fallback is rarely exercised for them.

    Returns dict with: series_title, season, episode, year, title
    """
    # Try guessit first if available (more robust than regex patterns)
    try:
        from standalone.parser import parse_media_file

        parsed = parse_media_file(file_path)
        if parsed.get("title"):
            return {
                "series_title": parsed["title"] if parsed["type"] == "episode" else "",
                "title": parsed["title"] if parsed["type"] == "movie" else "",
                "season": parsed.get("season"),
                "episode": parsed.get("episode"),
                "episodes": parsed.get("episodes", []),
                "absolute_episode": parsed.get("absolute_episode"),
                "year": parsed.get("year"),
                "release_group": parsed.get("release_group", ""),
                "source": parsed.get("source", ""),
                "resolution": parsed.get("resolution", ""),
                "is_anime": parsed.get("is_anime", False),
                "is_special": parsed.get("is_special", False),
                "is_ova": parsed.get("is_ova", False),
            }
    except ImportError:
        pass  # standalone.parser not available, fall through to regex

    filename = os.path.basename(file_path)
    name_without_ext = os.path.splitext(filename)[0]

    result = {
        "series_title": "",
        "title": "",
        "season": None,
        "episode": None,
        "year": None,
    }

    # Try to extract season/episode
    for pattern in _EPISODE_PATTERNS:
        match = pattern.search(name_without_ext)
        if match:
            if len(match.groups()) == 2:
                result["season"] = int(match.group(1))
                result["episode"] = int(match.group(2))
            else:
                result["episode"] = int(match.group(1))
            break

    # Extract year (4 digits, likely between 1900-2100)
    year_match = re.search(r"\b(19|20)\d{2}\b", name_without_ext)
    if year_match:
        result["year"] = int(year_match.group(0))

    # Extract series/movie title (everything before season/episode/year)
    # Remove common release group tags and quality indicators
    title_parts = re.split(r"[Ss]\d+[Ee]\d+|\.\d{4}\.|\[.*?\]|\(.*?\)", name_without_ext)
    if title_parts:
        clean_title = title_parts[0].strip(" .-_")
        # Remove quality tags (1080p, 720p, etc.)
        clean_title = re.sub(r"\b\d+p\b", "", clean_title, flags=re.IGNORECASE).strip(" .-_")
        # Remove codec tags (x264, x265, etc.)
        clean_title = re.sub(
            r"\b(x264|x265|h264|h265|hevc)\b", "", clean_title, flags=re.IGNORECASE
        ).strip(" .-_")

        if result["season"] is not None:
            result["series_title"] = clean_title
        else:
            result["title"] = clean_title

    return result


from wanted_search.metadata_enrichers import (  # noqa: F401 — re-exported for back-compat
    _compute_file_hash_for_query,
    _enrich_from_filename,
    _enrich_from_radarr,
    _enrich_from_sonarr,
    _enrich_from_standalone_movie,
    _enrich_from_standalone_series,
    _enrich_release_metadata,
    _resolve_anidb_absolute_episode,
    _resolve_anidb_from_shoko,
    _resolve_anidb_id_for_standalone,
    _validate_minimum_query_data,
)


def build_query_from_wanted(wanted_item: dict) -> VideoQuery:
    """Build a rich VideoQuery from a wanted item + Sonarr/Radarr metadata.

    Fetches series/movie metadata from the relevant *arr client to enrich
    the query with titles, IDs, season/episode numbers, etc.
    Uses target_language from the wanted item (language profile aware).
    Falls back to filename parsing if metadata is unavailable.
    """
    settings = get_settings()
    # Use item's target_language if set, otherwise fall back to global config
    item_lang = wanted_item.get("target_language") or settings.target_language

    query = VideoQuery(
        file_path=wanted_item["file_path"],
        languages=[item_lang],
    )

    metadata_available = False

    if wanted_item["item_type"] == "episode":
        if _enrich_from_sonarr(query, wanted_item):
            metadata_available = True
        if not metadata_available and _enrich_from_standalone_series(query, wanted_item):
            metadata_available = True
    elif wanted_item["item_type"] == "movie":
        if _enrich_from_radarr(query, wanted_item):
            metadata_available = True
        if not metadata_available and _enrich_from_standalone_movie(query, wanted_item):
            metadata_available = True

    if not metadata_available:
        _enrich_from_filename(query, wanted_item)

    # Authoritative Shoko file→AniDB lookup for anime episodes. Fills the gap
    # for the Sonarr/filename paths (the standalone path already tries Shoko as
    # Tier 0 in its own chain). Only runs when no AniDB ID is set yet, so an
    # explicit Sonarr custom-field tag still wins.
    if wanted_item["item_type"] == "episode" and not query.anidb_id:
        _resolve_anidb_from_shoko(query)

    _resolve_anidb_absolute_episode(query, wanted_item)
    _enrich_release_metadata(query, wanted_item)
    _compute_file_hash_for_query(query)

    if wanted_item.get("subtitle_type", "full") == "forced":
        query.forced_only = True

    _validate_minimum_query_data(query, wanted_item)
    return query
