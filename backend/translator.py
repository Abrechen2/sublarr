"""Core translation orchestration: extract, translate, reassemble subtitles.

Supports ASS (primary) and SRT (fallback) subtitle formats.
Target language ASS is always the goal — SRT output only when no ASS source exists.
All language-specific logic is parameterized via config.py.
"""

import os
import re
import shutil
import tempfile
import logging

import pysubs2

from config import get_settings
from ass_utils import (
    run_ffprobe,
    has_target_language_stream,
    select_best_subtitle_stream,
    extract_subtitle_stream,
    classify_styles,
    extract_tags,
    restore_tags,
    fix_line_breaks,
)
from ollama_client import translate_all

logger = logging.getLogger(__name__)

MIN_FREE_SPACE_MB = 100

# Common English words that indicate a subtitle was not actually translated
ENGLISH_MARKER_WORDS = {
    "the", "and", "that", "have", "for", "not", "with", "you",
    "this", "but", "from", "they", "will", "what", "about",
}


def get_output_path(mkv_path, fmt="ass"):
    """Get the output path for a translated subtitle file."""
    settings = get_settings()
    base = os.path.splitext(mkv_path)[0]
    return f"{base}.{settings.target_language}.{fmt}"


def detect_existing_target(mkv_path, probe_data=None):
    """Detect existing target language subtitles (external files and embedded streams).

    Returns:
        str or None: "ass" if target ASS found, "srt" if only target SRT found,
        None if no target language subtitle exists. ASS takes priority over SRT.
    """
    settings = get_settings()
    base = os.path.splitext(mkv_path)[0]

    # Check external files — ASS first (higher priority)
    for pattern in settings.get_target_patterns("ass"):
        if os.path.exists(base + pattern):
            return "ass"

    has_srt = False
    for pattern in settings.get_target_patterns("srt"):
        if os.path.exists(base + pattern):
            has_srt = True
            break

    # Check embedded streams
    if probe_data:
        embedded = has_target_language_stream(probe_data)
        if embedded == "ass":
            return "ass"
        if embedded == "srt":
            has_srt = True

    return "srt" if has_srt else None


def find_external_source_sub(mkv_path):
    """Find an external source language subtitle file next to the MKV."""
    settings = get_settings()
    base = os.path.splitext(mkv_path)[0]

    # Check both ASS and SRT patterns for the source language
    all_patterns = settings.get_source_patterns("srt") + settings.get_source_patterns("ass")
    for pattern in all_patterns:
        path = base + pattern
        if os.path.exists(path):
            logger.info("Found external source subtitle: %s", path)
            return path
    return None


def check_disk_space(path):
    """Check if there's enough free disk space."""
    stat = shutil.disk_usage(os.path.dirname(path))
    free_mb = stat.free / (1024 * 1024)
    if free_mb < MIN_FREE_SPACE_MB:
        raise RuntimeError(
            f"Insufficient disk space: {free_mb:.0f}MB free, "
            f"need at least {MIN_FREE_SPACE_MB}MB"
        )


def _skip_result(reason, output_path=None):
    """Create a skip result dict."""
    return {
        "success": True,
        "output_path": output_path,
        "stats": {"skipped": True, "reason": reason},
        "error": None,
    }


def _fail_result(error):
    """Create a failure result dict."""
    return {
        "success": False,
        "output_path": None,
        "stats": {},
        "error": error,
    }


def _check_translation_quality(original_texts, translated_texts):
    """Check translation quality and return warnings.

    Returns list of warning strings (empty if quality seems OK).
    """
    warnings = []

    identical = sum(1 for o, t in zip(original_texts, translated_texts) if o.strip() == t.strip())
    if identical > len(original_texts) * 0.5:
        warnings.append(f"{identical}/{len(original_texts)} lines identical to original (possibly untranslated)")

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


def translate_ass(mkv_path, stream_info, probe_data):
    """Translate an ASS subtitle stream to target language .{lang}.ass."""
    output_path = get_output_path(mkv_path, "ass")
    check_disk_space(output_path)

    suffix = ".ass"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = tmp.name

    try:
        extract_subtitle_stream(mkv_path, stream_info, tmp_path)

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
            return _fail_result("No dialog lines found to translate")

        translated_texts = translate_all(dialog_texts)

        if len(translated_texts) != len(dialog_texts):
            return _fail_result(
                f"Translation count mismatch: expected {len(dialog_texts)}, got {len(translated_texts)}"
            )

        # Quality check
        quality_warnings = _check_translation_quality(dialog_texts, translated_texts)
        for w in quality_warnings:
            logger.warning("Quality: %s", w)

        translated_count = 0
        for idx, trans_text, tags, orig_len in zip(
            dialog_indices, translated_texts, dialog_tags, dialog_orig_lengths
        ):
            fixed = fix_line_breaks(trans_text)
            restored = restore_tags(fixed, tags, orig_len)
            subs.events[idx].text = restored
            translated_count += 1

        settings = get_settings()
        lang_tag = settings.target_language.upper()
        info_title = subs.info.get("Title", "")
        if not info_title.startswith(f"[{lang_tag}]"):
            subs.info["Title"] = f"[{lang_tag}] {info_title}"

        check_disk_space(output_path)
        subs.save(output_path)
        logger.info("Saved ASS translation: %s", output_path)

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
            },
            "error": None,
        }

    except Exception as e:
        logger.exception("ASS translation failed for %s", mkv_path)
        return _fail_result(str(e))
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def translate_srt_from_stream(mkv_path, stream_info):
    """Translate an embedded SRT subtitle stream to target language .{lang}.srt."""
    output_path = get_output_path(mkv_path, "srt")
    check_disk_space(output_path)

    with tempfile.NamedTemporaryFile(suffix=".srt", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        extract_subtitle_stream(mkv_path, stream_info, tmp_path)
        return _translate_srt(tmp_path, output_path, source="embedded_srt")
    except Exception as e:
        logger.exception("SRT stream translation failed for %s", mkv_path)
        return _fail_result(str(e))
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def translate_srt_from_file(mkv_path, srt_path, source="external_srt"):
    """Translate an external SRT file to target language .{lang}.srt."""
    output_path = get_output_path(mkv_path, "srt")
    check_disk_space(output_path)

    try:
        return _translate_srt(srt_path, output_path, source=source)
    except Exception as e:
        logger.exception("SRT file translation failed for %s", mkv_path)
        return _fail_result(str(e))


def _translate_srt(srt_path, output_path, source="srt"):
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

    logger.info("SRT lines to translate: %d", len(dialog_texts))
    translated_texts = translate_all(dialog_texts)

    if len(translated_texts) != len(dialog_texts):
        return _fail_result(
            f"Translation count mismatch: expected {len(dialog_texts)}, got {len(translated_texts)}"
        )

    # Quality check
    quality_warnings = _check_translation_quality(dialog_texts, translated_texts)
    for w in quality_warnings:
        logger.warning("Quality: %s", w)

    translated_count = 0
    for idx, trans_text in zip(dialog_indices, translated_texts):
        subs.events[idx].text = trans_text.strip()
        translated_count += 1

    check_disk_space(output_path)
    subs.save(output_path, format_="srt")
    logger.info("Saved SRT translation: %s", output_path)

    return {
        "success": True,
        "output_path": output_path,
        "stats": {
            "total_events": len(subs.events),
            "translated": translated_count,
            "format": "srt",
            "source": source,
            "quality_warnings": quality_warnings,
        },
        "error": None,
    }


def _build_video_query(mkv_path, context=None):
    """Build a VideoQuery from file path and optional context."""
    from providers.base import VideoQuery

    settings = get_settings()
    query = VideoQuery(
        file_path=mkv_path,
        languages=[settings.source_language],
    )

    if context:
        query.series_title = context.get("series_title", "")
        query.title = context.get("title", "")
        if context.get("season") is not None:
            query.season = context["season"]
        if context.get("episode") is not None:
            query.episode = context["episode"]
        query.imdb_id = context.get("imdb_id", "")
        query.anidb_id = context.get("anidb_id")
        query.anilist_id = context.get("anilist_id")
        query.tvdb_id = context.get("tvdb_id")
        query.sonarr_series_id = context.get("sonarr_series_id")
        query.sonarr_episode_id = context.get("sonarr_episode_id")

    return query


def _search_providers_for_target_ass(mkv_path, context=None):
    """Search subtitle providers for a target language ASS file.

    Returns:
        str or None: path to downloaded ASS file, or None
    """
    try:
        from providers import get_provider_manager
        from providers.base import VideoQuery, SubtitleFormat

        settings = get_settings()
        manager = get_provider_manager()

        query = _build_video_query(mkv_path, context)
        query.languages = [settings.target_language]

        result = manager.search_and_download_best(
            query, format_filter=SubtitleFormat.ASS
        )
        if result and result.content:
            output_path = get_output_path(mkv_path, "ass")
            manager.save_subtitle(result, output_path)
            logger.info("Provider %s delivered target ASS: %s", result.provider_name, output_path)
            return output_path
    except Exception as e:
        logger.warning("Provider search for target ASS failed: %s", e)

    return None


def _search_providers_for_source_sub(mkv_path, context=None):
    """Search subtitle providers for a source language subtitle.

    Tries ASS first, falls back to SRT.

    Returns:
        tuple: (path, format) or (None, None)
    """
    try:
        from providers import get_provider_manager
        from providers.base import VideoQuery, SubtitleFormat

        settings = get_settings()
        manager = get_provider_manager()

        query = _build_video_query(mkv_path, context)
        query.languages = [settings.source_language]

        # Try ASS first
        result = manager.search_and_download_best(
            query, format_filter=SubtitleFormat.ASS
        )
        if result and result.content:
            base = os.path.splitext(mkv_path)[0]
            tmp_path = f"{base}.{settings.source_language}.ass"
            manager.save_subtitle(result, tmp_path)
            logger.info("Provider %s delivered source ASS: %s", result.provider_name, tmp_path)
            return tmp_path, "ass"

        # Fall back to any format (SRT most likely)
        result = manager.search_and_download_best(query)
        if result and result.content:
            base = os.path.splitext(mkv_path)[0]
            ext = result.format.value if result.format.value != "unknown" else "srt"
            tmp_path = f"{base}.{settings.source_language}.{ext}"
            manager.save_subtitle(result, tmp_path)
            logger.info("Provider %s delivered source %s: %s", result.provider_name, ext, tmp_path)
            return tmp_path, ext
    except Exception as e:
        logger.warning("Provider search for source subtitle failed: %s", e)

    return None, None


def _record_config_hash_for_result(result, file_path):
    """Record the translation config hash for a successful translation job."""
    if not result or not result.get("success") or result.get("stats", {}).get("skipped"):
        return
    try:
        settings = get_settings()
        config_hash = settings.get_translation_config_hash()
        from database import record_translation_config
        record_translation_config(
            config_hash=config_hash,
            ollama_model=settings.ollama_model,
            prompt_template=settings.get_prompt_template()[:200],
            target_language=settings.target_language,
        )
        # Store hash in result stats for job record
        result.setdefault("stats", {})["config_hash"] = config_hash
    except Exception as e:
        logger.debug("Failed to record config hash: %s", e)


def translate_file(mkv_path, force=False, bazarr_context=None):
    """Translate subtitles for a single MKV file.

    Three-case priority chain (target language ASS is always the goal):

    CASE A: Target ASS exists → Skip (goal achieved)
    CASE B: Target SRT exists → Upgrade attempt:
        B1: Provider search for target ASS
        B2: Source ASS embedded → translate to .{lang}.ass
        B3: No upgrade possible → keep SRT
    CASE C: No target subtitle:
        C1: Source ASS embedded → .{lang}.ass
        C2: Source SRT (embedded/external) → .{lang}.srt
        C3: Provider search for source subtitle → translate
        C4: Nothing → Fail

    After successful translation: notify integrations if context provided.
    """
    settings = get_settings()

    if not os.path.exists(mkv_path):
        raise FileNotFoundError(f"File not found: {mkv_path}")

    logger.info("Processing: %s", mkv_path)
    probe_data = run_ffprobe(mkv_path)

    if not force:
        target_status = detect_existing_target(mkv_path, probe_data)
    else:
        target_status = None

    result = None

    # === CASE A: Target ASS exists → Done ===
    if target_status == "ass":
        logger.info("Case A: Target ASS already exists, skipping")
        return _skip_result(f"{settings.target_language_name} ASS already exists")

    # === CASE B: Target SRT exists → Upgrade attempt to ASS ===
    if target_status == "srt":
        logger.info("Case B: Target SRT found, attempting upgrade to ASS")

        # B1: Provider search for target ASS
        target_ass_path = _search_providers_for_target_ass(mkv_path, bazarr_context)
        if target_ass_path:
            logger.info("Case B1: Provider found target ASS (upgrade from SRT)")
            return _skip_result(
                f"{settings.target_language_name} ASS downloaded via provider (upgraded from SRT)",
                output_path=target_ass_path,
            )

        # B2: Source ASS embedded → translate to .{lang}.ass
        best_ass = select_best_subtitle_stream(probe_data, format_filter="ass")
        if best_ass:
            logger.info("Case B2: Upgrading — translating source ASS to target ASS")
            result = translate_ass(mkv_path, best_ass, probe_data)
            if result["success"]:
                result["stats"]["upgrade_from_srt"] = True
                _record_config_hash_for_result(result, mkv_path)
                _notify_integrations(bazarr_context)
                return result

        # B3: No upgrade possible
        logger.info("Case B3: No ASS upgrade available, keeping target SRT")
        return _skip_result(f"{settings.target_language_name} SRT exists, no ASS upgrade available")

    # === CASE C: No target subtitle → Full pipeline ===

    # C1: Source ASS embedded → .{lang}.ass
    best_stream = select_best_subtitle_stream(probe_data)
    if best_stream and best_stream["format"] == "ass":
        logger.info("Case C1: Translating source ASS to target ASS")
        result = translate_ass(mkv_path, best_stream, probe_data)
        if result["success"]:
            _record_config_hash_for_result(result, mkv_path)
            _notify_integrations(bazarr_context)
        return result

    # C2: Source SRT embedded → .{lang}.srt
    if best_stream and best_stream["format"] == "srt":
        logger.info("Case C2: Translating embedded source SRT to target SRT")
        result = translate_srt_from_stream(mkv_path, best_stream)
        if result["success"]:
            _record_config_hash_for_result(result, mkv_path)
            _notify_integrations(bazarr_context)
        return result

    # C2b: External source SRT → .{lang}.srt
    ext_srt = find_external_source_sub(mkv_path)
    if ext_srt:
        logger.info("Case C2b: Translating external source SRT to target SRT")
        result = translate_srt_from_file(mkv_path, ext_srt)
        if result["success"]:
            _record_config_hash_for_result(result, mkv_path)
            _notify_integrations(bazarr_context)
        return result

    # C3: Provider search for source subtitle → translate
    src_path, src_fmt = _search_providers_for_source_sub(mkv_path, bazarr_context)
    if src_path:
        if src_fmt == "ass":
            logger.info("Case C3: Translating provider source ASS to target ASS")
            result = _translate_external_ass(mkv_path, src_path)
        else:
            logger.info("Case C3: Translating provider source SRT to target SRT")
            result = translate_srt_from_file(mkv_path, src_path, source="provider_source_srt")
        if result and result["success"]:
            _record_config_hash_for_result(result, mkv_path)
            _notify_integrations(bazarr_context)
        return result

    # C3b: Bazarr legacy fallback (if still configured)
    if bazarr_context:
        try:
            from bazarr_client import get_bazarr_client
            bazarr = get_bazarr_client()
            if bazarr:
                logger.info("Case C3b: Trying Bazarr legacy fallback for source SRT")
                src_srt_path = bazarr.fetch_source_srt(
                    bazarr_context.get("sonarr_series_id"),
                    bazarr_context.get("sonarr_episode_id"),
                )
                if src_srt_path:
                    result = translate_srt_from_file(
                        mkv_path, src_srt_path, source="bazarr_source_srt"
                    )
                    if result["success"]:
                        _record_config_hash_for_result(result, mkv_path)
                        _notify_integrations(bazarr_context)
                    return result
        except Exception as e:
            logger.warning("Bazarr fallback failed: %s", e)

    # C4: Nothing found
    logger.warning("Case C4: No source subtitle found for %s", mkv_path)
    return _fail_result(f"No {settings.source_language_name} subtitle source found")


def _translate_external_ass(mkv_path, ass_path):
    """Translate a downloaded external ASS file to target language."""
    output_path = get_output_path(mkv_path, "ass")
    check_disk_space(output_path)

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
            return _fail_result("No dialog lines found in external ASS")

        translated_texts = translate_all(dialog_texts)

        if len(translated_texts) != len(dialog_texts):
            return _fail_result(
                f"Translation count mismatch: expected {len(dialog_texts)}, got {len(translated_texts)}"
            )

        quality_warnings = _check_translation_quality(dialog_texts, translated_texts)
        for w in quality_warnings:
            logger.warning("Quality: %s", w)

        translated_count = 0
        for idx, trans_text, tags, orig_len in zip(
            dialog_indices, translated_texts, dialog_tags, dialog_orig_lengths
        ):
            fixed = fix_line_breaks(trans_text)
            restored = restore_tags(fixed, tags, orig_len)
            subs.events[idx].text = restored
            translated_count += 1

        settings = get_settings()
        lang_tag = settings.target_language.upper()
        info_title = subs.info.get("Title", "")
        if not info_title.startswith(f"[{lang_tag}]"):
            subs.info["Title"] = f"[{lang_tag}] {info_title}"

        check_disk_space(output_path)
        subs.save(output_path)
        logger.info("Saved ASS translation from external source: %s", output_path)

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
            },
            "error": None,
        }

    except Exception as e:
        logger.exception("External ASS translation failed for %s", mkv_path)
        return _fail_result(str(e))


def _notify_integrations(context):
    """Notify external services about new subtitle files."""
    if not context:
        return

    # Bazarr scan-disk (legacy, if still configured)
    series_id = context.get("sonarr_series_id")
    if series_id:
        try:
            from bazarr_client import get_bazarr_client
            bazarr = get_bazarr_client()
            if bazarr:
                bazarr.notify_scan_disk(series_id)
        except Exception as e:
            logger.debug("Bazarr notification skipped: %s", e)

    # Jellyfin library refresh
    try:
        from jellyfin_client import get_jellyfin_client
        jellyfin = get_jellyfin_client()
        if jellyfin:
            jellyfin.refresh_library()
    except Exception as e:
        logger.debug("Jellyfin notification skipped: %s", e)


def scan_directory(directory, force=False):
    """Scan a directory for MKV files that need translation.

    Returns:
        list: List of dicts with file info including target_status
    """
    files = []
    for root, _dirs, filenames in os.walk(directory):
        for filename in sorted(filenames):
            if not filename.lower().endswith(".mkv"):
                continue
            mkv_path = os.path.join(root, filename)

            # Check external target subs only (no ffprobe — too slow for scan)
            target_status = detect_existing_target(mkv_path)

            if target_status == "ass" and not force:
                continue  # Goal achieved, skip

            files.append({
                "path": mkv_path,
                "target_status": target_status,
                "size_mb": os.path.getsize(mkv_path) / (1024 * 1024),
            })
    return files
