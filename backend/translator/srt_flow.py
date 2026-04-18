"""SRT translation flow.

Extracted from translator/core.py. Owns the three SRT entry points —
``translate_srt_from_stream`` (embedded SRT in an MKV), ``translate_srt_from_file``
(external .srt already on disk), and the shared ``_translate_srt`` core
that does the heavy lifting (HI removal, translation-with-retries,
quality evaluation, output writing).

Same call-time module-lookup pattern as ``translator/ass_flow.py``:
``import translator.core as _core`` inside each function body so
``patch("translator.core.X")`` still affects the helpers at call time
instead of being snapshotted into this module's namespace at import.
"""

import logging
import os
import re
import tempfile

import pysubs2

logger = logging.getLogger(__name__)


def translate_srt_from_stream(mkv_path, stream_info, target_language=None, arr_context=None):
    """Translate an embedded SRT subtitle stream to target language .{lang}.srt."""
    import translator.core as _core

    output_path = _core.get_output_path_for_lang(mkv_path, "srt", target_language)
    _core.check_disk_space(output_path)

    _extract_subtitle_stream = _core._pkg().extract_subtitle_stream

    tmp_path = None
    with tempfile.NamedTemporaryFile(suffix=".srt", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        _extract_subtitle_stream(mkv_path, stream_info, tmp_path)
        return _core._translate_srt(
            tmp_path,
            output_path,
            source="embedded_srt",
            target_language=target_language,
            arr_context=arr_context,
        )
    except Exception as e:
        logger.exception("SRT stream translation failed for %s", mkv_path)
        return _core._fail_result(str(e))
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def translate_srt_from_file(
    mkv_path, srt_path, source="external_srt", target_language=None, arr_context=None
):
    """Translate an external SRT file to target language .{lang}.srt."""
    import translator.core as _core

    output_path = _core.get_output_path_for_lang(mkv_path, "srt", target_language)
    _core.check_disk_space(output_path)

    try:
        return _core._translate_srt(srt_path, output_path, source=source, arr_context=arr_context)
    except Exception as e:
        logger.exception("SRT file translation failed for %s", mkv_path)
        return _core._fail_result(str(e))


def _translate_srt(srt_path, output_path, source="srt", target_language=None, arr_context=None):
    """Internal: translate an SRT file.

    SRT is simpler than ASS: no styles to classify, no override tags.
    """
    import translator.core as _core

    subs = pysubs2.load(srt_path)
    logger.info("Loaded SRT with %d events", len(subs.events))

    dialog_indices = []
    dialog_texts = []

    for i, event in enumerate(subs.events):
        if event.is_comment:
            continue
        text = event.text.strip()
        if not text:
            continue
        # SRT may have HTML-like tags (<i>, <b>) — strip for translation
        clean = re.sub(r"<[^>]+>", "", text)
        if not clean.strip():
            continue
        dialog_indices.append(i)
        dialog_texts.append(clean)

    if not dialog_texts:
        return _core._fail_result("No dialog lines found in SRT")

    _get_settings = _core._pkg().get_settings
    settings = _get_settings()

    # HI-removal before translation
    if settings.hi_removal_enabled:
        from hi_remover import remove_hi_markers

        dialog_texts = [remove_hi_markers(t) for t in dialog_texts]

    logger.info("SRT lines to translate: %d", len(dialog_texts))
    # Extract series_id for glossary
    series_id = _core._extract_series_id(arr_context)
    tgt_lang = target_language or settings.target_language
    _tw_manager = _core._pkg()._translate_with_manager
    translated_texts, translation_result = _tw_manager(
        dialog_texts,
        source_lang=settings.source_language,
        target_lang=tgt_lang,
        arr_context=arr_context,
        series_id=series_id,
    )

    # Validate translation output
    validation_errors = []
    is_valid, validation_errors = _core.validate_translation_output(
        dialog_texts, translated_texts, format="srt"
    )
    if not is_valid:
        logger.warning("SRT translation validation failed: %s", validation_errors)
        # Retry logic: max 2 retries
        for retry in range(2):
            logger.info("Retrying SRT translation (attempt %d/2)...", retry + 1)
            translated_texts, translation_result = _tw_manager(
                dialog_texts,
                source_lang=settings.source_language,
                target_lang=tgt_lang,
                arr_context=arr_context,
                series_id=series_id,
            )
            is_valid, validation_errors = _core.validate_translation_output(
                dialog_texts, translated_texts, format="srt"
            )
            if is_valid:
                break
            logger.warning("SRT retry %d validation failed: %s", retry + 1, validation_errors)

    if len(translated_texts) != len(dialog_texts):
        return _core._fail_result(
            f"Translation count mismatch: expected {len(dialog_texts)}, got {len(translated_texts)}"
        )

    # Quality check
    quality_warnings = _core._check_translation_quality(dialog_texts, translated_texts)
    if validation_errors:
        quality_warnings.extend([f"Validation: {e}" for e in validation_errors])
    for w in quality_warnings:
        logger.warning("Quality: %s", w)

    # LLM quality evaluation + per-line retry for low-quality lines
    quality_scores = []
    _q_cfg = _core._pkg()._get_quality_config
    _q_enabled, _q_threshold, _q_max_retries = _q_cfg()
    if _q_enabled:
        _, _q_fallback_chain = _core._resolve_backend_for_context(arr_context, tgt_lang)
        translated_texts, quality_scores = _core._evaluate_and_retry_lines(
            dialog_texts,
            translated_texts,
            settings.source_language,
            tgt_lang,
            _q_fallback_chain,
            None,
            _q_threshold,
            _q_max_retries,
        )

    translated_count = 0
    for idx, trans_text in zip(dialog_indices, translated_texts):
        subs.events[idx].text = trans_text.strip()
        translated_count += 1

    _core.check_disk_space(output_path)
    subs.save(output_path, format_="srt")
    logger.info("Saved SRT translation: %s", output_path)

    _core._write_quality_sidecar(output_path, quality_scores)
    from nfo_export import maybe_write_nfo

    maybe_write_nfo(
        output_path,
        {
            "translation_backend": translation_result.backend_name
            if "translation_result" in dir()
            else "",
            "source_language": settings.source_language,
            "target_language": target_language or settings.target_language,
        },
    )
    _quality_stats = (
        _core._compute_quality_stats(quality_scores, _q_threshold) if quality_scores else {}
    )

    return {
        "success": True,
        "output_path": output_path,
        "stats": {
            "total_events": len(subs.events),
            "translated": translated_count,
            "format": "srt",
            "source": source,
            "quality_warnings": quality_warnings,
            "backend_name": translation_result.backend_name,
            **_quality_stats,
        },
        "error": None,
    }
