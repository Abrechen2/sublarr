"""Translation manager orchestration: glossary, cache, batching, fallback."""

import logging
import sys

from translation import get_translation_manager
from translator._helpers import (
    _get_cache_config,
    _resolve_backend_for_context,
)
from translator.cache import _apply_translation_cache, _store_translations_in_cache

logger = logging.getLogger(__name__)


def _pkg():
    """Return the translator package module (for patchable symbol lookup)."""
    return sys.modules["translator"]


def _translate_with_manager(lines, source_lang, target_lang, arr_context=None, series_id=None):
    """Translate lines using TranslationManager with profile-based backend selection.

    Resolves the backend and fallback chain from the language profile associated
    with the arr_context, loads glossary entries if a series_id is provided,
    and delegates to TranslationManager.translate_with_fallback().

    Args:
        lines: List of subtitle text lines to translate
        source_lang: ISO 639-1 source language code
        target_lang: ISO 639-1 target language code
        arr_context: Optional dict with sonarr_series_id or radarr_movie_id
        series_id: Optional Sonarr series ID for glossary lookup

    Returns:
        tuple[list[str], TranslationResult]: Translated lines and result metadata

    Raises:
        RuntimeError: If all backends in the fallback chain fail
    """
    _backend_name, fallback_chain = _resolve_backend_for_context(arr_context, target_lang)

    glossary_entries = _load_glossary_entries(series_id)

    # --- Translation memory cache lookup ---
    cache_enabled, similarity_threshold = _get_cache_config()

    if cache_enabled and lines:
        cached_results, uncached_indices, uncached_lines = _apply_translation_cache(
            lines, source_lang, target_lang, similarity_threshold
        )
        cache_hits = sum(1 for r in cached_results if r is not None)
        if cache_hits:
            logger.debug(
                "Translation memory: %d/%d lines from cache, %d need LLM",
                cache_hits,
                len(lines),
                len(uncached_lines),
            )
    else:
        cached_results = [None] * len(lines)
        uncached_indices = list(range(len(lines)))
        uncached_lines = list(lines)

    # If every line was served from cache, skip LLM entirely
    if not uncached_lines:
        from translation.base import TranslationResult

        synthetic = TranslationResult(
            success=True,
            translated_lines=cached_results,
            backend_name="translation_memory",
            error=None,
        )
        return cached_results, synthetic

    # Translate only the uncached lines via LLM, in batch_size chunks
    manager = get_translation_manager()
    _get_settings = _pkg().get_settings
    batch_size = getattr(_get_settings(), "batch_size", 15) or 15

    all_translated, result = _translate_in_batches(
        manager,
        uncached_lines,
        source_lang,
        target_lang,
        fallback_chain,
        glossary_entries,
        batch_size,
    )

    # Merge cached + freshly translated lines in original order
    output = list(cached_results)
    for out_idx, translated in zip(uncached_indices, all_translated):
        output[out_idx] = translated

    # Persist newly translated lines to cache
    if cache_enabled:
        _store_translations_in_cache(uncached_lines, all_translated, source_lang, target_lang)

    return output, result


def _load_glossary_entries(series_id):
    """Load glossary entries (global + per-series) if glossary is enabled.

    Args:
        series_id: Optional Sonarr series ID for per-series glossary

    Returns:
        list[dict] | None: Glossary entries or None if disabled/unavailable
    """
    _get_settings = _pkg().get_settings
    if not getattr(_get_settings(), "glossary_enabled", True):
        return None

    try:
        if series_id:
            from db.translation import get_merged_glossary_for_series

            entries = get_merged_glossary_for_series(series_id)
            if entries:
                max_terms = getattr(_get_settings(), "glossary_max_terms", 100)
                entries = entries[:max_terms]
                logger.debug(
                    "Loaded %d merged glossary entries for series %d",
                    len(entries),
                    series_id,
                )
                return entries
        else:
            from db.translation import get_global_glossary

            global_entries = get_global_glossary()
            if global_entries:
                max_terms = getattr(_get_settings(), "glossary_max_terms", 100)
                global_entries = global_entries[:max_terms]
                result = [
                    {"source_term": e["source_term"], "target_term": e["target_term"]}
                    for e in global_entries
                ]
                logger.debug("Loaded %d global glossary entries", len(result))
                return result
    except Exception as e:
        logger.debug("Failed to load glossary: %s", e)

    return None


def _translate_in_batches(
    manager,
    lines,
    source_lang,
    target_lang,
    fallback_chain,
    glossary_entries,
    batch_size,
):
    """Translate lines via LLM, chunking into batches if needed.

    Args:
        manager: TranslationManager instance
        lines: Lines to translate (uncached subset)
        source_lang: Source language code
        target_lang: Target language code
        fallback_chain: List of backend names to try in order
        glossary_entries: Optional glossary entries for translation
        batch_size: Maximum lines per LLM call

    Returns:
        tuple[list[str], TranslationResult]: All translated lines and last result
    """
    if len(lines) <= batch_size:
        result = manager.translate_with_fallback(
            lines, source_lang, target_lang, fallback_chain, glossary_entries
        )
        if not result.success:
            raise RuntimeError(f"Translation failed: {result.error}")
        return result.translated_lines, result

    logger.debug("Chunking %d lines into batches of %d", len(lines), batch_size)
    all_translated: list[str] = []
    last_result = None

    for chunk_start in range(0, len(lines), batch_size):
        chunk = lines[chunk_start : chunk_start + batch_size]
        chunk_result = manager.translate_with_fallback(
            chunk, source_lang, target_lang, fallback_chain, glossary_entries
        )
        if not chunk_result.success:
            raise RuntimeError(
                f"Translation failed on batch {chunk_start // batch_size + 1}: {chunk_result.error}"
            )
        if len(chunk_result.translated_lines) != len(chunk):
            raise RuntimeError(
                f"Chunk translation returned {len(chunk_result.translated_lines)} lines, "
                f"expected {len(chunk)}. Aborting to prevent cache pollution."
            )
        all_translated.extend(chunk_result.translated_lines)
        last_result = chunk_result

    return all_translated, last_result
