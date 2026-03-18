"""Translation quality checking and validation."""

import logging

from translator._helpers import ENGLISH_MARKER_WORDS

logger = logging.getLogger(__name__)


def _evaluate_and_retry_lines(
    source_lines,
    translated_lines,
    source_lang,
    target_lang,
    fallback_chain,
    glossary_entries,
    threshold,
    max_retries,
):
    """Evaluate per-line translation quality and retry low-quality lines.

    For each source/translated pair, calls the LLM evaluator to get a 0-100
    score. Lines scoring below threshold are re-translated (same fallback chain)
    up to max_retries times. The best-scoring translation is kept.

    Args:
        source_lines: Original source subtitle lines
        translated_lines: Initial translations (same length)
        source_lang: ISO 639-1 source language code
        target_lang: ISO 639-1 target language code
        fallback_chain: Backend names in priority order
        glossary_entries: Optional glossary for retries
        threshold: Minimum acceptable score (lines below get retried)
        max_retries: Maximum retry attempts per line

    Returns:
        (final_lines: list[str], scores: list[int])
        final_lines -- best translation for each line
        scores -- per-line quality scores (0-100)
    """
    from translation import get_translation_manager

    manager = get_translation_manager()
    final_lines = list(translated_lines)
    scores = []

    for idx, (src, trans) in enumerate(zip(source_lines, translated_lines)):
        score = manager.evaluate_line_quality(src, trans, source_lang, target_lang, fallback_chain)
        best_trans = trans
        best_score = score

        retry = 0
        while score < threshold and retry < max_retries:
            retry += 1
            logger.info(
                "Quality retry %d/%d for line %d (score=%d < threshold=%d): %r",
                retry,
                max_retries,
                idx,
                score,
                threshold,
                src[:60],
            )
            try:
                result = manager.translate_with_fallback(
                    [src], source_lang, target_lang, fallback_chain, glossary_entries
                )
                if result.success and result.translated_lines:
                    new_trans = result.translated_lines[0]
                    new_score = manager.evaluate_line_quality(
                        src, new_trans, source_lang, target_lang, fallback_chain
                    )
                    if new_score > best_score:
                        best_trans = new_trans
                        best_score = new_score
                    score = new_score
                else:
                    break
            except Exception as exc:
                logger.debug("Quality retry %d failed for line %d: %s", retry, idx, exc)
                break

        final_lines[idx] = best_trans
        scores.append(best_score)

    return final_lines, scores


def _compute_quality_stats(scores, threshold):
    """Compute aggregate quality metrics from per-line scores.

    Args:
        scores: List of per-line quality scores (0-100)
        threshold: Threshold used during evaluation

    Returns:
        Dict with avg_quality, min_quality, low_quality_lines keys.
        Returns empty dict when scores list is empty.
    """
    if not scores:
        return {}
    avg = round(sum(scores) / len(scores), 1)
    low = sum(1 for s in scores if s < threshold)
    return {
        "avg_quality": avg,
        "min_quality": min(scores),
        "low_quality_lines": low,
        "quality_threshold": threshold,
    }


def _write_quality_sidecar(subtitle_path, scores):
    """Write per-line quality scores to a JSON sidecar file.

    The sidecar file is named <subtitle_path>.quality.json and contains
    a JSON array of integer scores in the same order as the subtitle cues.
    Errors are logged but do not interrupt the translation pipeline.

    Args:
        subtitle_path: Absolute path to the translated subtitle file
        scores: Per-line quality scores (0-100) in cue order
    """
    if not scores:
        return
    import json as _json

    sidecar_path = subtitle_path + ".quality.json"
    try:
        with open(sidecar_path, "w", encoding="utf-8") as f:
            _json.dump(scores, f)
        logger.debug("Wrote quality sidecar: %s (%d scores)", sidecar_path, len(scores))
    except Exception as exc:
        logger.warning("Failed to write quality sidecar %s: %s", sidecar_path, exc)


def _check_translation_quality(original_texts, translated_texts):
    """Check translation quality and return warnings.

    Returns list of warning strings (empty if quality seems OK).
    """
    warnings = []

    identical = sum(1 for o, t in zip(original_texts, translated_texts) if o.strip() == t.strip())
    if identical > len(original_texts) * 0.5:
        warnings.append(
            f"{identical}/{len(original_texts)} lines identical to original (possibly untranslated)"
        )

    for i, (orig, trans) in enumerate(zip(original_texts, translated_texts)):
        if len(orig) > 5 and len(trans) > 0:
            ratio = len(trans) / len(orig)
            if ratio > 3.0 or ratio < 0.2:
                warnings.append(f"Line {i}: suspicious length ratio {ratio:.1f}x")
                break  # Only report first occurrence

    # Check for common English words in translation
    if translated_texts:
        sample = " ".join(translated_texts[:20]).lower().split()
        eng_count = sum(1 for w in sample if w in ENGLISH_MARKER_WORDS)
        if len(sample) > 10 and eng_count / len(sample) > 0.3:
            warnings.append(f"High English word ratio in translation ({eng_count}/{len(sample)})")

    return warnings


def validate_translation_output(original_texts, translated_texts, format="ass"):
    """Validate translation output for common issues.

    Returns (is_valid, errors) tuple.
    """
    errors = []
    if len(translated_texts) != len(original_texts):
        errors.append(f"Line count mismatch: {len(original_texts)} vs {len(translated_texts)}")
        return False, errors
    total_orig = sum(len(t) for t in original_texts)
    total_trans = sum(len(t) for t in translated_texts)
    if total_orig > 0 and total_trans > total_orig * 1.5:
        errors.append(f"Output too long: {total_trans / total_orig:.1f}x")
    empty = sum(1 for t in translated_texts if not t.strip())
    if empty > len(translated_texts) * 0.3:
        errors.append(f"Too many empty lines: {empty}/{len(translated_texts)}")
    return len(errors) == 0, errors
