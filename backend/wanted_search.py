"""Wanted search module — connects Wanted items with the Provider system.

Builds VideoQueries from wanted items, searches providers, downloads best
results, and triggers translation. Processes items sequentially to respect
provider rate limits.
"""

import os
import time
import logging

from config import get_settings, map_path
from database import (
    get_wanted_item,
    get_wanted_items,
    update_wanted_status,
    update_wanted_search,
)
from providers import get_provider_manager
from providers.base import VideoQuery, SubtitleFormat

logger = logging.getLogger(__name__)

INTER_ITEM_DELAY = 0.5  # seconds between items (rate-limit protection)


def build_query_from_wanted(wanted_item: dict) -> VideoQuery:
    """Build a rich VideoQuery from a wanted item + Sonarr/Radarr metadata.

    Fetches series/movie metadata from the relevant *arr client to enrich
    the query with titles, IDs, season/episode numbers, etc.
    """
    settings = get_settings()

    query = VideoQuery(
        file_path=wanted_item["file_path"],
        languages=[settings.target_language],
    )

    if wanted_item["item_type"] == "episode":
        series_id = wanted_item.get("sonarr_series_id")
        episode_id = wanted_item.get("sonarr_episode_id")

        if series_id and episode_id:
            try:
                from sonarr_client import get_sonarr_client
                sonarr = get_sonarr_client()
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
            except Exception as e:
                logger.warning("Failed to get Sonarr metadata for wanted %d: %s",
                               wanted_item["id"], e)

    elif wanted_item["item_type"] == "movie":
        movie_id = wanted_item.get("radarr_movie_id")

        if movie_id:
            try:
                from radarr_client import get_radarr_client
                radarr = get_radarr_client()
                if radarr:
                    meta = radarr.get_movie_metadata(movie_id)
                    if meta:
                        query.title = meta.get("title", "")
                        query.year = meta.get("year")
                        query.imdb_id = meta.get("imdb_id", "")
            except Exception as e:
                logger.warning("Failed to get Radarr metadata for wanted %d: %s",
                               wanted_item["id"], e)

    return query


def search_wanted_item(item_id: int) -> dict:
    """Search providers for a single wanted item.

    Returns:
        dict: {wanted_id, target_results, source_results}
    """
    item = get_wanted_item(item_id)
    if not item:
        return {"error": "Item not found", "wanted_id": item_id}

    settings = get_settings()
    manager = get_provider_manager()

    # Build query for target language ASS
    query = build_query_from_wanted(item)
    query.languages = [settings.target_language]

    target_results = []
    try:
        results = manager.search(query, format_filter=SubtitleFormat.ASS)
        target_results = [_result_to_dict(r) for r in results[:20]]
    except Exception as e:
        logger.warning("Target ASS search failed for wanted %d: %s", item_id, e)

    # Build query for source language (for translation)
    source_query = build_query_from_wanted(item)
    source_query.languages = [settings.source_language]

    source_results = []
    try:
        results = manager.search(source_query)
        source_results = [_result_to_dict(r) for r in results[:20]]
    except Exception as e:
        logger.warning("Source sub search failed for wanted %d: %s", item_id, e)

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

    # Step 1: Try to find target language ASS directly from providers
    manager = get_provider_manager()
    query = build_query_from_wanted(item)
    query.languages = [settings.target_language]

    try:
        result = manager.search_and_download_best(
            query, format_filter=SubtitleFormat.ASS
        )
        if result and result.content:
            from translator import get_output_path
            output_path = get_output_path(file_path, "ass")
            manager.save_subtitle(result, output_path)
            logger.info("Wanted %d: Provider %s delivered target ASS directly",
                         item_id, result.provider_name)
            update_wanted_status(item_id, "found")
            return {
                "wanted_id": item_id,
                "status": "found",
                "output_path": output_path,
                "provider": result.provider_name,
            }
    except Exception as e:
        logger.warning("Wanted %d: Direct target ASS search failed: %s", item_id, e)

    # Step 2: Fall back to translate_file() which handles all cases (B1/C1-C4)
    try:
        from translator import translate_file
        translate_result = translate_file(file_path)

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
