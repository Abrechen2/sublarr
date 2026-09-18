"""Translation quality checking and validation."""

import logging

from services.scheduler.cancellation import abort_requested
from translator._helpers import ENGLISH_MARKER_WORDS
from translator.errors import TranslationAbortedError

logger = logging.getLogger(__name__)


def _memory_enabled():
    """Whether the translation memory is switched on for this install."""
    try:
        from config import get_settings

        return bool(getattr(get_settings(), "translation_memory_enabled", True))
    except Exception:  # noqa: BLE001 — never let a settings read stop a translation
        logger.debug("could not read translation_memory_enabled", exc_info=True)
        return False


def _remembered_scores(source_lang, target_lang, source_lines, translated_lines):
    """Per line: the score this pass already gave *this* text, or None.

    One query for the whole file — the point is to avoid buying a judgement
    twice, which a per-line database round trip would partly give back.

    A stored score counts only when the remembered translation is the one in
    hand. A score describes a translation, not a source line, so a line the
    model rendered differently this time has to be judged on its own.
    """
    if not _memory_enabled() or not source_lines:
        return [None] * len(source_lines)
    try:
        from db.translation import lookup_quality_scores

        remembered = lookup_quality_scores(source_lang, target_lang, list(source_lines))
    except Exception:  # noqa: BLE001 — the memory is an optimisation, never a gate
        logger.debug("translation memory lookup failed; scoring every line", exc_info=True)
        return [None] * len(source_lines)

    return [
        score if (score is not None and text == current) else None
        for (text, score), current in zip(remembered, translated_lines)
    ]


def _remember_score(source_lang, target_lang, source_text, translated_text, score):
    """Persist the pass's verdict on this exact translation."""
    if not _memory_enabled():
        return
    try:
        from db.translation import store_translation_cache

        store_translation_cache(
            source_lang, target_lang, source_text, translated_text, quality_score=score
        )
    except Exception:  # noqa: BLE001 — a memory write must not fail a translation
        logger.debug("could not record the quality score for a line", exc_info=True)


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
    remembered = _remembered_scores(source_lang, target_lang, source_lines, translated_lines)
    reused = 0

    for idx, (src, trans) in enumerate(zip(source_lines, translated_lines)):
        # One LLM round trip per line, plus up to two more per weak line, all
        # sequential — for a 600-line subtitle this loop *is* the tick. Without
        # a check here the scheduler's stop request is only seen once the whole
        # file is done: prod 2026-09-17 took 71 minutes to reach its next check
        # point against a 900 s grace.
        if abort_requested():
            raise TranslationAbortedError(
                f"asked to stop after scoring {idx} of {len(source_lines)} line(s); "
                "the batches themselves were written to the translation memory before "
                "this pass, so a re-run starts from them rather than from nothing"
            )

        if remembered[idx] is not None:
            # This exact translation already went through this pass. Asking the
            # model to judge it a second time buys the same answer.
            final_lines[idx] = trans
            scores.append(remembered[idx])
            reused += 1
            continue

        score = manager.evaluate_line_quality(src, trans, source_lang, target_lang, fallback_chain)
        best_trans = trans
        best_score = score

        retry = 0
        while score < threshold and retry < max_retries:
            if abort_requested():
                raise TranslationAbortedError(
                    f"asked to stop while retrying line {idx}; "
                    "the batches themselves were written to the translation memory before "
                    "this pass, so a re-run starts from them rather than from nothing"
                )
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
            except TranslationAbortedError:
                # A stop request is not a retry failure. Re-raised explicitly
                # so a check added inside this try later cannot be turned into
                # a silent "break" by the handler below.
                raise
            except Exception as exc:
                logger.debug("Quality retry %d failed for line %d: %s", retry, idx, exc)
                break

        final_lines[idx] = best_trans
        scores.append(best_score)
        # The pass has now judged this text. Writing it back is what makes the
        # skip above legitimate: the batch was cached before this pass ran, so
        # without this the memory would keep serving the unchecked line.
        _remember_score(source_lang, target_lang, src, best_trans, best_score)

    if reused:
        logger.info(
            "Quality: reused %d of %d stored verdict(s); %d line(s) scored",
            reused,
            len(source_lines),
            len(source_lines) - reused,
        )

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
