"""Core translation pipeline: translate_file, translate_ass, translate_srt_*, etc."""

import logging
import os
import sys

# Helpers consumed by the ass_flow/srt_flow sibling modules via
# ``import translator.core as _core``. They MUST stay imported here so that
# (a) ``translator.core.X`` is a valid patch target for tests, and (b) the
# moved flow functions can resolve them through the ``_core.*`` namespace.
from translator._helpers import (  # noqa: F401 — re-exported for patches
    _extract_series_id,
    _fail_result,
    _get_whisper_fallback_min_score,
    _is_whisper_enabled,
    _resolve_backend_for_context,
    _skip_result,
    _submit_whisper_job,
    check_disk_space,
    find_any_source_sub,
    find_external_source_sub,
)
from translator.ass_flow import (  # noqa: F401 — re-exported for patches
    _translate_external_ass,
    translate_ass,
)
from translator.manager import _translate_with_manager  # noqa: F401 — re-exported
from translator.output_paths import (  # noqa: F401 — re-exported for patches
    detect_existing_target_for_lang,
    get_output_path_for_lang,
)
from translator.providers import (
    _search_providers_for_source_sub,
    _search_providers_for_target_ass,
)
from translator.quality import (  # noqa: F401 — re-exported for patches
    _check_translation_quality,
    _compute_quality_stats,
    _evaluate_and_retry_lines,
    _write_quality_sidecar,
    validate_translation_output,
)
from translator.srt_flow import (  # noqa: F401 — re-exported for patches
    _translate_srt,
    translate_srt_from_file,
    translate_srt_from_stream,
)

logger = logging.getLogger(__name__)

# Bounded fallback source languages for provider search when the preferred
# source isn't available. Common subtitle source languages, ordered by how
# often they carry a translatable original. The target language is always
# excluded at the call site.
_FALLBACK_SOURCE_LANGUAGES = ("en", "ja", "zh", "ko", "es", "fr", "de", "pt", "it", "ru")


def _pkg():
    """Return the translator package module (for patchable symbol lookup).

    Functions that tests patch via patch("translator.X") must look up those
    symbols at call time, not at import time, so they see the patched version.
    """
    return sys.modules["translator"]


# translate_ass lives in translator/ass_flow.py — re-imported below so
# translator.core.translate_ass stays a valid patch target for tests.


# translate_srt_from_stream, translate_srt_from_file, _translate_srt live
# in translator/srt_flow.py — re-imported below so their canonical
# translator.core.* patch targets stay valid for tests.


# _translate_external_ass lives in translator/ass_flow.py — re-imported
# below the other helpers so ``translator.core._translate_external_ass``
# stays a valid patch target for tests.


def translate_file(
    mkv_path,
    force=False,
    arr_context=None,
    target_language=None,
    target_language_name=None,
    source_language=None,
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

    from config_language_data import normalize_language_code

    settings = _get_settings()
    tgt_lang = target_language or settings.target_language
    tgt_name = target_language_name or settings.target_language_name
    # Preferred source language (translation direction). Falls back to the
    # configured global source; callers (e.g. wanted_search) may pass the
    # profile's source_language. When the actual available source is in a
    # different language, that real language is used instead of this preference.
    pref_source = source_language or settings.source_language

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
    emb_src = (
        (normalize_language_code(best_stream.get("language") or "") or pref_source)
        if best_stream
        else pref_source
    )
    if best_stream and best_stream["format"] == "ass":
        logger.info("Case C1: Translating source ASS (%s) to target ASS", emb_src)
        result = translate_ass(
            mkv_path,
            best_stream,
            probe_data,
            target_language=tgt_lang,
            target_language_name=tgt_name,
            arr_context=arr_context,
            source_language=emb_src,
        )
        if result["success"]:
            _record_config_hash_for_result(result, mkv_path)
            _notify_integrations(arr_context, file_path=mkv_path)
        return result

    # C2: Source SRT embedded → .{lang}.srt
    if best_stream and best_stream["format"] == "srt":
        logger.info("Case C2: Translating embedded source SRT (%s) to target SRT", emb_src)
        result = translate_srt_from_stream(
            mkv_path,
            best_stream,
            target_language=tgt_lang,
            arr_context=arr_context,
            source_language=emb_src,
        )
        if result["success"]:
            _record_config_hash_for_result(result, mkv_path)
            _notify_integrations(arr_context, file_path=mkv_path)
        return result

    # C2b: External source sidecar (any available language) → translate
    ext_src, ext_lang = find_any_source_sub(
        mkv_path, target_language=tgt_lang, preferred_language=pref_source
    )
    if ext_src:
        if ext_src.lower().endswith(".ass"):
            logger.info("Case C2b: Translating external source ASS (%s) to target ASS", ext_lang)
            result = _translate_external_ass(
                mkv_path,
                ext_src,
                target_language=tgt_lang,
                target_language_name=tgt_name,
                arr_context=arr_context,
                source_language=ext_lang,
            )
        else:
            logger.info("Case C2b: Translating external source SRT (%s) to target SRT", ext_lang)
            result = translate_srt_from_file(
                mkv_path,
                ext_src,
                target_language=tgt_lang,
                arr_context=arr_context,
                source_language=ext_lang,
            )
        if result and result["success"]:
            _record_config_hash_for_result(result, mkv_path)
            _notify_integrations(arr_context, file_path=mkv_path)
        return result

    # C3: Provider search for a source subtitle (any language) → translate.
    # Try the preferred source first, then a bounded fallback set so a provider
    # can supply a source in whatever language it has — never the target.
    src_lang_candidates = [
        lang
        for lang in [pref_source, *_FALLBACK_SOURCE_LANGUAGES]
        if lang and lang != tgt_lang
    ]
    src_path, src_fmt, src_score, src_lang = _search_providers_for_source_sub(
        mkv_path, arr_context, source_languages=src_lang_candidates
    )

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
                "Case C3: Translating provider source ASS (%s) to target ASS (score=%d)",
                src_lang,
                src_score,
            )
            result = _translate_external_ass(
                mkv_path,
                src_path,
                target_language=tgt_lang,
                target_language_name=tgt_name,
                arr_context=arr_context,
                source_language=src_lang,
            )
        else:
            logger.info(
                "Case C3: Translating provider source SRT (%s) to target SRT (score=%d)",
                src_lang,
                src_score,
            )
            result = translate_srt_from_file(
                mkv_path,
                src_path,
                source="provider_source_srt",
                target_language=tgt_lang,
                arr_context=arr_context,
                source_language=src_lang,
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

    return _fail_result("No source subtitle found to translate from")


class Translator:
    """Compatibility shim for routes.wanted.extract auto-translate feature.

    Wraps the module-level translate_file function in an object interface
    so that ``Translator().translate_file(path, target_language=lang)`` works.
    """

    def translate_file(self, mkv_path, target_language=None, **kwargs):
        """Delegate to the module-level translate_file function."""
        return translate_file(mkv_path, target_language=target_language, **kwargs)
