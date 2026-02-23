"""Wanted search module — connects Wanted items with the Provider system.

Builds VideoQueries from wanted items, searches providers, downloads best
results, and triggers translation. Supports parallel item processing via
ThreadPoolExecutor. Provider-level rate limiters and circuit breakers
handle concurrency safety.
"""

import os
import re
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Optional

from config import get_settings, map_path
from db.wanted import (
    get_wanted_item, get_wanted_items, update_wanted_status,
    update_wanted_search, set_wanted_retry_after,
)
from db.library import record_upgrade
from db.providers import record_subtitle_download
from db.jobs import create_job, update_job, record_stat
from upgrade_scorer import should_upgrade
from providers import get_provider_manager
from providers.base import VideoQuery, SubtitleFormat
from translator import get_forced_output_path

logger = logging.getLogger(__name__)


def _compute_retry_after(search_count: int, settings) -> Optional[str]:
    """Compute ISO retry_after timestamp using exponential backoff.

    Formula: delay = min(base_hours × 2^(search_count-1), cap_hours)
    - search_count=1 → 1h, =2 → 2h, =3 → 4h, =4 → 8h, ... capped at 168h (7 days)
    """
    if not getattr(settings, "wanted_adaptive_backoff_enabled", True):
        return None
    base = getattr(settings, "wanted_backoff_base_hours", 1.0)
    cap = getattr(settings, "wanted_backoff_cap_hours", 168)
    delay_hours = min(base * (2 ** max(search_count - 1, 0)), cap)
    return (datetime.now(timezone.utc) + timedelta(hours=delay_hours)).isoformat()


def _set_adaptive_retry_after(item_id: int, search_count: int, settings) -> None:
    """Set retry_after on a wanted item (best-effort, never raises)."""
    try:
        retry_after = _compute_retry_after(search_count, settings)
        if retry_after:
            set_wanted_retry_after(item_id, retry_after)
    except Exception:
        pass  # Non-critical — backoff is advisory, failure here must not abort the pipeline


# Episode patterns for filename parsing (ordered by specificity)
_EPISODE_PATTERNS = [
    re.compile(r'[Ss](\d+)[Ee](\d+)'),           # S01E02
    re.compile(r'(\d+)x(\d+)'),                    # 1x02
    re.compile(r'[Ee](?:pisode)?\s*(\d+)', re.I),  # E02, Episode 02
    re.compile(r' - (\d{2,3})(?:\s|\.|\[|$)'),     # " - 02" (anime absolute)
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
                "year": parsed.get("year"),
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
    year_match = re.search(r'\b(19|20)\d{2}\b', name_without_ext)
    if year_match:
        result["year"] = int(year_match.group(0))
    
    # Extract series/movie title (everything before season/episode/year)
    # Remove common release group tags and quality indicators
    title_parts = re.split(r'[Ss]\d+[Ee]\d+|\.\d{4}\.|\[.*?\]|\(.*?\)', name_without_ext)
    if title_parts:
        clean_title = title_parts[0].strip(' .-_')
        # Remove quality tags (1080p, 720p, etc.)
        clean_title = re.sub(r'\b\d+p\b', '', clean_title, flags=re.IGNORECASE).strip(' .-_')
        # Remove codec tags (x264, x265, etc.)
        clean_title = re.sub(r'\b(x264|x265|h264|h265|hevc)\b', '', clean_title, flags=re.IGNORECASE).strip(' .-_')
        
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
                        logger.debug("Built query from Sonarr metadata: %s S%02dE%02d", 
                                   query.series_title, query.season or 0, query.episode or 0)
            except Exception as e:
                logger.warning("Failed to get Sonarr metadata for wanted %d: %s",
                               wanted_item["id"], e)

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
                            se_match = re.match(r'S(\d+)E(\d+)', se, re.IGNORECASE)
                            if se_match:
                                query.season = int(se_match.group(1))
                                query.episode = int(se_match.group(2))
                        metadata_available = True
                        logger.debug("Built query from standalone series metadata: %s",
                                     query.series_title)
                except Exception as e:
                    logger.warning("Failed to get standalone series metadata for wanted %d: %s",
                                   wanted_item["id"], e)

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
                        logger.debug("Built query from Radarr metadata: %s (%s)", 
                                   query.title, query.year or "no year")
            except Exception as e:
                logger.warning("Failed to get Radarr metadata for wanted %d: %s",
                               wanted_item["id"], e)

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
                        logger.debug("Built query from standalone movie metadata: %s (%s)",
                                     query.title, query.year)
                except Exception as e:
                    logger.warning("Failed to get standalone movie metadata for wanted %d: %s",
                                   wanted_item["id"], e)

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
        if query.year is None and parsed["year"] is not None:
            query.year = parsed["year"]
        
        logger.debug("Parsed from filename: series=%s, title=%s, S%02dE%02d, year=%s",
                     query.series_title or "N/A", query.title or "N/A", 
                     query.season or 0, query.episode or 0, query.year or "N/A")

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
                    abs_ep = repo.get_anidb_absolute(
                        query.tvdb_id, query.season, query.episode
                    )
                    if abs_ep is not None:
                        query.absolute_episode = abs_ep
                        logger.debug(
                            "Wanted %d: AniDB absolute episode resolved: S%02dE%02d -> abs %d",
                            wanted_item["id"], query.season, query.episode, abs_ep,
                        )
                    else:
                        logger.debug(
                            "Wanted %d: absolute_order enabled but no AniDB mapping for "
                            "TVDB %d S%02dE%02d — falling back to standard S/E",
                            wanted_item["id"], query.tvdb_id, query.season, query.episode,
                        )
            except Exception as _abs_err:
                logger.warning(
                    "Wanted %d: AniDB absolute episode resolution failed: %s",
                    wanted_item["id"], _abs_err,
                )

    # Set forced_only based on wanted item's subtitle_type
    if wanted_item.get("subtitle_type", "full") == "forced":
        query.forced_only = True

    # Validate query has minimum required data
    has_minimum_data = False
    if wanted_item["item_type"] == "episode":
        has_minimum_data = bool(query.series_title or query.title) and query.season is not None and query.episode is not None
    else:
        has_minimum_data = bool(query.title)

    if not has_minimum_data:
        logger.warning("Query for wanted item %d lacks minimum required data: file_path=%s, series_title=%s, title=%s, season=%s, episode=%s",
                      wanted_item["id"], query.file_path, query.series_title, query.title, query.season, query.episode)
    else:
        logger.debug("Query validated: %s", query.display_name)

    return query


def _get_priority_key(result, target_lang, source_lang):
    """Calculate priority: target.ass=0, source.ass=1, target.srt=2, source.srt=3"""
    is_target = result["language"] == target_lang
    is_ass = result["format"] == "ass"
    
    if is_target and is_ass:
        return (0, -result["score"])  # Highest priority: target.ass
    elif not is_target and is_ass:
        return (1, -result["score"])  # Second priority: source.ass
    elif is_target and not is_ass:
        return (2, -result["score"])  # Third priority: target.srt
    else:
        return (3, -result["score"])  # Lowest priority: source.srt


def search_wanted_item(item_id: int) -> dict:
    """Search providers for a single wanted item.

    Priority order:
    1. target_language ASS (e.g. de.ass) - absolute priority
    2. source_language ASS (e.g. en.ass) - for LLM translation
    3. target_language SRT (e.g. de.srt)
    4. source_language SRT (e.g. en.srt) - for LLM translation

    Returns:
        dict: {wanted_id, target_results, source_results}
    """
    item = get_wanted_item(item_id)
    if not item:
        return {"error": "Item not found", "wanted_id": item_id}

    settings = get_settings()
    manager = get_provider_manager()
    item_lang = item.get("target_language") or settings.target_language
    source_lang = settings.source_language

    # Build queries (forced_only is set by build_query_from_wanted based on subtitle_type)
    target_query = build_query_from_wanted(item)
    target_query.languages = [item_lang]

    source_query = build_query_from_wanted(item)
    source_query.languages = [source_lang]

    all_results = []

    # Search 1: target_language ASS (Priority 1)
    try:
        results = manager.search(target_query, format_filter=SubtitleFormat.ASS)
        all_results.extend([_result_to_dict(r) for r in results[:20]])
    except Exception as e:
        logger.warning("Target ASS search failed for wanted %d: %s", item_id, e, exc_info=True)
        # Continue with other searches - don't fail entire operation

    # Search 2: source_language ASS (Priority 2)
    try:
        results = manager.search(source_query, format_filter=SubtitleFormat.ASS)
        all_results.extend([_result_to_dict(r) for r in results[:20]])
    except Exception as e:
        logger.warning("Source ASS search failed for wanted %d: %s", item_id, e, exc_info=True)
        # Continue with other searches - don't fail entire operation

    # Search 3: target_language SRT (Priority 3)
    try:
        results = manager.search(target_query, format_filter=SubtitleFormat.SRT)
        all_results.extend([_result_to_dict(r) for r in results[:20]])
    except Exception as e:
        logger.warning("Target SRT search failed for wanted %d: %s", item_id, e, exc_info=True)
        # Continue with other searches - don't fail entire operation

    # Search 4: source_language SRT (Priority 4)
    try:
        results = manager.search(source_query, format_filter=SubtitleFormat.SRT)
        all_results.extend([_result_to_dict(r) for r in results[:20]])
    except Exception as e:
        logger.warning("Source SRT search failed for wanted %d: %s", item_id, e, exc_info=True)
        # Continue with other searches - don't fail entire operation

    # Sort by priority: target.ass > source.ass > target.srt > source.srt
    all_results.sort(key=lambda r: _get_priority_key(r, item_lang, source_lang))

    # Split into target_results and source_results for API compatibility
    target_results = [r for r in all_results if r["language"] == item_lang]
    source_results = [r for r in all_results if r["language"] == source_lang]

    # Track the search attempt
    update_wanted_search(item_id)

    return {
        "wanted_id": item_id,
        "target_results": target_results,
        "source_results": source_results,
    }


def process_wanted_item(item_id: int) -> dict:
    """Full pipeline for one item: search -> download best -> translate.

    Returns:
        dict: {wanted_id, status, output_path, provider, error}
    """
    item = get_wanted_item(item_id)
    if not item:
        return {"wanted_id": item_id, "status": "error", "error": "Item not found"}

    settings = get_settings()
    item_lang = item.get("target_language") or settings.target_language

    # Check max search attempts
    if item["search_count"] >= settings.wanted_max_search_attempts:
        update_wanted_status(item_id, "failed", error="Max search attempts reached")
        return {
            "wanted_id": item_id,
            "status": "failed",
            "error": "Max search attempts reached",
        }

    update_wanted_status(item_id, "searching")
    update_wanted_search(item_id)

    file_path = item["file_path"]
    if not os.path.exists(file_path):
        update_wanted_status(item_id, "failed", error="File not found on disk")
        return {
            "wanted_id": item_id,
            "status": "failed",
            "error": f"File not found: {file_path}",
        }

    is_upgrade = bool(item.get("upgrade_candidate"))
    current_score = item.get("current_score", 0)
    subtitle_type = item.get("subtitle_type", "full")
    manager = get_provider_manager()

    # Forced subtitle handling: download-only, no translation
    if subtitle_type == "forced":
        return _process_forced_wanted_item(item, item_id, item_lang, manager)

    # Track whether any ASS content was found in Steps 1+2 (for SRT early-exit, Phase 2)
    _ass_had_results = False

    # Step 1: Try to find target language ASS directly from providers (Priority 1)
    query = build_query_from_wanted(item)
    query.languages = [item_lang]

    try:
        result = manager.search_and_download_best(
            query, format_filter=SubtitleFormat.ASS
        )
        if result and result.content:
            _ass_had_results = True
            new_score = result.score

            # For upgrade candidates, check if the new sub is actually better
            if is_upgrade and current_score > 0:
                from translator import get_output_path_for_lang
                existing_srt = get_output_path_for_lang(file_path, "srt", item_lang)
                do_upgrade, reason = should_upgrade(
                    "srt", current_score, "ass", new_score,
                    upgrade_prefer_ass=settings.upgrade_prefer_ass,
                    upgrade_min_score_delta=settings.upgrade_min_score_delta,
                    upgrade_window_days=settings.upgrade_window_days,
                    existing_file_path=existing_srt,
                )
                if not do_upgrade:
                    logger.info("Wanted %d: Upgrade rejected — %s", item_id, reason)
                    update_wanted_status(item_id, "wanted")
                    return {
                        "wanted_id": item_id,
                        "status": "skipped",
                        "reason": reason,
                    }
                logger.info("Wanted %d: Upgrade approved — %s", item_id, reason)

            from translator import get_output_path_for_lang
            output_path = get_output_path_for_lang(file_path, "ass", item_lang)

            # If upgrading from SRT, remove old SRT file
            if is_upgrade:
                old_srt = get_output_path_for_lang(file_path, "srt", item_lang)
                if os.path.exists(old_srt):
                    os.remove(old_srt)
                    logger.info("Wanted %d: Removed old SRT: %s", item_id, old_srt)
                record_upgrade(
                    file_path=file_path,
                    old_format="srt", old_score=current_score,
                    new_format="ass", new_score=new_score,
                    provider_name=result.provider_name,
                    upgrade_reason=f"SRT->ASS via {result.provider_name}",
                )

            try:
                manager.save_subtitle(result, output_path)
                record_subtitle_download(
                    result.provider_name, result.subtitle_id, item_lang,
                    result.format.value if result.format.value != "unknown" else "ass",
                    file_path, result.score,
                )
                logger.info("Wanted %d: Provider %s delivered target ASS directly",
                             item_id, result.provider_name)
                update_wanted_status(item_id, "found")
                return {
                    "wanted_id": item_id,
                    "status": "found",
                    "output_path": output_path,
                    "provider": result.provider_name,
                    "upgraded": is_upgrade,
                }
            except (OSError, RuntimeError) as save_error:
                logger.error("Wanted %d: Failed to save subtitle from %s: %s",
                             item_id, result.provider_name, save_error)
                # Fall through to next step
    except Exception as e:
        logger.warning("Wanted %d: Direct target ASS search failed: %s", item_id, e, exc_info=True)

    # Step 2: Try to find source language ASS for translation (Priority 2)
    source_query = build_query_from_wanted(item)
    source_query.languages = [settings.source_language]

    try:
        result = manager.search_and_download_best(
            source_query, format_filter=SubtitleFormat.ASS
        )
        if result and result.content:
            _ass_had_results = True
            # Download source ASS and translate it
            from translator import get_output_path_for_lang, _translate_external_ass
            base = os.path.splitext(file_path)[0]
            tmp_source_path = f"{base}.{settings.source_language}.ass"
            try:
                # Use the returned path — save_subtitle may adjust the extension
                # (e.g. if the downloaded file turns out to be SRT, not ASS)
                actual_source_path = manager.save_subtitle(result, tmp_source_path)
                record_subtitle_download(
                    result.provider_name, result.subtitle_id, settings.source_language,
                    result.format.value if result.format.value != "unknown" else "ass",
                    file_path, result.score,
                )
            except (OSError, RuntimeError) as save_error:
                logger.error("Wanted %d: Failed to save source ASS from %s: %s",
                             item_id, result.provider_name, save_error)
                raise  # skip to next step

            # Build arr_context for glossary lookup
            arr_context = {}
            if item.get("sonarr_series_id"):
                arr_context["sonarr_series_id"] = item["sonarr_series_id"]
            if item.get("sonarr_episode_id"):
                arr_context["sonarr_episode_id"] = item["sonarr_episode_id"]
            if item.get("radarr_movie_id"):
                arr_context["radarr_movie_id"] = item["radarr_movie_id"]

            job = create_job(file_path, force=False, arr_context=arr_context if arr_context else None)
            update_job(job["id"], "running")
            try:
                translate_result = _translate_external_ass(
                    file_path, actual_source_path,
                    target_language=item_lang,
                    target_language_name=settings.target_language_name,
                    arr_context=arr_context if arr_context else None
                )
            except Exception as trans_error:
                logger.error("Wanted %d: Translation failed for source ASS: %s",
                             item_id, trans_error, exc_info=True)
                update_job(job["id"], "failed", error=str(trans_error))
                record_stat(success=False)
                try:
                    if os.path.exists(actual_source_path):
                        os.remove(actual_source_path)
                except Exception:
                    pass
                raise  # skip to next step

            # Clean up temporary source file
            try:
                if os.path.exists(actual_source_path):
                    os.remove(actual_source_path)
            except Exception:
                pass

            if translate_result and translate_result.get("success"):
                update_job(job["id"], "completed", result=translate_result, error=translate_result.get("error"))
                s = translate_result.get("stats", {})
                record_stat(success=True, skipped=s.get("skipped", False), fmt=s.get("format", ""), source=s.get("source", ""))
                logger.info("Wanted %d: Translated source ASS from provider %s",
                           item_id, result.provider_name)
                update_wanted_status(item_id, "found")
                return {
                    "wanted_id": item_id,
                    "status": "found",
                    "output_path": translate_result.get("output_path"),
                    "provider": f"{result.provider_name} (translated)",
                }
            else:
                update_job(job["id"], "failed", result=translate_result, error=translate_result.get("error") if translate_result else "Translation failed")
                record_stat(success=False)
    except Exception as e:
        logger.warning("Wanted %d: Source ASS search/translation failed: %s", item_id, e, exc_info=True)

    # Early exit: skip SRT steps if no ASS was found in Steps 1+2 (providers likely have nothing)
    _skip_srt = getattr(settings, "wanted_skip_srt_on_no_ass", True) and not _ass_had_results
    if _skip_srt:
        logger.debug("Wanted %d: No ASS found in Steps 1+2, skipping SRT steps", item_id)

    # Step 3: Try to find target language SRT directly (Priority 3)
    if not _skip_srt:
        try:
            result = manager.search_and_download_best(
                query, format_filter=SubtitleFormat.SRT
            )
            if result and result.content:
                from translator import get_output_path_for_lang
                output_path = get_output_path_for_lang(file_path, "srt", item_lang)
                try:
                    manager.save_subtitle(result, output_path)
                    record_subtitle_download(
                        result.provider_name, result.subtitle_id, item_lang,
                        result.format.value if result.format.value != "unknown" else "srt",
                        file_path, result.score,
                    )
                    logger.info("Wanted %d: Provider %s delivered target SRT directly",
                                 item_id, result.provider_name)
                    update_wanted_status(item_id, "found")
                    return {
                        "wanted_id": item_id,
                        "status": "found",
                        "output_path": output_path,
                        "provider": result.provider_name,
                    }
                except (OSError, RuntimeError) as save_error:
                    logger.error("Wanted %d: Failed to save target SRT from %s: %s",
                                 item_id, result.provider_name, save_error)
                    # Fall through to next step
        except Exception as e:
            logger.warning("Wanted %d: Direct target SRT search failed: %s", item_id, e, exc_info=True)

    # Step 4: Try to find source language SRT for translation (Priority 4)
    if not _skip_srt:
        try:
            result = manager.search_and_download_best(
                source_query, format_filter=SubtitleFormat.SRT
            )
            if result and result.content:
                # Download source SRT and translate it
                from translator import get_output_path_for_lang, translate_srt_from_file
                base = os.path.splitext(file_path)[0]
                tmp_source_path = f"{base}.{settings.source_language}.srt"
                try:
                    actual_source_path = manager.save_subtitle(result, tmp_source_path)
                    record_subtitle_download(
                        result.provider_name, result.subtitle_id, settings.source_language,
                        result.format.value if result.format.value != "unknown" else "srt",
                        file_path, result.score,
                    )
                except (OSError, RuntimeError) as save_error:
                    logger.error("Wanted %d: Failed to save source SRT from %s: %s",
                                 item_id, result.provider_name, save_error)
                    raise  # skip to next step

                # Build arr_context for glossary lookup
                arr_context = {}
                if item.get("sonarr_series_id"):
                    arr_context["sonarr_series_id"] = item["sonarr_series_id"]
                if item.get("sonarr_episode_id"):
                    arr_context["sonarr_episode_id"] = item["sonarr_episode_id"]
                if item.get("radarr_movie_id"):
                    arr_context["radarr_movie_id"] = item["radarr_movie_id"]

                job = create_job(file_path, force=False, arr_context=arr_context if arr_context else None)
                update_job(job["id"], "running")
                try:
                    translate_result = translate_srt_from_file(
                        file_path, actual_source_path,
                        source="provider_source_srt",
                        target_language=item_lang,
                        arr_context=arr_context if arr_context else None
                    )
                except Exception as trans_error:
                    logger.error("Wanted %d: Translation failed for source SRT: %s",
                                 item_id, trans_error, exc_info=True)
                    update_job(job["id"], "failed", error=str(trans_error))
                    record_stat(success=False)
                    try:
                        if os.path.exists(actual_source_path):
                            os.remove(actual_source_path)
                    except Exception:
                        pass
                    raise  # skip to next step

                # Clean up temporary source file
                try:
                    if os.path.exists(actual_source_path):
                        os.remove(actual_source_path)
                except Exception:
                    pass

                if translate_result and translate_result.get("success"):
                    update_job(job["id"], "completed", result=translate_result, error=translate_result.get("error"))
                    s = translate_result.get("stats", {})
                    record_stat(success=True, skipped=s.get("skipped", False), fmt=s.get("format", ""), source=s.get("source", ""))
                    logger.info("Wanted %d: Translated source SRT from provider %s",
                               item_id, result.provider_name)
                    update_wanted_status(item_id, "found")
                    return {
                        "wanted_id": item_id,
                        "status": "found",
                        "output_path": translate_result.get("output_path"),
                        "provider": f"{result.provider_name} (translated)",
                    }
                else:
                    update_job(job["id"], "failed", result=translate_result, error=translate_result.get("error") if translate_result else "Translation failed")
                    record_stat(success=False)
        except Exception as e:
            logger.warning("Wanted %d: Source SRT search/translation failed: %s", item_id, e, exc_info=True)

    # Step 5: Fall back to translate_file() which handles embedded subtitles (B1/C1-C4)
    try:
        from translator import translate_file
        # Build arr_context from wanted_item for glossary lookup
        arr_context = {}
        if item.get("sonarr_series_id"):
            arr_context["sonarr_series_id"] = item["sonarr_series_id"]
        if item.get("sonarr_episode_id"):
            arr_context["sonarr_episode_id"] = item["sonarr_episode_id"]
        if item.get("radarr_movie_id"):
            arr_context["radarr_movie_id"] = item["radarr_movie_id"]
        job = create_job(file_path, force=False, arr_context=arr_context if arr_context else None)
        update_job(job["id"], "running")
        translate_result = translate_file(file_path, target_language=item_lang, arr_context=arr_context if arr_context else None)

        if translate_result["success"]:
            update_job(job["id"], "completed", result=translate_result, error=translate_result.get("error"))
            s = translate_result.get("stats", {})
            record_stat(success=True, skipped=s.get("skipped", False), fmt=s.get("format", ""), source=s.get("source", ""))
            if translate_result["stats"].get("skipped"):
                update_wanted_status(item_id, "found")
                return {
                    "wanted_id": item_id,
                    "status": "found",
                    "output_path": translate_result.get("output_path"),
                    "provider": "translate_pipeline",
                }
            else:
                update_wanted_status(item_id, "found")
                return {
                    "wanted_id": item_id,
                    "status": "found",
                    "output_path": translate_result.get("output_path"),
                    "provider": translate_result.get("stats", {}).get("source", "unknown"),
                }
        else:
            error = translate_result.get("error", "Translation failed")
            update_job(job["id"], "failed", result=translate_result, error=error)
            record_stat(success=False)
            update_wanted_status(item_id, "failed", error=error)
            _set_adaptive_retry_after(item_id, item["search_count"] + 1, settings)
            return {
                "wanted_id": item_id,
                "status": "failed",
                "error": error,
            }
    except Exception as e:
        error = str(e)
        try:
            update_job(job["id"], "failed", error=error)
        except Exception:
            pass  # job may not have been created
        try:
            record_stat(success=False)
        except Exception:
            pass
        logger.exception("Wanted %d: Process failed: %s", item_id, error)
        update_wanted_status(item_id, "failed", error=error)
        _set_adaptive_retry_after(item_id, item["search_count"] + 1, settings)
        return {
            "wanted_id": item_id,
            "status": "failed",
            "error": error,
        }


def _process_forced_wanted_item(item, item_id, item_lang, manager):
    """Process a forced wanted item: search with forced_only, download, skip translation.

    Forced subtitles are download-only (no translation per research recommendation).
    Saves to the forced output path (.lang.forced.ext).

    Returns:
        dict: {wanted_id, status, output_path, provider, error}
    """
    file_path = item["file_path"]

    # Build forced query
    query = build_query_from_wanted(item)
    query.languages = [item_lang]
    query.forced_only = True

    # Try target language forced ASS first, then forced SRT
    for fmt in (SubtitleFormat.ASS, SubtitleFormat.SRT):
        try:
            result = manager.search_and_download_best(query, format_filter=fmt)
            if result and result.content:
                ext = result.format.value if result.format != SubtitleFormat.UNKNOWN else fmt.value
                output_path = get_forced_output_path(file_path, fmt=ext, target_language=item_lang)
                try:
                    manager.save_subtitle(result, output_path)
                    record_subtitle_download(
                        result.provider_name, result.subtitle_id, item_lang,
                        result.format.value if result.format.value != "unknown" else fmt.value,
                        file_path, result.score,
                    )
                    logger.info("Wanted %d: Forced subtitle downloaded from %s, skipping translation",
                               item_id, result.provider_name)
                    update_wanted_status(item_id, "found")
                    return {
                        "wanted_id": item_id,
                        "status": "found",
                        "output_path": output_path,
                        "provider": result.provider_name,
                        "forced": True,
                    }
                except (OSError, RuntimeError) as save_error:
                    logger.error("Wanted %d: Failed to save forced subtitle from %s: %s",
                                 item_id, result.provider_name, save_error)
                    # Try next format
                    continue
        except Exception as e:
            logger.warning("Wanted %d: Forced %s search failed: %s", item_id, fmt.value, e, exc_info=True)

    # Also try source language forced subtitles (download-only, no translation)
    settings = get_settings()
    source_lang = settings.source_language
    source_query = build_query_from_wanted(item)
    source_query.languages = [source_lang]
    source_query.forced_only = True

    for fmt in (SubtitleFormat.ASS, SubtitleFormat.SRT):
        try:
            result = manager.search_and_download_best(source_query, format_filter=fmt)
            if result and result.content:
                ext = result.format.value if result.format != SubtitleFormat.UNKNOWN else fmt.value
                output_path = get_forced_output_path(file_path, fmt=ext, target_language=source_lang)
                try:
                    manager.save_subtitle(result, output_path)
                    record_subtitle_download(
                        result.provider_name, result.subtitle_id, source_lang,
                        result.format.value if result.format.value != "unknown" else fmt.value,
                        file_path, result.score,
                    )
                    logger.info("Wanted %d: Forced subtitle (source lang) downloaded from %s, skipping translation",
                               item_id, result.provider_name)
                    update_wanted_status(item_id, "found")
                    return {
                        "wanted_id": item_id,
                        "status": "found",
                        "output_path": output_path,
                        "provider": result.provider_name,
                        "forced": True,
                    }
                except (OSError, RuntimeError) as save_error:
                    logger.error("Wanted %d: Failed to save forced subtitle (source) from %s: %s",
                                 item_id, result.provider_name, save_error)
                    # Try next format
                    continue
        except Exception as e:
            logger.warning("Wanted %d: Forced source %s search failed: %s", item_id, fmt.value, e, exc_info=True)

    # No forced subtitle found
    error = "No forced subtitle found from any provider"
    update_wanted_status(item_id, "failed", error=error)
    return {
        "wanted_id": item_id,
        "status": "failed",
        "error": error,
        "forced": True,
    }


def process_wanted_batch(item_ids=None, app=None):
    """Process multiple wanted items with parallel execution.

    Uses ThreadPoolExecutor for parallel processing. Provider-level rate
    limiters and circuit breakers handle concurrency safety. Error isolation
    ensures one item failure doesn't abort the batch.

    Args:
        item_ids: List of specific IDs, or None for all 'wanted' items.
        app: Flask app instance. Each worker thread pushes its own app context.

    Yields:
        Progress dicts for each item processed.
    """
    settings = get_settings()
    max_attempts = settings.wanted_max_search_attempts

    if item_ids:
        items = []
        for iid in item_ids:
            item = get_wanted_item(iid)
            if item:
                items.append(item)
    else:
        result = get_wanted_items(page=1, per_page=10000, status="wanted")
        items = result.get("data", [])

    # Filter out items that exceeded max search attempts
    items = [i for i in items if i["search_count"] < max_attempts]

    total = len(items)
    processed = 0
    found = 0
    failed = 0
    skipped = 0

    def _run_item(item_id):
        if app is not None:
            with app.app_context():
                return process_wanted_item(item_id)
        return process_wanted_item(item_id)

    max_workers = min(4, total) if total > 0 else 1
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_item = {
            executor.submit(_run_item, item["id"]): item
            for item in items
        }

        for future in as_completed(future_to_item):
            item = future_to_item[future]
            item_id = item["id"]
            display = item.get("title", item.get("file_path", str(item_id)))

            try:
                result = future.result()
                processed += 1

                if result.get("status") == "found":
                    found += 1
                elif result.get("status") == "failed":
                    failed += 1
                else:
                    skipped += 1

                yield {
                    "processed": processed,
                    "total": total,
                    "found": found,
                    "failed": failed,
                    "skipped": skipped,
                    "current_item": display,
                    "last_result": result,
                }

            except Exception as e:
                processed += 1
                failed += 1
                logger.exception("Batch: error processing wanted %d: %s", item_id, e)
                yield {
                    "processed": processed,
                    "total": total,
                    "found": found,
                    "failed": failed,
                    "skipped": skipped,
                    "current_item": display,
                    "last_result": {"wanted_id": item_id, "status": "failed", "error": str(e)},
                }


def _result_to_dict(result) -> dict:
    """Convert a SubtitleResult to a JSON-serializable dict."""
    return {
        "provider": result.provider_name,
        "subtitle_id": result.subtitle_id,
        "language": result.language,
        "format": result.format.value,
        "filename": result.filename,
        "release_info": result.release_info,
        "score": result.score,
        "hearing_impaired": result.hearing_impaired,
        "matches": list(result.matches),
    }


# ─── Interactive Search ───────────────────────────────────────────────────────


def search_providers_for_item(item_id: int) -> dict:
    """Search all providers for a wanted item, returning all results for interactive selection.

    Unlike search_wanted_item(), this searches all formats and both target+source
    languages in a single pass, returning a flat result list sorted by score.
    Used by the interactive search modal (arr-style manual search).

    Returns:
        dict: {results, total, item}
    """
    item = get_wanted_item(item_id)
    if not item:
        return {"error": "Item not found", "wanted_id": item_id}

    settings = get_settings()
    manager = get_provider_manager()
    item_lang = item.get("target_language") or settings.target_language
    source_lang = settings.source_language

    # Search both languages in a single pass (deduplicated set)
    query = build_query_from_wanted(item)
    query.languages = list({item_lang, source_lang})

    all_results = []
    try:
        results = manager.search(query, early_exit=False)
        all_results.extend(results)
    except Exception as e:
        logger.error("Interactive search failed for wanted %d: %s", item_id, e)

    # Deduplicate by (provider_name, subtitle_id)
    seen = set()
    unique_results = []
    for r in all_results:
        key = (r.provider_name, r.subtitle_id)
        if key not in seen:
            seen.add(key)
            unique_results.append(r)

    # Sort: ASS first, then by score descending
    unique_results.sort(key=lambda r: (0 if r.format.value == "ass" else 1, -r.score))

    update_wanted_search(item_id)

    return {
        "results": [_result_to_dict_interactive(r) for r in unique_results],
        "total": len(unique_results),
        "item": {
            "id": item["id"],
            "title": item.get("title", ""),
            "item_type": item.get("item_type", "episode"),
        },
    }


def download_specific_for_item(
    item_id: int,
    provider_name: str,
    subtitle_id: str,
    language: str,
    translate: bool,
) -> dict:
    """Download a specific subtitle result and optionally translate it.

    Re-searches providers to find the specific result by provider_name + subtitle_id,
    downloads it, saves it to disk, and optionally runs the translation pipeline.
    When translate=True and language != item_lang, the subtitle is saved as a
    temporary source file and the translation pipeline is triggered.

    Returns:
        dict: {success, path, format, translated, error}
    """
    item = get_wanted_item(item_id)
    if not item:
        return {"success": False, "error": "Item not found"}

    settings = get_settings()
    item_lang = item.get("target_language") or settings.target_language
    manager = get_provider_manager()
    file_path = item["file_path"]

    # Build query for the given language and re-search to find the specific result
    query = build_query_from_wanted(item)
    query.languages = [language]

    try:
        results = manager.search(query)
    except Exception as e:
        logger.error("Search failed during download_specific for wanted %d: %s", item_id, e)
        return {"success": False, "error": f"Search failed: {e}"}

    target_result = None
    for r in results:
        if r.provider_name == provider_name and r.subtitle_id == subtitle_id:
            target_result = r
            break

    if not target_result:
        return {"success": False, "error": f"Result not found: {provider_name}/{subtitle_id}"}

    content = manager.download(target_result)
    if content is None:
        return {"success": False, "error": "Download failed"}

    from translator import get_output_path_for_lang
    fmt_ext = target_result.format.value if target_result.format.value != "unknown" else "srt"

    # When translate=True and we have a non-target language: save + translate
    if translate and language != item_lang:
        base = os.path.splitext(file_path)[0]
        tmp_source_path = f"{base}.{language}.{fmt_ext}"

        try:
            actual_source_path = manager.save_subtitle(target_result, tmp_source_path)
            record_subtitle_download(
                provider_name, subtitle_id, language, fmt_ext,
                file_path, target_result.score,
            )
        except (OSError, RuntimeError) as e:
            return {"success": False, "error": f"Failed to save subtitle: {e}"}

        arr_context = {}
        for key in ("sonarr_series_id", "sonarr_episode_id", "radarr_movie_id"):
            if item.get(key):
                arr_context[key] = item[key]

        # Create a translation job so it appears in Activity/Queue
        job = create_job(file_path, force=False, arr_context=arr_context or None)
        update_job(job["id"], "running")
        try:
            if actual_source_path.endswith(".ass"):
                from translator import _translate_external_ass
                translate_result = _translate_external_ass(
                    file_path, actual_source_path,
                    target_language=item_lang,
                    target_language_name=settings.target_language_name,
                    arr_context=arr_context or None,
                )
            else:
                from translator import translate_srt_from_file
                translate_result = translate_srt_from_file(
                    file_path, actual_source_path,
                    source="provider_interactive",
                    target_language=item_lang,
                    arr_context=arr_context or None,
                )
        except Exception as e:
            logger.error("Translation failed in download_specific for wanted %d: %s", item_id, e, exc_info=True)
            update_job(job["id"], "failed", error=str(e))
            record_stat(success=False)
            try:
                if os.path.exists(actual_source_path):
                    os.remove(actual_source_path)
            except Exception:
                pass
            return {"success": False, "error": f"Translation failed: {e}"}

        try:
            if os.path.exists(actual_source_path):
                os.remove(actual_source_path)
        except Exception:
            pass

        if not translate_result or not translate_result.get("success"):
            err = translate_result.get("error", "Translation failed") if translate_result else "Translation failed"
            update_job(job["id"], "failed", result=translate_result, error=err)
            record_stat(success=False)
            return {"success": False, "error": err}

        status = "completed"
        update_job(job["id"], status, result=translate_result, error=translate_result.get("error"))
        s = translate_result.get("stats", {})
        record_stat(
            success=True,
            skipped=s.get("skipped", False),
            fmt=s.get("format", ""),
            source=s.get("source", ""),
        )
        update_wanted_status(item_id, "found")
        out = translate_result.get("output_path")
        if out:
            _try_auto_sync(out, file_path, settings)
        return {
            "success": True,
            "path": out,
            "format": "ass",
            "translated": True,
        }

    # Download only (no translation)
    output_path = get_output_path_for_lang(file_path, fmt_ext, language)
    try:
        actual_path = manager.save_subtitle(target_result, output_path)
        record_subtitle_download(
            provider_name, subtitle_id, language, fmt_ext,
            file_path, target_result.score,
        )
    except (OSError, RuntimeError) as e:
        return {"success": False, "error": f"Failed to save subtitle: {e}"}

    update_wanted_status(item_id, "found")
    _try_auto_sync(actual_path, file_path, settings)
    return {
        "success": True,
        "path": actual_path,
        "format": fmt_ext,
        "translated": False,
    }


def _result_to_dict_interactive(result) -> dict:
    """Convert a SubtitleResult to a JSON-serializable dict for the interactive search API.

    Uses provider_name key (not provider) for consistency with the download-specific endpoint.
    """
    return {
        "provider_name": result.provider_name,
        "subtitle_id": result.subtitle_id,
        "language": result.language,
        "format": result.format.value,
        "filename": result.filename,
        "release_info": result.release_info,
        "score": result.score,
        "hearing_impaired": result.hearing_impaired,
        "forced": result.forced,
        "matches": list(result.matches),
        "machine_translated": getattr(result, "machine_translated", False),
        "mt_confidence": getattr(result, "mt_confidence", 0.0),
        "uploader_trust_bonus": getattr(result, "uploader_trust", 0.0),
        "uploader_name": getattr(result, "uploader_name", ""),
    }


# ─── Video Sync ───────────────────────────────────────────────────────────────


def _try_auto_sync(subtitle_path: str, video_path: str, settings) -> None:
    """Enqueue a sync job if auto_sync_after_download is enabled.

    Only ffsubsync is supported for auto-sync (alass requires a reference track).
    Errors are logged but never propagated — sync is best-effort.
    """
    if not getattr(settings, "auto_sync_after_download", False):
        return
    engine = getattr(settings, "auto_sync_engine", "ffsubsync")
    if engine != "ffsubsync":
        logger.warning("Auto-sync: alass requires a reference track — skipping auto-sync for %s", subtitle_path)
        return
    try:
        from services.video_sync import sync_with_ffsubsync, SyncUnavailableError
        logger.info("Auto-sync: starting ffsubsync for %s against %s", subtitle_path, video_path)
        sync_with_ffsubsync(subtitle_path, video_path)
        logger.info("Auto-sync: complete for %s", subtitle_path)
    except SyncUnavailableError as e:
        logger.warning("Auto-sync skipped: %s", e)
    except Exception as e:
        logger.error("Auto-sync failed for %s: %s", subtitle_path, e)


# ─── Job Queue Integration ────────────────────────────────────────────────────


def _get_job_queue():
    """Get the app-level job queue backend, or None.

    Uses Flask's current_app to access the job_queue. Returns None if called
    outside Flask context or if job_queue is not configured. Never raises.
    """
    try:
        from flask import current_app
        return getattr(current_app, 'job_queue', None)
    except (RuntimeError, ImportError):
        return None


def submit_wanted_search(item_id, job_id=None):
    """Submit a wanted search job via the app job queue.

    When a job queue is available (RQ with Redis, or MemoryJobQueue), the
    process_wanted_item function is enqueued for background execution. When
    no queue is available, falls back to direct synchronous execution.

    For the MemoryJobQueue fallback, this behaves identically to the current
    ThreadPoolExecutor pattern. For RQ, jobs survive container restarts and
    can be monitored via the queue API.

    Args:
        item_id: Wanted item ID to process.
        job_id: Optional custom job ID. Defaults to "wanted-{item_id}".

    Returns:
        str: Job ID if enqueued via queue, or the result dict if executed directly.
    """
    queue = _get_job_queue()
    if queue:
        try:
            _job_id = job_id or f"wanted-{item_id}"
            return queue.enqueue(
                process_wanted_item,
                item_id,
                job_id=_job_id,
            )
        except Exception as e:
            logger.warning("Job queue submission failed for wanted %d, executing directly: %s",
                           item_id, e)

    # Fallback: direct synchronous execution
    return process_wanted_item(item_id)


def submit_wanted_batch_search(item_ids=None):
    """Submit wanted batch search jobs via the app job queue.

    When a job queue is available, each item is submitted as a separate job
    for independent execution and monitoring. When no queue is available,
    falls back to the existing process_wanted_batch() generator.

    Args:
        item_ids: List of specific item IDs, or None for all 'wanted' items.

    Returns:
        list[str]: List of job IDs if enqueued via queue, or processes directly.
    """
    queue = _get_job_queue()
    if queue and item_ids:
        try:
            return [
                queue.enqueue(
                    process_wanted_item,
                    iid,
                    job_id=f"wanted-{iid}",
                )
                for iid in item_ids
            ]
        except Exception as e:
            logger.warning("Job queue batch submission failed, executing directly: %s", e)

    # Fallback: direct execution via existing batch processor
    results = []
    for progress in process_wanted_batch(item_ids):
        results.append(progress)
    return results
