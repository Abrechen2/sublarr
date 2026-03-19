"""Wanted search — provider search functions."""

import logging

from config import get_settings
from db.wanted import get_wanted_item, update_wanted_search
from providers import get_provider_manager
from providers.base import SubtitleFormat
from wanted_search.metadata import build_query_from_wanted
from wanted_search.scoring import _apply_fansub_rules, _get_priority_key

logger = logging.getLogger(__name__)


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
        "score_breakdown": result.score_breakdown,
        "hearing_impaired": result.hearing_impaired,
        "matches": list(result.matches),
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
        "score_breakdown": result.score_breakdown,
        "hearing_impaired": result.hearing_impaired,
        "forced": result.forced,
        "matches": list(result.matches),
        "machine_translated": getattr(result, "machine_translated", False),
        "mt_confidence": getattr(result, "mt_confidence", 0.0),
        "uploader_trust_bonus": getattr(result, "uploader_trust", 0.0),
        "uploader_name": getattr(result, "uploader_name", ""),
    }


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

    # Apply per-series fansub group preferences
    series_id = item.get("sonarr_series_id")
    if series_id:
        from db.repositories.fansub_prefs import FansubPreferenceRepository

        fansub = FansubPreferenceRepository().get_fansub_prefs(series_id)
        if fansub:
            _apply_fansub_rules(
                all_results,
                preferred=fansub["preferred_groups"],
                excluded=fansub["excluded_groups"],
                bonus=fansub["bonus"],
            )

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
