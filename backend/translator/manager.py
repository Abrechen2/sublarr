"""Translation manager orchestration: glossary, cache, batching, fallback."""

import logging
import sys

from services.scheduler.cancellation import abort_requested
from translation import get_translation_manager
from translation.context_windower import build_chunks
from translator._helpers import (
    _get_cache_config,
    _resolve_backend_for_context,
)
from translator.cache import _apply_translation_cache, _store_translations_in_cache
from translator.errors import TranslationAbortedError
from translator.output_guard import find_chat_filler

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
        cache_enabled=cache_enabled,
    )

    # Merge cached + freshly translated lines in original order
    output = list(cached_results)
    for out_idx, translated in zip(uncached_indices, all_translated):
        output[out_idx] = translated

    # No bulk write here any more. `_translate_in_batches` stores each batch
    # the moment it is verified, so a run that dies partway keeps what it
    # finished. Writing again here would store every line a second time.

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


def _cache_batch(cache_enabled, source_lines, result, source_lang, target_lang):
    """Write one verified batch to the translation memory.

    The backend name comes off this batch's own result rather than the file's
    last one: with a fallback chain, batches in a single file can legitimately
    come from different backends, and the memory records which produced what.
    """
    if not cache_enabled:
        return
    _store_translations_in_cache(
        list(source_lines),
        list(result.translated_lines),
        source_lang,
        target_lang,
        backend=getattr(result, "backend_name", None),
    )


def _verify_batch(result, expected_count, batch_label):
    """Verify one backend result before it may reach the file or the cache.

    Checks line count and rejects chat filler. The count check alone cannot
    catch a conversational reply in a single-line batch — that reply is
    exactly one line — which is how 1124 chat replies reached the prod
    translation memory during the batch_size=1 era.

    Raises:
        RuntimeError: If the count is off or a line is filler, so the batch
            fails like any other translation failure and nothing is cached.
    """
    if len(result.translated_lines) != expected_count:
        raise RuntimeError(
            f"{batch_label} returned {len(result.translated_lines)} lines, "
            f"expected {expected_count}. Aborting to prevent cache pollution."
        )
    suspects = find_chat_filler(result.translated_lines)
    if suspects:
        idx, text = suspects[0]
        raise RuntimeError(
            f"{batch_label} returned chat filler instead of a translation "
            f"(line {idx + 1}: {text[:80]!r}). Aborting to prevent cache pollution."
        )


def _translate_in_batches(
    manager,
    lines,
    source_lang,
    target_lang,
    fallback_chain,
    glossary_entries,
    batch_size,
    cache_enabled=True,
):
    """Translate lines via LLM, chunking into batches if needed.

    Each batch is written to the translation memory as soon as it comes back
    verified, rather than the whole file being written once at the end. A run
    that stops partway — a line-count mismatch, a container restart, a
    scheduler timeout — then keeps the batches it finished, and the next
    attempt pays only for the remainder. The memory is the resume mechanism;
    there is no progress column and no partial file on disk.

    Prod 2026-08-16: 176 failed translation jobs against 160 successful in 24
    hours, failures observed as deep as batch 150, every one of them
    discarding everything before it.

    Args:
        manager: TranslationManager instance
        lines: Lines to translate (uncached subset)
        source_lang: Source language code
        target_lang: Target language code
        fallback_chain: List of backend names to try in order
        glossary_entries: Optional glossary entries for translation
        batch_size: Maximum lines per LLM call
        cache_enabled: Whether to write finished batches to the translation
            memory. The caller has already resolved this; passing it avoids a
            second config read per file.

    Returns:
        tuple[list[str], TranslationResult]: All translated lines and last result
    """
    if len(lines) <= batch_size:
        # Single batch path: no surrounding lines to provide as context.
        result = manager.translate_with_fallback(
            lines, source_lang, target_lang, fallback_chain, glossary_entries
        )
        if not result.success:
            raise RuntimeError(f"Translation failed: {result.error}")
        _verify_batch(result, len(lines), "Translation")
        _cache_batch(cache_enabled, lines, result, source_lang, target_lang)
        return result.translated_lines, result

    # Multi-batch path: pre-chunk the file with lookback/lookahead context so
    # LLM backends can resolve pronouns and keep terminology consistent across
    # batch boundaries. See translation.context_windower.build_chunks.
    _get_settings = _pkg().get_settings
    settings = _get_settings()
    if getattr(settings, "translation_context_enabled", True):
        lookback_n = getattr(settings, "translation_context_lookback_lines", 10)
        lookahead_n = getattr(settings, "translation_context_lookahead_lines", 5)
    else:
        lookback_n = 0
        lookahead_n = 0

    chunks = build_chunks(
        lines,
        batch_size=batch_size,
        lookback=lookback_n,
        lookahead=lookahead_n,
    )

    logger.debug(
        "Translating %d lines in %d chunks (batch_size=%d, lookback=%d, lookahead=%d)",
        len(lines),
        len(chunks),
        batch_size,
        lookback_n,
        lookahead_n,
    )

    all_translated: list[str] = []
    last_result = None

    for i, chunk in enumerate(chunks):
        # The batch boundary is this job's only honest stopping point. The
        # drain worker checks between queue items, but one item is a whole
        # translation — prod measured those at ~16 minutes against a 900s
        # grace, which is why 43 of 61 abandoned runs in the 30 days to
        # 2026-08-22 were subtitle_automation. Everything above this line is
        # already cached, so stopping here costs the remainder, not the file.
        if abort_requested():
            raise TranslationAbortedError(
                f"asked to stop after {i} of {len(chunks)} batches; "
                "the finished batches are cached and the next attempt resumes from them"
            )
        chunk_result = manager.translate_with_fallback(
            chunk.batch,
            source_lang,
            target_lang,
            fallback_chain,
            glossary_entries,
            # Empty list -> None so LLM prompt assembly skips context sections
            # entirely for the first (no lookback) and last (no lookahead) chunks.
            lookback=chunk.lookback or None,
            lookahead=chunk.lookahead or None,
        )
        if not chunk_result.success:
            raise RuntimeError(f"Translation failed on batch {i + 1}: {chunk_result.error}")
        _verify_batch(chunk_result, len(chunk.batch), "Chunk translation")
        all_translated.extend(chunk_result.translated_lines)
        # Written here, not after the loop: everything above this line is
        # verified and paid for, and the next failure must not take it.
        _cache_batch(cache_enabled, chunk.batch, chunk_result, source_lang, target_lang)
        last_result = chunk_result

    return all_translated, last_result
