"""Core translation pipeline: translate_file, translate_ass, translate_srt_*, etc."""

import logging
import os
import re
import sys
import tempfile

import pysubs2

from translator._helpers import (
    _extract_series_id,
    _fail_result,
    _get_whisper_fallback_min_score,
    _is_whisper_enabled,
    _resolve_backend_for_context,
    _skip_result,
    _submit_whisper_job,
    check_disk_space,
    find_external_source_sub,
)
from translator.ass_flow import (  # noqa: F401 — re-exported for patches
    _translate_external_ass,
    translate_ass,
)
from translator.manager import _translate_with_manager  # noqa: F401 — re-exported
from translator.output_paths import detect_existing_target_for_lang, get_output_path_for_lang
from translator.providers import (
    _search_providers_for_source_sub,
    _search_providers_for_target_ass,
)
from translator.quality import (
    _check_translation_quality,
    _compute_quality_stats,
    _evaluate_and_retry_lines,
    _write_quality_sidecar,
    validate_translation_output,
)

logger = logging.getLogger(__name__)


def _pkg():
    """Return the translator package module (for patchable symbol lookup).

    Functions that tests patch via patch("translator.X") must look up those
    symbols at call time, not at import time, so they see the patched version.
    """
    return sys.modules["translator"]


# translate_ass lives in translator/ass_flow.py — re-imported below so
# translator.core.translate_ass stays a valid patch target for tests.


def translate_srt_from_stream(mkv_path, stream_info, target_language=None, arr_context=None):
    """Translate an embedded SRT subtitle stream to target language .{lang}.srt."""
    output_path = get_output_path_for_lang(mkv_path, "srt", target_language)
    check_disk_space(output_path)

    _extract_subtitle_stream = _pkg().extract_subtitle_stream

    tmp_path = None
    with tempfile.NamedTemporaryFile(suffix=".srt", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        _extract_subtitle_stream(mkv_path, stream_info, tmp_path)
        return _translate_srt(
            tmp_path,
            output_path,
            source="embedded_srt",
            target_language=target_language,
            arr_context=arr_context,
        )
    except Exception as e:
        logger.exception("SRT stream translation failed for %s", mkv_path)
        return _fail_result(str(e))
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def translate_srt_from_file(
    mkv_path, srt_path, source="external_srt", target_language=None, arr_context=None
):
    """Translate an external SRT file to target language .{lang}.srt."""
    output_path = get_output_path_for_lang(mkv_path, "srt", target_language)
    check_disk_space(output_path)

    try:
        return _translate_srt(srt_path, output_path, source=source, arr_context=arr_context)
    except Exception as e:
        logger.exception("SRT file translation failed for %s", mkv_path)
        return _fail_result(str(e))


def _translate_srt(srt_path, output_path, source="srt", target_language=None, arr_context=None):
    """Internal: translate an SRT file.

    SRT is simpler than ASS: no styles to classify, no override tags.
    """
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
        return _fail_result("No dialog lines found in SRT")

    _get_settings = _pkg().get_settings
    settings = _get_settings()

    # HI-removal before translation
    if settings.hi_removal_enabled:
        from hi_remover import remove_hi_markers

        dialog_texts = [remove_hi_markers(t) for t in dialog_texts]

    logger.info("SRT lines to translate: %d", len(dialog_texts))
    # Extract series_id for glossary
    series_id = _extract_series_id(arr_context)
    tgt_lang = target_language or settings.target_language
    _tw_manager = _pkg()._translate_with_manager
    translated_texts, translation_result = _tw_manager(
        dialog_texts,
        source_lang=settings.source_language,
        target_lang=tgt_lang,
        arr_context=arr_context,
        series_id=series_id,
    )

    # Validate translation output
    validation_errors = []
    is_valid, validation_errors = validate_translation_output(
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
            is_valid, validation_errors = validate_translation_output(
                dialog_texts, translated_texts, format="srt"
            )
            if is_valid:
                break
            logger.warning("SRT retry %d validation failed: %s", retry + 1, validation_errors)

    if len(translated_texts) != len(dialog_texts):
        return _fail_result(
            f"Translation count mismatch: expected {len(dialog_texts)}, got {len(translated_texts)}"
        )

    # Quality check
    quality_warnings = _check_translation_quality(dialog_texts, translated_texts)
    if validation_errors:
        quality_warnings.extend([f"Validation: {e}" for e in validation_errors])
    for w in quality_warnings:
        logger.warning("Quality: %s", w)

    # LLM quality evaluation + per-line retry for low-quality lines
    quality_scores = []
    _q_cfg = _pkg()._get_quality_config
    _q_enabled, _q_threshold, _q_max_retries = _q_cfg()
    if _q_enabled:
        _, _q_fallback_chain = _resolve_backend_for_context(arr_context, tgt_lang)
        translated_texts, quality_scores = _evaluate_and_retry_lines(
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

    check_disk_space(output_path)
    subs.save(output_path, format_="srt")
    logger.info("Saved SRT translation: %s", output_path)

    _write_quality_sidecar(output_path, quality_scores)
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
    _quality_stats = _compute_quality_stats(quality_scores, _q_threshold) if quality_scores else {}

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


# _translate_external_ass lives in translator/ass_flow.py — re-imported
# below the other helpers so ``translator.core._translate_external_ass``
# stays a valid patch target for tests.


def translate_file(
    mkv_path, force=False, arr_context=None, target_language=None, target_language_name=None
):
    """Translate subtitles for a single MKV file.

    Four-case priority chain (target language ASS is always the goal):

    CASE A: Target ASS exists → Skip (goal achieved)
    CASE B: Target SRT exists → Upgrade attempt:
        B1: Provider search for target ASS
        B2: Source ASS embedded → translate to .{lang}.ass
        B3: No upgrade possible → keep SRT
    CASE C: No target subtitle:
        C1: Source ASS embedded → .{lang}.ass
        C2: Source SRT (embedded/external) → .{lang}.srt
        C3: Provider search for source subtitle → translate
        C4: Nothing → Fall through to Case D
    CASE D: Whisper transcription (if enabled):
        D1: Submit audio transcription to Whisper queue → returns whisper_pending

    After successful translation: notify integrations if context provided.

    Args:
        target_language: Override target language (e.g. "de"). Defaults to config.
        target_language_name: Override target language name (e.g. "German"). Defaults to config.
    """
    from translator.jobs import _notify_integrations, _record_config_hash_for_result

    # Access via package namespace so tests can patch translator.get_settings etc.
    _get_settings = _pkg().get_settings
    _get_media_streams = _pkg().get_media_streams
    _select_best_subtitle_stream = _pkg().select_best_subtitle_stream

    settings = _get_settings()
    tgt_lang = target_language or settings.target_language
    tgt_name = target_language_name or settings.target_language_name

    if not os.path.exists(mkv_path):
        raise FileNotFoundError(f"File not found: {mkv_path}")

    logger.info("Processing: %s (target: %s)", mkv_path, tgt_lang)
    probe_data = _get_media_streams(mkv_path)

    if not force:
        target_status = detect_existing_target_for_lang(mkv_path, tgt_lang, probe_data)
    else:
        target_status = None

    result = None

    # === CASE A: Target ASS exists → Done ===
    if target_status == "ass":
        logger.info("Case A: Target ASS already exists, skipping")
        return _skip_result(f"{tgt_name} ASS already exists")

    # === CASE B: Target SRT exists → Upgrade attempt to ASS ===
    if target_status == "srt":
        logger.info("Case B: Target SRT found, attempting upgrade to ASS")

        # B1: Provider search for target ASS
        target_ass_path = _search_providers_for_target_ass(
            mkv_path, arr_context, target_language=tgt_lang
        )
        if target_ass_path:
            logger.info("Case B1: Provider found target ASS (upgrade from SRT)")
            return _skip_result(
                f"{tgt_name} ASS downloaded via provider (upgraded from SRT)",
                output_path=target_ass_path,
            )

        # B2: Source ASS embedded → translate to .{lang}.ass
        best_ass = _select_best_subtitle_stream(probe_data, format_filter="ass")
        if best_ass:
            logger.info("Case B2: Upgrading — translating source ASS to target ASS")
            result = translate_ass(
                mkv_path,
                best_ass,
                probe_data,
                target_language=tgt_lang,
                target_language_name=tgt_name,
                arr_context=arr_context,
            )
            if result["success"]:
                result["stats"]["upgrade_from_srt"] = True
                _record_config_hash_for_result(result, mkv_path)
                _notify_integrations(arr_context, file_path=mkv_path)
                return result

        # B3: No upgrade possible
        logger.info("Case B3: No ASS upgrade available, keeping target SRT")
        return _skip_result(f"{tgt_name} SRT exists, no ASS upgrade available")

    # === CASE C: No target subtitle → Full pipeline ===

    # C1: Source ASS embedded → .{lang}.ass
    best_stream = _select_best_subtitle_stream(probe_data)
    if best_stream and best_stream["format"] == "ass":
        logger.info("Case C1: Translating source ASS to target ASS")
        result = translate_ass(
            mkv_path,
            best_stream,
            probe_data,
            target_language=tgt_lang,
            target_language_name=tgt_name,
            arr_context=arr_context,
        )
        if result["success"]:
            _record_config_hash_for_result(result, mkv_path)
            _notify_integrations(arr_context, file_path=mkv_path)
        return result

    # C2: Source SRT embedded → .{lang}.srt
    if best_stream and best_stream["format"] == "srt":
        logger.info("Case C2: Translating embedded source SRT to target SRT")
        result = translate_srt_from_stream(
            mkv_path, best_stream, target_language=tgt_lang, arr_context=arr_context
        )
        if result["success"]:
            _record_config_hash_for_result(result, mkv_path)
            _notify_integrations(arr_context, file_path=mkv_path)
        return result

    # C2b: External source SRT → .{lang}.srt
    ext_srt = find_external_source_sub(mkv_path)
    if ext_srt:
        logger.info("Case C2b: Translating external source SRT to target SRT")
        result = translate_srt_from_file(
            mkv_path, ext_srt, target_language=tgt_lang, arr_context=arr_context
        )
        if result["success"]:
            _record_config_hash_for_result(result, mkv_path)
            _notify_integrations(arr_context, file_path=mkv_path)
        return result

    # C3: Provider search for source subtitle → translate
    src_path, src_fmt, src_score = _search_providers_for_source_sub(mkv_path, arr_context)

    # C3 Whisper-fallback threshold check:
    _min_score = _get_whisper_fallback_min_score()
    _below_threshold = src_path is not None and _min_score > 0 and src_score < _min_score
    if _below_threshold:
        logger.info(
            "Case C3: Provider source score %d < threshold %d for %s -- skipping, will try Whisper fallback",
            src_score,
            _min_score,
            mkv_path,
        )
        src_path = None  # discard below-threshold result; fall through to Case D

    if src_path:
        if src_fmt == "ass":
            logger.info(
                "Case C3: Translating provider source ASS to target ASS (score=%d)", src_score
            )
            result = _translate_external_ass(
                mkv_path,
                src_path,
                target_language=tgt_lang,
                target_language_name=tgt_name,
                arr_context=arr_context,
            )
        else:
            logger.info(
                "Case C3: Translating provider source SRT to target SRT (score=%d)", src_score
            )
            result = translate_srt_from_file(
                mkv_path,
                src_path,
                source="provider_source_srt",
                target_language=tgt_lang,
                arr_context=arr_context,
            )
        if result and result["success"]:
            _record_config_hash_for_result(result, mkv_path)
            _notify_integrations(arr_context, file_path=mkv_path)
        return result

    # C4: Nothing found from providers/embedded
    logger.warning("Case C4: No source subtitle found for %s", mkv_path)

    # === CASE D: Whisper transcription as last resort or score-based fallback ===
    if _is_whisper_enabled():
        if _below_threshold:
            logger.info(
                "Case D: Provider score %d below threshold %d, using Whisper fallback for %s",
                src_score,
                _min_score,
                mkv_path,
            )
        else:
            logger.info(
                "Case D: No subtitle source found, attempting Whisper transcription for %s",
                mkv_path,
            )
        whisper_result = _submit_whisper_job(mkv_path, arr_context)
        if whisper_result:
            return whisper_result
        logger.warning(
            "Case D: Whisper transcription not available or failed to submit for %s", mkv_path
        )

    return _fail_result(f"No {settings.source_language_name} subtitle source found")


class Translator:
    """Compatibility shim for routes.wanted.extract auto-translate feature.

    Wraps the module-level translate_file function in an object interface
    so that ``Translator().translate_file(path, target_language=lang)`` works.
    """

    def translate_file(self, mkv_path, target_language=None, **kwargs):
        """Delegate to the module-level translate_file function."""
        return translate_file(mkv_path, target_language=target_language, **kwargs)
