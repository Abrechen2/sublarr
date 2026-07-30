"""Per-source enrichers for ``build_query_from_wanted``.

Extracted from wanted_search/metadata.py. Each ``_enrich_from_*``
helper populates the shared :class:`VideoQuery` with fields sourced
from a single backend (Sonarr, Radarr, standalone series/movies, or
filename parsing) and returns ``True`` when it succeeded — the
orchestrator uses that flag to decide whether to fall through to the
next enricher.

Cross-cutting helpers (AniDB ID resolution + AniDB absolute-episode
lookup + release-metadata enrichment + file-hash pre-computation +
final validation) live here too so the entire ``build_query_from_wanted``
pipeline is co-located.

No tests patch wanted_search.metadata.* directly, so moving the
helpers to this sibling is transparent — ``build_query_from_wanted``
imports and calls them at module top in the facade (``metadata.py``).
"""

import logging
import os
import re

from providers.base import VideoQuery

logger = logging.getLogger(__name__)


def _enrich_from_sonarr(query: VideoQuery, wanted_item: dict) -> bool:
    """Populate the episode fields on ``query`` from Sonarr. Returns True on success."""
    series_id = wanted_item.get("sonarr_series_id")
    episode_id = wanted_item.get("sonarr_episode_id")
    if not (series_id and episode_id):
        return False
    try:
        from sonarr_client import get_sonarr_client

        sonarr = get_sonarr_client(instance_name=wanted_item.get("instance_name"))
        if not sonarr:
            return False
        meta = sonarr.get_episode_metadata(series_id, episode_id)
        if not meta:
            return False
        query.series_title = meta.get("series_title", "")
        query.title = meta.get("title", "")
        query.year = meta.get("year")
        query.season = meta.get("season")
        query.episode = meta.get("episode")
        query.imdb_id = meta.get("imdb_id", "")
        query.tvdb_id = meta.get("tvdb_id")
        query.anidb_id = meta.get("anidb_id")
        query.anilist_id = meta.get("anilist_id")
        logger.debug(
            "Built query from Sonarr metadata: %s S%02dE%02d",
            query.series_title,
            query.season or 0,
            query.episode or 0,
        )
        return True
    except Exception as e:
        logger.warning("Failed to get Sonarr metadata for wanted %d: %s", wanted_item["id"], e)
        return False


def _resolve_anidb_from_shoko(query: VideoQuery) -> bool:
    """Tier 0: set AniDB IDs from Shoko's authoritative file→AniDB mapping.

    Shoko already matches every physical file to its exact AniDB anime,
    AniDB episode and (for Normal episodes) absolute-episode number, so when
    a Shoko instance is configured this short-circuits the fuzzy resolution
    chain below. No-op (returns False) when Shoko is disabled/unreachable or
    the file is unknown to Shoko.
    """
    if not query.file_path:
        return False
    try:
        from config import get_shoko_config

        shoko_cfg = get_shoko_config()
        if not shoko_cfg:
            return False

        from metadata.shoko_client import ShokoClient

        client = ShokoClient(
            url=shoko_cfg.get("url", ""),
            api_key=shoko_cfg.get("api_key", ""),
            username=shoko_cfg.get("username", ""),
            password=shoko_cfg.get("password", ""),
        )
        ids = client.get_file_ids_by_path(query.file_path)
        if not ids or not ids.anidb_anime_id:
            return False

        query.anidb_id = ids.anidb_anime_id
        if ids.anidb_episode_id:
            query.anidb_episode_id = ids.anidb_episode_id
        if ids.absolute_episode is not None and query.absolute_episode is None:
            query.absolute_episode = ids.absolute_episode
        logger.debug(
            "Resolved AniDB ID %d (ep %s, abs %s) from Shoko for %s",
            ids.anidb_anime_id,
            ids.anidb_episode_id,
            ids.absolute_episode,
            query.file_path,
        )
        return True
    except Exception as _e:  # noqa: BLE001 — Shoko lookup is best-effort
        logger.debug("Shoko AniDB resolution failed for %s: %s", query.file_path, _e)
        return False


def _resolve_anidb_id_for_standalone(query: VideoQuery, wanted_item: dict) -> None:
    """Try to set ``query.anidb_id`` using Shoko → cache → AniList → title search → title dump."""
    if query.anidb_id:
        return
    # Tier 0: authoritative Shoko file→AniDB mapping (short-circuits the rest).
    if _resolve_anidb_from_shoko(query):
        return
    try:
        # Tier 1: TVDB→AniDB cache
        if query.tvdb_id:
            from db.cache import get_anidb_mapping

            cached_anidb_id = get_anidb_mapping(query.tvdb_id)
            if cached_anidb_id:
                query.anidb_id = cached_anidb_id
                logger.debug(
                    "Resolved AniDB ID %d from cache for standalone TVDB %d",
                    cached_anidb_id,
                    query.tvdb_id,
                )

        # Tier 2: AniList external links
        if not query.anidb_id and query.anilist_id:
            from anidb_mapper import resolve_anidb_from_anilist

            anidb_id = resolve_anidb_from_anilist(query.anilist_id, query.tvdb_id)
            if anidb_id:
                query.anidb_id = anidb_id
                logger.debug(
                    "Resolved AniDB ID %d via AniList %d for wanted %d",
                    anidb_id,
                    query.anilist_id,
                    wanted_item["id"],
                )

        # Tier 3: title-based AniList search (works even when tvdb_id/anilist_id are unknown)
        if not query.anidb_id and query.series_title:
            from anidb_mapper import resolve_anidb_from_title

            anidb_id = resolve_anidb_from_title(query.series_title, tvdb_id=query.tvdb_id)
            if anidb_id:
                query.anidb_id = anidb_id
                logger.debug(
                    "Resolved AniDB ID %d via title search %r for wanted %d",
                    anidb_id,
                    query.series_title,
                    wanted_item["id"],
                )

        # Tier 4: AniDB title dump (offline xml.gz lookup — works when AniList has no AniDB link)
        if not query.anidb_id and query.series_title:
            from anidb_mapper import resolve_anidb_from_title_dump

            anidb_id = resolve_anidb_from_title_dump(query.series_title, tvdb_id=query.tvdb_id)
            if anidb_id:
                query.anidb_id = anidb_id
                logger.debug(
                    "Resolved AniDB ID %d via title dump %r for wanted %d",
                    anidb_id,
                    query.series_title,
                    wanted_item["id"],
                )
    except Exception as _e:
        logger.debug(
            "AniDB ID resolution failed for standalone wanted %d: %s", wanted_item["id"], _e
        )


def _enrich_from_standalone_series(query: VideoQuery, wanted_item: dict) -> bool:
    """Populate episode fields on ``query`` from the standalone series table."""
    standalone_sid = wanted_item.get("standalone_series_id")
    if not standalone_sid:
        return False
    try:
        from db.standalone import get_standalone_series

        series = get_standalone_series(standalone_sid)
        if not series:
            return False
        query.series_title = series.get("title", "")
        query.year = series.get("year")
        query.imdb_id = series.get("imdb_id", "")
        query.tvdb_id = series.get("tvdb_id")
        query.tmdb_id = series.get("tmdb_id")
        query.anilist_id = series.get("anilist_id")
        se = wanted_item.get("season_episode", "")
        if se:
            se_match = re.match(r"S(\d+)E(\d+)", se, re.IGNORECASE)
            if se_match:
                query.season = int(se_match.group(1))
                query.episode = int(se_match.group(2))
        logger.debug("Built query from standalone series metadata: %s", query.series_title)
        _resolve_anidb_id_for_standalone(query, wanted_item)
        return True
    except Exception as e:
        logger.warning(
            "Failed to get standalone series metadata for wanted %d: %s", wanted_item["id"], e
        )
        return False


def _enrich_from_radarr(query: VideoQuery, wanted_item: dict) -> bool:
    """Populate the movie fields on ``query`` from Radarr. Returns True on success."""
    movie_id = wanted_item.get("radarr_movie_id")
    if not movie_id:
        return False
    try:
        from radarr_client import get_radarr_client

        radarr = get_radarr_client(instance_name=wanted_item.get("instance_name"))
        if not radarr:
            return False
        meta = radarr.get_movie_metadata(movie_id)
        if not meta:
            return False
        query.title = meta.get("title", "")
        query.year = meta.get("year")
        query.imdb_id = meta.get("imdb_id", "")
        query.tmdb_id = meta.get("tmdb_id")
        query.genres = meta.get("genres", [])
        logger.debug(
            "Built query from Radarr metadata: %s (%s)", query.title, query.year or "no year"
        )
        return True
    except Exception as e:
        logger.warning("Failed to get Radarr metadata for wanted %d: %s", wanted_item["id"], e)
        return False


def _enrich_from_standalone_movie(query: VideoQuery, wanted_item: dict) -> bool:
    """Populate movie fields on ``query`` from the standalone movies table."""
    standalone_mid = wanted_item.get("standalone_movie_id")
    if not standalone_mid:
        return False
    try:
        from db.standalone import get_standalone_movies

        movie = get_standalone_movies(standalone_mid)
        if not (movie and isinstance(movie, dict)):
            return False
        query.title = movie.get("title", "")
        query.year = movie.get("year")
        query.imdb_id = movie.get("imdb_id", "")
        query.tmdb_id = movie.get("tmdb_id")
        logger.debug("Built query from standalone movie metadata: %s (%s)", query.title, query.year)
        return True
    except Exception as e:
        logger.warning(
            "Failed to get standalone movie metadata for wanted %d: %s", wanted_item["id"], e
        )
        return False


def _enrich_from_filename(query: VideoQuery, wanted_item: dict) -> None:
    """Fall back to filename parsing when no *arr/standalone metadata is available."""
    # Imported here so metadata.py can keep the regex patterns + parser at home.
    from wanted_search.metadata import _parse_filename_for_metadata

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


def _resolve_anidb_absolute_episode(query: VideoQuery, wanted_item: dict) -> None:
    """Set query.absolute_episode from the AniDB mapping when absolute_order is enabled."""
    # Shoko (or another authoritative source) may already have set the absolute
    # episode; its per-file AniDB number beats the TVDB→AniDB range mapping.
    if query.absolute_episode is not None:
        return
    if not (
        wanted_item["item_type"] == "episode"
        and query.tvdb_id is not None
        and query.season is not None
        and query.episode is not None
    ):
        return

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
    elif wanted_item.get("standalone_series_id") and query.absolute_episode is None:
        # Standalone items have no per-series absolute_order flag — try resolving anyway
        # if a TVDB→absolute mapping exists in the DB (populated by AniDB sync).
        try:
            from db.repositories.anidb import AnidbRepository

            repo = AnidbRepository()
            abs_ep = repo.get_anidb_absolute(query.tvdb_id, query.season, query.episode)
            if abs_ep is not None:
                query.absolute_episode = abs_ep
                logger.debug(
                    "Wanted %d (standalone): AniDB absolute episode resolved: S%02dE%02d -> abs %d",
                    wanted_item["id"],
                    query.season,
                    query.episode,
                    abs_ep,
                )
        except Exception as _abs_err:
            logger.debug(
                "Wanted %d (standalone): AniDB absolute episode resolution skipped: %s",
                wanted_item["id"],
                _abs_err,
            )


def _enrich_release_metadata(query: VideoQuery, wanted_item: dict) -> None:
    """Populate release_group/source/resolution/video_codec from the filename via guessit.

    Runs always (not just in the fallback path) so metadata-rich Sonarr/Radarr
    entries also benefit from accurate release-group scoring.
    """
    if query.release_group:
        return
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


def _compute_file_hash_for_query(query: VideoQuery) -> None:
    """Pre-compute the OpenSubtitles hash so hash-based providers share one value."""
    if query.file_hash or not query.file_path or not os.path.isfile(query.file_path):
        return
    try:
        from providers.opensubtitles import _compute_opensubtitles_hash

        query.file_hash = _compute_opensubtitles_hash(query.file_path)
        if query.file_hash:
            logger.debug("Pre-computed file hash for %s: %s", query.file_path, query.file_hash)
    except Exception as _hash_err:
        logger.debug("Hash pre-computation skipped: %s", _hash_err)


def _validate_minimum_query_data(query: VideoQuery, wanted_item: dict) -> None:
    """Log-only validation: warn if the built query lacks the minimum matching fields."""
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
