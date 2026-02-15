"""Wanted search module — connects Wanted items with the Provider system.

Builds VideoQueries from wanted items, searches providers, downloads best
results, and triggers translation. Processes items sequentially to respect
provider rate limits.
"""

import os
import time
import logging

from config import get_settings, map_path
from db.wanted import get_wanted_item, get_wanted_items, update_wanted_status, update_wanted_search
from db.library import record_upgrade
from upgrade_scorer import should_upgrade
from providers import get_provider_manager
from providers.base import VideoQuery, SubtitleFormat

logger = logging.getLogger(__name__)

INTER_ITEM_DELAY = 0.5  # seconds between items (rate-limit protection)


def _parse_filename_for_metadata(file_path: str) -> dict:
    """Parse filename to extract series title, season, episode, year.
    
    Returns dict with: series_title, season, episode, year, title
    """
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

    # Build queries
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
        logger.warning("Target ASS search failed for wanted %d: %s", item_id, e)

    # Search 2: source_language ASS (Priority 2)
    try:
        results = manager.search(source_query, format_filter=SubtitleFormat.ASS)
        all_results.extend([_result_to_dict(r) for r in results[:20]])
    except Exception as e:
        logger.warning("Source ASS search failed for wanted %d: %s", item_id, e)

    # Search 3: target_language SRT (Priority 3)
    try:
        results = manager.search(target_query, format_filter=SubtitleFormat.SRT)
        all_results.extend([_result_to_dict(r) for r in results[:20]])
    except Exception as e:
        logger.warning("Target SRT search failed for wanted %d: %s", item_id, e)

    # Search 4: source_language SRT (Priority 4)
    try:
        results = manager.search(source_query, format_filter=SubtitleFormat.SRT)
        all_results.extend([_result_to_dict(r) for r in results[:20]])
    except Exception as e:
        logger.warning("Source SRT search failed for wanted %d: %s", item_id, e)

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
    manager = get_provider_manager()

    # Step 1: Try to find target language ASS directly from providers (Priority 1)
    query = build_query_from_wanted(item)
    query.languages = [item_lang]

    try:
        result = manager.search_and_download_best(
            query, format_filter=SubtitleFormat.ASS
        )
        if result and result.content:
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

            manager.save_subtitle(result, output_path)
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
    except Exception as e:
        logger.warning("Wanted %d: Direct target ASS search failed: %s", item_id, e)

    # Step 2: Try to find source language ASS for translation (Priority 2)
    source_query = build_query_from_wanted(item)
    source_query.languages = [settings.source_language]

    try:
        result = manager.search_and_download_best(
            source_query, format_filter=SubtitleFormat.ASS
        )
        if result and result.content:
            # Download source ASS and translate it
            from translator import get_output_path_for_lang, _translate_external_ass
            base = os.path.splitext(file_path)[0]
            tmp_source_path = f"{base}.{settings.source_language}.ass"
            manager.save_subtitle(result, tmp_source_path)
            
            # Build arr_context for glossary lookup
            arr_context = {}
            if item.get("sonarr_series_id"):
                arr_context["sonarr_series_id"] = item["sonarr_series_id"]
            if item.get("sonarr_episode_id"):
                arr_context["sonarr_episode_id"] = item["sonarr_episode_id"]
            if item.get("radarr_movie_id"):
                arr_context["radarr_movie_id"] = item["radarr_movie_id"]

            translate_result = _translate_external_ass(
                file_path, tmp_source_path,
                target_language=item_lang,
                target_language_name=settings.target_language_name,
                arr_context=arr_context if arr_context else None
            )
            
            # Clean up temporary source file
            try:
                if os.path.exists(tmp_source_path):
                    os.remove(tmp_source_path)
            except Exception:
                pass
            
            if translate_result and translate_result.get("success"):
                logger.info("Wanted %d: Translated source ASS from provider %s",
                           item_id, result.provider_name)
                update_wanted_status(item_id, "found")
                return {
                    "wanted_id": item_id,
                    "status": "found",
                    "output_path": translate_result.get("output_path"),
                    "provider": f"{result.provider_name} (translated)",
                }
    except Exception as e:
        logger.warning("Wanted %d: Source ASS search/translation failed: %s", item_id, e)

    # Step 3: Try to find target language SRT directly (Priority 3)
    try:
        result = manager.search_and_download_best(
            query, format_filter=SubtitleFormat.SRT
        )
        if result and result.content:
            from translator import get_output_path_for_lang
            output_path = get_output_path_for_lang(file_path, "srt", item_lang)
            manager.save_subtitle(result, output_path)
            logger.info("Wanted %d: Provider %s delivered target SRT directly",
                         item_id, result.provider_name)
            update_wanted_status(item_id, "found")
            return {
                "wanted_id": item_id,
                "status": "found",
                "output_path": output_path,
                "provider": result.provider_name,
            }
    except Exception as e:
        logger.warning("Wanted %d: Direct target SRT search failed: %s", item_id, e)

    # Step 4: Try to find source language SRT for translation (Priority 4)
    try:
        result = manager.search_and_download_best(
            source_query, format_filter=SubtitleFormat.SRT
        )
        if result and result.content:
            # Download source SRT and translate it
            from translator import get_output_path_for_lang, translate_srt_from_file
            base = os.path.splitext(file_path)[0]
            tmp_source_path = f"{base}.{settings.source_language}.srt"
            manager.save_subtitle(result, tmp_source_path)
            
            # Build arr_context for glossary lookup
            arr_context = {}
            if item.get("sonarr_series_id"):
                arr_context["sonarr_series_id"] = item["sonarr_series_id"]
            if item.get("sonarr_episode_id"):
                arr_context["sonarr_episode_id"] = item["sonarr_episode_id"]
            if item.get("radarr_movie_id"):
                arr_context["radarr_movie_id"] = item["radarr_movie_id"]

            translate_result = translate_srt_from_file(
                file_path, tmp_source_path,
                source="provider_source_srt",
                target_language=item_lang,
                arr_context=arr_context if arr_context else None
            )
            
            # Clean up temporary source file
            try:
                if os.path.exists(tmp_source_path):
                    os.remove(tmp_source_path)
            except Exception:
                pass
            
            if translate_result and translate_result.get("success"):
                logger.info("Wanted %d: Translated source SRT from provider %s",
                           item_id, result.provider_name)
                update_wanted_status(item_id, "found")
                return {
                    "wanted_id": item_id,
                    "status": "found",
                    "output_path": translate_result.get("output_path"),
                    "provider": f"{result.provider_name} (translated)",
                }
    except Exception as e:
        logger.warning("Wanted %d: Source SRT search/translation failed: %s", item_id, e)

    # Step 5: Fall back to translate_file() which handles embedded subtitles (B1/C1-C4)
    try:
        from translator import translate_file
        # Build arr_context from wanted_item for glossary lookup
        arr_context = {}
        if item.get("sonarr_series_id"):
            arr_context["sonarr_series_id"] = item["sonarr_series_id"]
        if item.get("sonarr_episode_id"):
            arr_context["sonarr_episode_id"] = item["sonarr_episode_id"]
        translate_result = translate_file(file_path, target_language=item_lang, arr_context=arr_context if arr_context else None)

        if translate_result["success"]:
            if translate_result["stats"].get("skipped"):
                # Already had a subtitle — mark as found
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
            update_wanted_status(item_id, "failed", error=error)
            return {
                "wanted_id": item_id,
                "status": "failed",
                "error": error,
            }
    except Exception as e:
        error = str(e)
        logger.exception("Wanted %d: Process failed: %s", item_id, error)
        update_wanted_status(item_id, "failed", error=error)
        return {
            "wanted_id": item_id,
            "status": "failed",
            "error": error,
        }


def process_wanted_batch(item_ids=None):
    """Process multiple wanted items sequentially.

    Args:
        item_ids: List of specific IDs, or None for all 'wanted' items.

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

    for item in items:
        item_id = item["id"]
        display = item.get("title", item.get("file_path", str(item_id)))

        try:
            result = process_wanted_item(item_id)
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

        # Rate-limit protection between items
        if processed < total:
            time.sleep(INTER_ITEM_DELAY)


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
