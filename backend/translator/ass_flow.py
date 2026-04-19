"""External-ASS translation flow.

Extracted from translator/core.py. ``_translate_external_ass`` handles
the ``CASE C3`` branch: translate a downloaded provider source ASS file
into the target language. The bulk of the heavy lifting (quality checks,
validation retries, glossary lookup) runs via helpers that live on
``translator.core`` so tests can keep patching them at their canonical
``translator.core.X`` path.

Module-namespace trick:
The helpers are looked up via ``import translator.core as _core`` *inside*
``_translate_external_ass`` so that ``patch("translator.core.X")``
affects the helper resolution at call time. If we imported them at
module top, the binding in ``translator.ass_flow`` would snapshot the
original function and ignore the patch.
"""

import logging
import os
import tempfile

import pysubs2

from ass_utils import classify_styles, extract_tags, fix_line_breaks, restore_tags

logger = logging.getLogger(__name__)


def translate_ass(
    mkv_path,
    stream_info,
    probe_data,
    target_language=None,
    target_language_name=None,
    arr_context=None,
):
    """Translate an ASS subtitle stream to target language .{lang}.ass."""
    # Call-time import so test patches on translator.core.* take effect.
    import translator.core as _core

    output_path = _core.get_output_path_for_lang(mkv_path, "ass", target_language)
    _core.check_disk_space(output_path)

    # Access via package namespace so tests can patch translator.extract_subtitle_stream
    _extract_subtitle_stream = _core._pkg().extract_subtitle_stream

    suffix = ".ass"
    tmp_path = None
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = tmp.name

    try:
        _extract_subtitle_stream(mkv_path, stream_info, tmp_path)

        subs = pysubs2.load(tmp_path)
        logger.info("Loaded %d events, %d styles", len(subs.events), len(subs.styles))

        dialog_styles, signs_styles = classify_styles(subs)

        dialog_indices = []
        dialog_texts = []
        dialog_tags = []
        dialog_orig_lengths = []

        for i, event in enumerate(subs.events):
            if event.is_comment:
                continue
            if event.style not in dialog_styles:
                continue
            if not event.text.strip():
                continue

            clean_text, tag_info, orig_len = extract_tags(event.text)
            if not clean_text.strip():
                continue

            dialog_indices.append(i)
            dialog_texts.append(clean_text)
            dialog_tags.append(tag_info)
            dialog_orig_lengths.append(orig_len)

        logger.info(
            "Dialog lines to translate: %d, Signs/Songs kept: %d",
            len(dialog_texts),
            sum(1 for e in subs.events if not e.is_comment and e.style in signs_styles),
        )

        if not dialog_texts:
            return _core._fail_result("No dialog lines found to translate")

        # HI-removal before translation
        _get_settings = _core._pkg().get_settings
        settings = _get_settings()
        if settings.hi_removal_enabled:
            from hi_remover import remove_hi_from_ass_events

            dialog_texts = remove_hi_from_ass_events(dialog_texts)

        series_id = _core._extract_series_id(arr_context)
        tgt_lang = target_language or settings.target_language
        # Access _translate_with_manager via package namespace for test patching
        _tw_manager = _core._pkg()._translate_with_manager
        translated_texts, translation_result = _tw_manager(
            dialog_texts,
            source_lang=settings.source_language,
            target_lang=tgt_lang,
            arr_context=arr_context,
            series_id=series_id,
        )

        if len(translated_texts) != len(dialog_texts):
            return _core._fail_result(
                f"Translation count mismatch: expected {len(dialog_texts)}, got {len(translated_texts)}"
            )

        # Quality check
        quality_warnings = _core._check_translation_quality(dialog_texts, translated_texts)
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
        for idx, trans_text, tags, orig_len in zip(
            dialog_indices, translated_texts, dialog_tags, dialog_orig_lengths
        ):
            fixed = fix_line_breaks(trans_text)
            restored = restore_tags(fixed, tags, orig_len)
            subs.events[idx].text = restored
            translated_count += 1

        lang_tag = tgt_lang.upper()
        info_title = subs.info.get("Title", "")
        if not info_title.startswith(f"[{lang_tag}]"):
            subs.info["Title"] = f"[{lang_tag}] {info_title}"

        _core.check_disk_space(output_path)
        subs.save(output_path)
        logger.info("Saved ASS translation: %s", output_path)

        # Plan B5 — subtitle repair pass on translated output
        from translator._helpers import run_subtitle_repair

        run_subtitle_repair(output_path)

        _core._write_quality_sidecar(output_path, quality_scores)
        from nfo_export import maybe_write_nfo

        maybe_write_nfo(
            output_path,
            {
                "translation_backend": translation_result.backend_name
                if "translation_result" in dir()
                else "",
                "source_language": getattr(settings, "source_language", ""),
                "target_language": tgt_lang or getattr(settings, "target_language", ""),
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
                "signs_kept": len(signs_styles),
                "dialog_styles": list(dialog_styles),
                "signs_styles": list(signs_styles),
                "format": "ass",
                "source": "embedded_ass",
                "quality_warnings": quality_warnings,
                "backend_name": translation_result.backend_name,
                **_quality_stats,
            },
            "error": None,
        }

    except Exception as e:
        logger.exception("ASS translation failed for %s", mkv_path)
        return _core._fail_result(str(e))
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _translate_external_ass(
    mkv_path, ass_path, target_language=None, target_language_name=None, arr_context=None
):
    """Translate a downloaded external ASS file to target language."""
    # Call-time import so test patches on translator.core.* take effect.
    import translator.core as _core

    output_path = _core.get_output_path_for_lang(mkv_path, "ass", target_language)
    _core.check_disk_space(output_path)

    try:
        subs = pysubs2.load(ass_path)
        logger.info("Loaded external ASS: %d events, %d styles", len(subs.events), len(subs.styles))

        dialog_styles, signs_styles = classify_styles(subs)

        dialog_indices = []
        dialog_texts = []
        dialog_tags = []
        dialog_orig_lengths = []

        for i, event in enumerate(subs.events):
            if event.is_comment:
                continue
            if event.style not in dialog_styles:
                continue
            if not event.text.strip():
                continue

            clean_text, tag_info, orig_len = extract_tags(event.text)
            if not clean_text.strip():
                continue

            dialog_indices.append(i)
            dialog_texts.append(clean_text)
            dialog_tags.append(tag_info)
            dialog_orig_lengths.append(orig_len)

        if not dialog_texts:
            return _core._fail_result("No dialog lines found in external ASS")

        # HI-removal before translation
        _get_settings = _core._pkg().get_settings
        settings = _get_settings()
        if settings.hi_removal_enabled:
            from hi_remover import remove_hi_from_ass_events

            dialog_texts = remove_hi_from_ass_events(dialog_texts)

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
        is_valid, validation_errors = _core.validate_translation_output(
            dialog_texts, translated_texts, format="ass"
        )
        if not is_valid:
            logger.warning("Translation validation failed: %s", validation_errors)
            # Retry logic: max 2 retries
            for retry in range(2):
                logger.info("Retrying translation (attempt %d/2)...", retry + 1)
                translated_texts, translation_result = _tw_manager(
                    dialog_texts,
                    source_lang=settings.source_language,
                    target_lang=tgt_lang,
                    arr_context=arr_context,
                    series_id=series_id,
                )
                is_valid, validation_errors = _core.validate_translation_output(
                    dialog_texts, translated_texts, format="ass"
                )
                if is_valid:
                    break
                logger.warning("Retry %d validation failed: %s", retry + 1, validation_errors)

            if not is_valid:
                logger.error("Translation validation failed after retries: %s", validation_errors)
                # Log for manual review but continue (non-fatal)

        if len(translated_texts) != len(dialog_texts):
            return _core._fail_result(
                f"Translation count mismatch: expected {len(dialog_texts)}, got {len(translated_texts)}"
            )

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
        for idx, trans_text, tags, orig_len in zip(
            dialog_indices, translated_texts, dialog_tags, dialog_orig_lengths
        ):
            fixed = fix_line_breaks(trans_text)
            restored = restore_tags(fixed, tags, orig_len)
            subs.events[idx].text = restored
            translated_count += 1

        lang_tag = tgt_lang.upper()
        info_title = subs.info.get("Title", "")
        if not info_title.startswith(f"[{lang_tag}]"):
            subs.info["Title"] = f"[{lang_tag}] {info_title}"

        _core.check_disk_space(output_path)
        subs.save(output_path)
        logger.info("Saved ASS translation from external source: %s", output_path)

        # Plan B5 — subtitle repair pass on translated output
        from translator._helpers import run_subtitle_repair

        run_subtitle_repair(output_path)

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
                "signs_kept": len(signs_styles),
                "dialog_styles": list(dialog_styles),
                "signs_styles": list(signs_styles),
                "format": "ass",
                "source": "provider_source_ass",
                "quality_warnings": quality_warnings,
                "backend_name": translation_result.backend_name,
                **_quality_stats,
            },
            "error": None,
        }

    except Exception as e:
        logger.exception("External ASS translation failed for %s", mkv_path)
        return _core._fail_result(str(e))
