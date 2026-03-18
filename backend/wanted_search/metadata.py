"""Wanted search metadata — retry computation, filename parsing, query building."""

import logging
import os
import re
from datetime import UTC, datetime, timedelta

from config import get_settings
from db.wanted import set_wanted_retry_after
from providers.base import VideoQuery

logger = logging.getLogger(__name__)


def _compute_retry_after(search_count: int, settings) -> str | None:
    """Compute ISO retry_after timestamp using exponential backoff.

    Formula: delay = min(base_hours × 2^(search_count-1), cap_hours)
    - search_count=1 → 1h, =2 → 2h, =3 → 4h, =4 → 8h, ... capped at 168h (7 days)
    """
    if not getattr(settings, "wanted_adaptive_backoff_enabled", True):
        return None
    base = getattr(settings, "wanted_backoff_base_hours", 1.0)
    cap = getattr(settings, "wanted_backoff_cap_hours", 168)
    delay_hours = min(base * (2 ** max(search_count - 1, 0)), cap)
    return (datetime.now(UTC) + timedelta(hours=delay_hours)).isoformat()


def _set_adaptive_retry_after(item_id: int, search_count: int, settings) -> None:
    """Set retry_after on a wanted item (best-effort, never raises)."""
    try:
        retry_after = _compute_retry_after(search_count, settings)
        if retry_after:
            set_wanted_retry_after(item_id, retry_after)
    except Exception as e:
        logger.debug("_set_adaptive_retry_after failed for item %d (non-critical): %s", item_id, e)


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
        series_id = wanted_item.get("sonarr_series_id")
        episode_id = wanted_item.get("sonarr_episode_id")

        if series_id and episode_id:
            try:
                from sonarr_client import get_sonarr_client

                sonarr = get_sonarr_client(instance_name=wanted_item.get("instance_name"))
                if sonarr:
                    meta = sonarr.get_episode_metadata(series_id, episode_id)
                    if meta:
                        query.series_title = meta.get("series_title", "")
                        query.title = meta.get("title", "")
                        query.year = meta.get("year")
                        query.season = meta.get("season")
                        query.episode = meta.get("episode")
                        query.imdb_id = meta.get("imdb_id", "")
                        query.tvdb_id = meta.get("tvdb_id")
                        query.anidb_id = meta.get("anidb_id")
                        query.anilist_id = meta.get("anilist_id")
                        metadata_available = True
                        logger.debug(
                            "Built query from Sonarr metadata: %s S%02dE%02d",
                            query.series_title,
                            query.season or 0,
                            query.episode or 0,
                        )
            except Exception as e:
                logger.warning(
                    "Failed to get Sonarr metadata for wanted %d: %s", wanted_item["id"], e
                )

        # Try standalone metadata if no Sonarr metadata
        if not metadata_available:
            standalone_sid = wanted_item.get("standalone_series_id")
            if standalone_sid:
                try:
                    from db.standalone import get_standalone_series

                    series = get_standalone_series(standalone_sid)
                    if series:
                        query.series_title = series.get("title", "")
                        query.year = series.get("year")
                        query.imdb_id = series.get("imdb_id", "")
                        query.tvdb_id = series.get("tvdb_id")
                        query.tmdb_id = series.get("tmdb_id")
                        query.anilist_id = series.get("anilist_id")
                        # Parse season/episode from wanted item's season_episode field
                        se = wanted_item.get("season_episode", "")
                        if se:
                            se_match = re.match(r"S(\d+)E(\d+)", se, re.IGNORECASE)
                            if se_match:
                                query.season = int(se_match.group(1))
                                query.episode = int(se_match.group(2))
                        metadata_available = True
                        logger.debug(
                            "Built query from standalone series metadata: %s", query.series_title
                        )
                except Exception as e:
                    logger.warning(
                        "Failed to get standalone series metadata for wanted %d: %s",
                        wanted_item["id"],
                        e,
                    )

    elif wanted_item["item_type"] == "movie":
        movie_id = wanted_item.get("radarr_movie_id")

        if movie_id:
            try:
                from radarr_client import get_radarr_client

                radarr = get_radarr_client(instance_name=wanted_item.get("instance_name"))
                if radarr:
                    meta = radarr.get_movie_metadata(movie_id)
                    if meta:
                        query.title = meta.get("title", "")
                        query.year = meta.get("year")
                        query.imdb_id = meta.get("imdb_id", "")
                        query.tmdb_id = meta.get("tmdb_id")
                        query.genres = meta.get("genres", [])
                        metadata_available = True
                        logger.debug(
                            "Built query from Radarr metadata: %s (%s)",
                            query.title,
                            query.year or "no year",
                        )
            except Exception as e:
                logger.warning(
                    "Failed to get Radarr metadata for wanted %d: %s", wanted_item["id"], e
                )

        # Try standalone metadata if no Radarr metadata
        if not metadata_available:
            standalone_mid = wanted_item.get("standalone_movie_id")
            if standalone_mid:
                try:
                    from db.standalone import get_standalone_movies

                    movie = get_standalone_movies(standalone_mid)
                    if movie and isinstance(movie, dict):
                        query.title = movie.get("title", "")
                        query.year = movie.get("year")
                        query.imdb_id = movie.get("imdb_id", "")
                        query.tmdb_id = movie.get("tmdb_id")
                        metadata_available = True
                        logger.debug(
                            "Built query from standalone movie metadata: %s (%s)",
                            query.title,
                            query.year,
                        )
                except Exception as e:
                    logger.warning(
                        "Failed to get standalone movie metadata for wanted %d: %s",
                        wanted_item["id"],
                        e,
                    )

    # Fallback to filename parsing if metadata unavailable
    if not metadata_available:
        logger.debug("Metadata unavailable, parsing filename: %s", wanted_item["file_path"])
        parsed = _parse_filename_for_metadata(wanted_item["file_path"])

        if not query.series_title and parsed["series_title"]:
            query.series_title = parsed["series_title"]
        if not query.title and parsed["title"]:
            query.title = parsed["title"]
        if query.season is None and parsed["season"] is not None:
            query.season = parsed["season"]
        if query.episode is None and parsed["episode"] is not None:
            query.episode = parsed["episode"]
        if not query.episodes and parsed.get("episodes"):
            query.episodes = parsed["episodes"]
        if query.absolute_episode is None and parsed.get("absolute_episode") is not None:
            query.absolute_episode = parsed["absolute_episode"]
        if query.year is None and parsed["year"] is not None:
            query.year = parsed["year"]
        if not query.release_group and parsed.get("release_group"):
            query.release_group = parsed["release_group"]
        if not query.source and parsed.get("source"):
            query.source = parsed["source"]
        if not query.resolution and parsed.get("resolution"):
            query.resolution = parsed["resolution"]
        if parsed.get("is_special"):
            query.is_special = True
        if parsed.get("is_ova"):
            query.is_ova = True

        logger.debug(
            "Parsed from filename: series=%s, title=%s, S%02dE%02d, year=%s, "
            "episodes=%s, special=%s, ova=%s",
            query.series_title or "N/A",
            query.title or "N/A",
            query.season or 0,
            query.episode or 0,
            query.year or "N/A",
            query.episodes or [],
            query.is_special,
            query.is_ova,
        )

    # Resolve AniDB absolute episode if the series has absolute_order enabled.
    # Only applies to episodes with a known TVDB ID, season, and episode number.
    if (
        wanted_item["item_type"] == "episode"
        and query.tvdb_id is not None
        and query.season is not None
        and query.episode is not None
    ):
        series_id = wanted_item.get("sonarr_series_id")
        if series_id:
            try:
                from db.repositories.anidb import AnidbRepository

                repo = AnidbRepository()
                if repo.get_absolute_order(series_id):
                    abs_ep = repo.get_anidb_absolute(query.tvdb_id, query.season, query.episode)
                    if abs_ep is not None:
                        query.absolute_episode = abs_ep
                        logger.debug(
                            "Wanted %d: AniDB absolute episode resolved: S%02dE%02d -> abs %d",
                            wanted_item["id"],
                            query.season,
                            query.episode,
                            abs_ep,
                        )
                    else:
                        logger.debug(
                            "Wanted %d: absolute_order enabled but no AniDB mapping for "
                            "TVDB %d S%02dE%02d — falling back to standard S/E",
                            wanted_item["id"],
                            query.tvdb_id,
                            query.season,
                            query.episode,
                        )
            except Exception as _abs_err:
                logger.warning(
                    "Wanted %d: AniDB absolute episode resolution failed: %s",
                    wanted_item["id"],
                    _abs_err,
                )

    # Enrich query with release metadata parsed from the video filename.
    # parse_media_file uses guessit to extract release_group, source, resolution,
    # and video_codec — these feed into provider scoring (release_group: +14 pts).
    # Runs always (not just fallback) so Sonarr/Radarr metadata path also benefits.
    if not query.release_group:
        try:
            from standalone.parser import parse_media_file

            file_meta = parse_media_file(wanted_item["file_path"])
            if file_meta.get("release_group"):
                query.release_group = file_meta["release_group"]
            if not query.source and file_meta.get("source"):
                query.source = file_meta["source"]
            if not query.resolution and file_meta.get("resolution"):
                query.resolution = file_meta["resolution"]
            if not query.video_codec and file_meta.get("video_codec"):
                query.video_codec = file_meta["video_codec"]
            if query.release_group:
                logger.debug(
                    "Wanted %d: release metadata — group=%r source=%r res=%r",
                    wanted_item["id"],
                    query.release_group,
                    query.source,
                    query.resolution,
                )
        except Exception as _rg_err:
            logger.debug("Failed to parse release metadata from filename: %s", _rg_err)

    # Pre-compute video file hash for hash-based provider matching (e.g. OpenSubtitles, Napisy24).
    # Computed once here so all providers share the same cached value via query.file_hash.
    if not query.file_hash and query.file_path and os.path.isfile(query.file_path):
        try:
            from providers.opensubtitles import _compute_opensubtitles_hash

            query.file_hash = _compute_opensubtitles_hash(query.file_path)
            if query.file_hash:
                logger.debug("Pre-computed file hash for %s: %s", query.file_path, query.file_hash)
        except Exception as _hash_err:
            logger.debug("Hash pre-computation skipped: %s", _hash_err)

    # Set forced_only based on wanted item's subtitle_type
    if wanted_item.get("subtitle_type", "full") == "forced":
        query.forced_only = True

    # Validate query has minimum required data
    has_minimum_data = False
    if wanted_item["item_type"] == "episode":
        has_minimum_data = (
            bool(query.series_title or query.title)
            and query.season is not None
            and query.episode is not None
        )
    else:
        has_minimum_data = bool(query.title)

    if not has_minimum_data:
        logger.warning(
            "Query for wanted item %d lacks minimum required data: file_path=%s, series_title=%s, title=%s, season=%s, episode=%s",
            wanted_item["id"],
            query.file_path,
            query.series_title,
            query.title,
            query.season,
            query.episode,
        )
    else:
        logger.debug("Query validated: %s", query.display_name)

    return query
