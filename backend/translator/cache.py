"""Translation memory cache functions."""

import logging

logger = logging.getLogger(__name__)


def _apply_translation_cache(lines, source_lang, target_lang, similarity_threshold):
    """Split lines into cache-hit and cache-miss buckets.

    Args:
        lines: All source lines for translation.
        source_lang: ISO 639-1 source language code.
        target_lang: ISO 639-1 target language code.
        similarity_threshold: Forwarded to lookup_translation_cache.

    Returns:
        (cached_results, uncached_indices, uncached_lines) where:
          - cached_results[i] is the cached translation for lines[i], or None
          - uncached_indices is a list of original indices with no cache hit
          - uncached_lines are the corresponding source texts
    """
    from db.translation import lookup_translation_cache

    cached_results = [None] * len(lines)
    uncached_indices = []
    uncached_lines = []

    for idx, line in enumerate(lines):
        try:
            hit = lookup_translation_cache(source_lang, target_lang, line, similarity_threshold)
        except Exception as e:
            logger.debug("Cache lookup error for line %d: %s", idx, e)
            hit = None

        if hit is not None:
            cached_results[idx] = hit
        else:
            uncached_indices.append(idx)
            uncached_lines.append(line)

    return cached_results, uncached_indices, uncached_lines


def _store_translations_in_cache(source_lines, translated_lines, source_lang, target_lang):
    """Persist newly translated lines into the translation memory cache.

    Silently ignores errors so cache failures never break the translation pipeline.
    """
    from db.translation import store_translation_cache

    for src_line, tgt_line in zip(source_lines, translated_lines):
        try:
            store_translation_cache(source_lang, target_lang, src_line, tgt_line)
        except Exception as e:
            logger.debug("Cache store error: %s", e)
