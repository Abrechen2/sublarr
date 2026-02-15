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
from translation import get_translation_manager
from translation.base import TranslationResult

logger = logging.getLogger(__name__)

MIN_FREE_SPACE_MB = 100

# Common English words that indicate a subtitle was not actually translated
ENGLISH_MARKER_WORDS = {
    "the", "and", "that", "have", "for", "not", "with", "you",
    "this", "but", "from", "they", "will", "what", "about",
}


def _is_whisper_enabled() -> bool:
    """Check if Whisper transcription is enabled in config."""
    try:
        from db.config import get_config_entry
        enabled = get_config_entry("whisper_enabled")
        return enabled is not None and enabled.lower() in ("true", "1", "yes")
    except Exception:
        return False


def _submit_whisper_job(mkv_path: str, arr_context: dict = None):
    """Submit a Whisper transcription job for the given media file.

    Case D is async: submits to the Whisper queue and returns a
    'whisper_pending' status. The queue worker handles transcription and
    can re-enter the translation pipeline after completion.

    Returns:
        Dict with status='whisper_pending' and job_id, or None if Whisper
        is not available.
    """
    try:
        from whisper import get_whisper_manager
        from routes.whisper import _get_queue
        from extensions import socketio
        import uuid

        manager = get_whisper_manager()
        backend = manager.get_active_backend()
        if not backend:
            logger.info("Case D: No Whisper backend configured")
            return None

        # Determine source language from config
        settings = get_settings()
        source_lang = settings.source_language or "ja"

        job_id = uuid.uuid4().hex
        queue = _get_queue()
        queue.submit(
            job_id=job_id,
            file_path=mkv_path,
            language=source_lang,
            source_language=source_lang,
            whisper_manager=manager,
            socketio=socketio,
        )

        logger.info("Case D: Submitted Whisper job %s for %s (language: %s)",
                    job_id, os.path.basename(mkv_path), source_lang)

        return {
            "success": True,
            "status": "whisper_pending",
            "whisper_job_id": job_id,
            "message": f"Whisper transcription queued (job {job_id[:8]}...)",
            "stats": {"source": "whisper", "whisper_job_id": job_id},
        }
    except Exception as e:
        logger.warning("Case D: Failed to submit Whisper job: %s", e)
        return None


def _extract_series_id(arr_context):
    """Extract Sonarr series_id from arr_context.
    
    Returns:
        int or None: Series ID if found, None otherwise
    """
    if not arr_context:
        return None
    
    # Try direct series_id field
    if arr_context.get("sonarr_series_id"):
        return arr_context["sonarr_series_id"]
    
    # Try series.id (from webhook)
    series = arr_context.get("series", {})
    if isinstance(series, dict) and series.get("id"):
        return series["id"]
    
    return None


def _resolve_backend_for_context(arr_context, target_language):
    """Resolve translation backend and fallback chain from language profile.

    Uses the arr_context to determine which series/movie profile to use.
    Falls back to the default profile if no specific assignment exists.

    Args:
        arr_context: Dict with sonarr_series_id or radarr_movie_id (or None)
        target_language: Target language code (unused currently, for future per-lang backends)

    Returns:
        tuple: (translation_backend: str, fallback_chain: list[str])
    """
    from db.profiles import get_default_profile, get_series_profile, get_movie_profile

    profile = None
    if arr_context:
        if arr_context.get("sonarr_series_id"):
            profile = get_series_profile(arr_context["sonarr_series_id"])
        elif arr_context.get("radarr_movie_id"):
            profile = get_movie_profile(arr_context["radarr_movie_id"])

    if not profile:
        profile = get_default_profile()

    backend = profile.get("translation_backend", "ollama")
    chain = profile.get("fallback_chain", ["ollama"])

    # Ensure primary backend is first in chain
    if backend not in chain:
        chain = [backend] + list(chain)

    return (backend, chain)


def _translate_with_manager(lines, source_lang, target_lang,
                            arr_context=None, series_id=None):
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
        list[str]: Translated lines in same order as input

    Raises:
        RuntimeError: If all backends in the fallback chain fail
    """
    _backend_name, fallback_chain = _resolve_backend_for_context(arr_context, target_lang)

    # Load glossary entries if series_id provided
    glossary_entries = None
    if series_id:
        try:
            from db.translation import get_glossary_for_series
            entries = get_glossary_for_series(series_id)
            if entries:
                glossary_entries = entries
                logger.debug("Loaded %d glossary entries for series %d", len(entries), series_id)
        except Exception as e:
            logger.debug("Failed to load glossary for series %d: %s", series_id, e)

    manager = get_translation_manager()
    result = manager.translate_with_fallback(
        lines, source_lang, target_lang, fallback_chain, glossary_entries
    )

    if result.success:
        return result.translated_lines, result
    else:
        raise RuntimeError(f"Translation failed: {result.error}")


def get_output_path(mkv_path, fmt="ass"):
    """Get the output path for a translated subtitle file."""
    settings = get_settings()
    base = os.path.splitext(mkv_path)[0]
    return f"{base}.{settings.target_language}.{fmt}"


def get_output_path_for_lang(mkv_path, fmt="ass", target_language=None):
    """Get the output path for a specific target language."""
    if not target_language:
        return get_output_path(mkv_path, fmt)
    base = os.path.splitext(mkv_path)[0]
    return f"{base}.{target_language}.{fmt}"


def detect_existing_target(mkv_path, probe_data=None):
    """Detect existing target language subtitles (external files and embedded streams).

    Returns:
        str or None: "ass" if target ASS found, "srt" if only target SRT found,
        None if no target language subtitle exists. ASS takes priority over SRT.
    """
    settings = get_settings()
    return detect_existing_target_for_lang(mkv_path, settings.target_language, probe_data)


def detect_existing_target_for_lang(mkv_path, target_language, probe_data=None,
                                    subtitle_type: str = "full"):
    """Detect existing subtitles for a specific target language and subtitle type.

    When subtitle_type is "forced", only checks for .forced. pattern files
    (e.g., movie.de.forced.ass). When subtitle_type is "full" (default),
    checks non-forced files only (original behavior).

    Returns:
        str or None: "ass" if target ASS found, "srt" if only target SRT found,
        None if no target language subtitle exists.
    """
    from config import _get_language_tags
    base = os.path.splitext(mkv_path)[0]
    lang_tags = _get_language_tags(target_language)

    if subtitle_type == "forced":
        # Only check for .forced. pattern files
        for tag in lang_tags:
            if os.path.exists(f"{base}.{tag}.forced.ass"):
                return "ass"
        for tag in lang_tags:
            if os.path.exists(f"{base}.{tag}.forced.srt"):
                return "srt"
        return None

    # Default "full" behavior: check non-forced files
    # Check external files — ASS first (higher priority)
    for tag in lang_tags:
        if os.path.exists(f"{base}.{tag}.ass"):
            return "ass"

    has_srt = False
    for tag in lang_tags:
        if os.path.exists(f"{base}.{tag}.srt"):
            has_srt = True
            break

    # Also check for .forced. patterns so they are not invisible to scanner
    for tag in lang_tags:
        if os.path.exists(f"{base}.{tag}.forced.ass"):
            # Forced ASS exists but we're looking for full -- don't count it
            pass
        if os.path.exists(f"{base}.{tag}.forced.srt"):
            # Forced SRT exists but we're looking for full -- don't count it
            pass

    # Check embedded streams (only works for default target language)
    if probe_data:
        embedded = has_target_language_stream(probe_data)
        if embedded == "ass":
            return "ass"
        if embedded == "srt":
            has_srt = True

    return "srt" if has_srt else None


def get_forced_output_path(mkv_path, fmt="ass", target_language=None):
    """Get the output path for a forced/signs subtitle file.

    Follows Plex/Jellyfin/Emby/Kodi standard naming convention:
    {base}.{lang}.forced.{fmt}

    Args:
        mkv_path: Path to the video file.
        fmt: Subtitle format ("ass" or "srt").
        target_language: Target language code. If None, uses config default.

    Returns:
        str: Output path like /path/to/Movie.de.forced.ass
    """
    if not target_language:
        settings = get_settings()
        target_language = settings.target_language
    base = os.path.splitext(mkv_path)[0]
    return f"{base}.{target_language}.forced.{fmt}"


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
        errors.append(f"Output too long: {total_trans/total_orig:.1f}x")
    empty = sum(1 for t in translated_texts if not t.strip())
    if empty > len(translated_texts) * 0.3:
        errors.append(f"Too many empty lines: {empty}/{len(translated_texts)}")
    return len(errors) == 0, errors


def translate_ass(mkv_path, stream_info, probe_data,
                  target_language=None, target_language_name=None,
                  arr_context=None):
    """Translate an ASS subtitle stream to target language .{lang}.ass."""
    output_path = get_output_path_for_lang(mkv_path, "ass", target_language)
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

        # HI-removal before translation
        settings = get_settings()
        if settings.hi_removal_enabled:
            from hi_remover import remove_hi_from_ass_events
            dialog_texts = remove_hi_from_ass_events(dialog_texts)

        series_id = _extract_series_id(arr_context)
        tgt_lang = target_language or settings.target_language
        translated_texts, translation_result = _translate_with_manager(
            dialog_texts,
            source_lang=settings.source_language,
            target_lang=tgt_lang,
            arr_context=arr_context,
            series_id=series_id,
        )

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

        lang_tag = tgt_lang.upper()
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
                "backend_name": translation_result.backend_name,
            },
            "error": None,
        }

    except Exception as e:
        logger.exception("ASS translation failed for %s", mkv_path)
        return _fail_result(str(e))
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def translate_srt_from_stream(mkv_path, stream_info, target_language=None, arr_context=None):
    """Translate an embedded SRT subtitle stream to target language .{lang}.srt."""
    output_path = get_output_path_for_lang(mkv_path, "srt", target_language)
    check_disk_space(output_path)

    with tempfile.NamedTemporaryFile(suffix=".srt", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        extract_subtitle_stream(mkv_path, stream_info, tmp_path)
        return _translate_srt(tmp_path, output_path, source="embedded_srt", arr_context=arr_context)
    except Exception as e:
        logger.exception("SRT stream translation failed for %s", mkv_path)
        return _fail_result(str(e))
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def translate_srt_from_file(mkv_path, srt_path, source="external_srt",
                           target_language=None, arr_context=None):
    """Translate an external SRT file to target language .{lang}.srt."""
    output_path = get_output_path_for_lang(mkv_path, "srt", target_language)
    check_disk_space(output_path)

    try:
        return _translate_srt(srt_path, output_path, source=source, arr_context=arr_context)
    except Exception as e:
        logger.exception("SRT file translation failed for %s", mkv_path)
        return _fail_result(str(e))


def _translate_srt(srt_path, output_path, source="srt", arr_context=None):
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

    # HI-removal before translation
    if get_settings().hi_removal_enabled:
        from hi_remover import remove_hi_markers
        dialog_texts = [remove_hi_markers(t) for t in dialog_texts]

    logger.info("SRT lines to translate: %d", len(dialog_texts))
    # Extract series_id for glossary
    series_id = _extract_series_id(arr_context)
    settings = get_settings()
    translated_texts, translation_result = _translate_with_manager(
        dialog_texts,
        source_lang=settings.source_language,
        target_lang=settings.target_language,
        arr_context=arr_context,
        series_id=series_id,
    )

    # Validate translation output
    validation_errors = []
    is_valid, validation_errors = validate_translation_output(dialog_texts, translated_texts, format="srt")
    if not is_valid:
        logger.warning("SRT translation validation failed: %s", validation_errors)
        # Retry logic: max 2 retries
        for retry in range(2):
            logger.info("Retrying SRT translation (attempt %d/2)...", retry + 1)
            translated_texts, translation_result = _translate_with_manager(
                dialog_texts,
                source_lang=settings.source_language,
                target_lang=settings.target_language,
                arr_context=arr_context,
                series_id=series_id,
            )
            is_valid, validation_errors = validate_translation_output(dialog_texts, translated_texts, format="srt")
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
            "backend_name": translation_result.backend_name,
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


def _search_providers_for_target_ass(mkv_path, context=None, target_language=None):
    """Search subtitle providers for a target language ASS file.

    Returns:
        str or None: path to downloaded ASS file, or None
    """
    try:
        from providers import get_provider_manager
        from providers.base import VideoQuery, SubtitleFormat, ProviderAuthError, ProviderRateLimitError

        settings = get_settings()
        tgt_lang = target_language or settings.target_language
        manager = get_provider_manager()

        query = _build_video_query(mkv_path, context)
        query.languages = [tgt_lang]

        result = manager.search_and_download_best(
            query, format_filter=SubtitleFormat.ASS
        )
        if result and result.content:
            output_path = get_output_path_for_lang(mkv_path, "ass", tgt_lang)
            manager.save_subtitle(result, output_path)
            logger.info("Provider %s delivered target ASS: %s", result.provider_name, output_path)
            return output_path
    except ProviderAuthError as e:
        logger.error("Provider authentication failed — check API keys: %s", e)
    except ProviderRateLimitError as e:
        logger.error("Provider rate limit exceeded — retry later: %s", e)
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
        from providers.base import VideoQuery, SubtitleFormat, ProviderAuthError, ProviderRateLimitError

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
    except ProviderAuthError as e:
        logger.error("Provider authentication failed — check API keys: %s", e)
    except ProviderRateLimitError as e:
        logger.error("Provider rate limit exceeded — retry later: %s", e)
    except Exception as e:
        logger.warning("Provider search for source subtitle failed: %s", e)

    return None, None


def _record_config_hash_for_result(result, file_path):
    """Record the translation config hash for a successful translation job.

    Includes backend_name in the hash so that switching backends triggers
    re-translation detection.
    """
    if not result or not result.get("success") or result.get("stats", {}).get("skipped"):
        return
    try:
        settings = get_settings()
        backend_name = result.get("stats", {}).get("backend_name", "ollama")
        config_hash = settings.get_translation_config_hash(backend_name=backend_name)
        from db.translation import record_translation_config
        # For non-Ollama backends, model is not relevant
        model_info = settings.ollama_model if backend_name == "ollama" else backend_name
        record_translation_config(
            config_hash=config_hash,
            ollama_model=model_info,
            prompt_template=settings.get_prompt_template()[:200],
            target_language=settings.target_language,
        )
        # Store hash in result stats for job record
        result.setdefault("stats", {})["config_hash"] = config_hash
    except Exception as e:
        logger.debug("Failed to record config hash: %s", e)


def translate_file(mkv_path, force=False, arr_context=None,
                   target_language=None, target_language_name=None):
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
    settings = get_settings()
    tgt_lang = target_language or settings.target_language
    tgt_name = target_language_name or settings.target_language_name

    if not os.path.exists(mkv_path):
        raise FileNotFoundError(f"File not found: {mkv_path}")

    logger.info("Processing: %s (target: %s)", mkv_path, tgt_lang)
    probe_data = run_ffprobe(mkv_path)

    if not force:
        target_status = detect_existing_target_for_lang(mkv_path, tgt_lang, probe_data)
    else:
        target_status = None

    result = None

    # Helper to get output path with the right language
    def _out(fmt):
        return get_output_path_for_lang(mkv_path, fmt, tgt_lang)

    # === CASE A: Target ASS exists → Done ===
    if target_status == "ass":
        logger.info("Case A: Target ASS already exists, skipping")
        return _skip_result(f"{tgt_name} ASS already exists")

    # === CASE B: Target SRT exists → Upgrade attempt to ASS ===
    if target_status == "srt":
        logger.info("Case B: Target SRT found, attempting upgrade to ASS")

        # B1: Provider search for target ASS
        target_ass_path = _search_providers_for_target_ass(
            mkv_path, arr_context, target_language=tgt_lang)
        if target_ass_path:
            logger.info("Case B1: Provider found target ASS (upgrade from SRT)")
            return _skip_result(
                f"{tgt_name} ASS downloaded via provider (upgraded from SRT)",
                output_path=target_ass_path,
            )

        # B2: Source ASS embedded → translate to .{lang}.ass
        best_ass = select_best_subtitle_stream(probe_data, format_filter="ass")
        if best_ass:
            logger.info("Case B2: Upgrading — translating source ASS to target ASS")
            result = translate_ass(mkv_path, best_ass, probe_data,
                                   target_language=tgt_lang, target_language_name=tgt_name,
                                   arr_context=arr_context)
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
    best_stream = select_best_subtitle_stream(probe_data)
    if best_stream and best_stream["format"] == "ass":
        logger.info("Case C1: Translating source ASS to target ASS")
        result = translate_ass(mkv_path, best_stream, probe_data,
                               target_language=tgt_lang, target_language_name=tgt_name,
                               arr_context=arr_context)
        if result["success"]:
            _record_config_hash_for_result(result, mkv_path)
            _notify_integrations(arr_context, file_path=mkv_path)
        return result

    # C2: Source SRT embedded → .{lang}.srt
    if best_stream and best_stream["format"] == "srt":
        logger.info("Case C2: Translating embedded source SRT to target SRT")
        result = translate_srt_from_stream(mkv_path, best_stream,
                                           target_language=tgt_lang, arr_context=arr_context)
        if result["success"]:
            _record_config_hash_for_result(result, mkv_path)
            _notify_integrations(arr_context, file_path=mkv_path)
        return result

    # C2b: External source SRT → .{lang}.srt
    ext_srt = find_external_source_sub(mkv_path)
    if ext_srt:
        logger.info("Case C2b: Translating external source SRT to target SRT")
        result = translate_srt_from_file(mkv_path, ext_srt,
                                         target_language=tgt_lang, arr_context=arr_context)
        if result["success"]:
            _record_config_hash_for_result(result, mkv_path)
            _notify_integrations(arr_context, file_path=mkv_path)
        return result

    # C3: Provider search for source subtitle → translate
    src_path, src_fmt = _search_providers_for_source_sub(mkv_path, arr_context)
    if src_path:
        if src_fmt == "ass":
            logger.info("Case C3: Translating provider source ASS to target ASS")
            result = _translate_external_ass(mkv_path, src_path,
                                             target_language=tgt_lang,
                                             target_language_name=tgt_name,
                                             arr_context=arr_context)
        else:
            logger.info("Case C3: Translating provider source SRT to target SRT")
            result = translate_srt_from_file(mkv_path, src_path,
                                             source="provider_source_srt",
                                             target_language=tgt_lang,
                                             arr_context=arr_context)
        if result and result["success"]:
            _record_config_hash_for_result(result, mkv_path)
            _notify_integrations(arr_context, file_path=mkv_path)
        return result

    # C4: Nothing found from providers/embedded
    logger.warning("Case C4: No source subtitle found for %s", mkv_path)

    # === CASE D: Whisper transcription as last resort ===
    if _is_whisper_enabled():
        logger.info("Case D: No subtitle source found, attempting Whisper transcription for %s", mkv_path)
        whisper_result = _submit_whisper_job(mkv_path, arr_context)
        if whisper_result:
            return whisper_result
        logger.warning("Case D: Whisper transcription not available or failed to submit for %s", mkv_path)

    return _fail_result(f"No {settings.source_language_name} subtitle source found")


def _translate_external_ass(mkv_path, ass_path, target_language=None,
                           target_language_name=None, arr_context=None):
    """Translate a downloaded external ASS file to target language."""
    output_path = get_output_path_for_lang(mkv_path, "ass", target_language)
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

        # HI-removal before translation
        if get_settings().hi_removal_enabled:
            from hi_remover import remove_hi_from_ass_events
            dialog_texts = remove_hi_from_ass_events(dialog_texts)

        # Extract series_id for glossary
        series_id = _extract_series_id(arr_context)
        settings = get_settings()
        tgt_lang = target_language or settings.target_language
        translated_texts, translation_result = _translate_with_manager(
            dialog_texts,
            source_lang=settings.source_language,
            target_lang=tgt_lang,
            arr_context=arr_context,
            series_id=series_id,
        )

        # Validate translation output
        is_valid, validation_errors = validate_translation_output(dialog_texts, translated_texts, format="ass")
        if not is_valid:
            logger.warning("Translation validation failed: %s", validation_errors)
            # Retry logic: max 2 retries
            for retry in range(2):
                logger.info("Retrying translation (attempt %d/2)...", retry + 1)
                translated_texts, translation_result = _translate_with_manager(
                    dialog_texts,
                    source_lang=settings.source_language,
                    target_lang=tgt_lang,
                    arr_context=arr_context,
                    series_id=series_id,
                )
                is_valid, validation_errors = validate_translation_output(dialog_texts, translated_texts, format="ass")
                if is_valid:
                    break
                logger.warning("Retry %d validation failed: %s", retry + 1, validation_errors)

            if not is_valid:
                logger.error("Translation validation failed after retries: %s", validation_errors)
                # Log for manual review but continue (non-fatal)

        if len(translated_texts) != len(dialog_texts):
            return _fail_result(
                f"Translation count mismatch: expected {len(dialog_texts)}, got {len(translated_texts)}"
            )

        quality_warnings = _check_translation_quality(dialog_texts, translated_texts)
        if validation_errors:
            quality_warnings.extend([f"Validation: {e}" for e in validation_errors])
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

        lang_tag = tgt_lang.upper()
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
                "backend_name": translation_result.backend_name,
            },
            "error": None,
        }

    except Exception as e:
        logger.exception("External ASS translation failed for %s", mkv_path)
        return _fail_result(str(e))


def _notify_integrations(context, file_path=None):
    """Notify all configured media servers about new subtitle files.

    Args:
        context: arr_context dict with sonarr_series_id, sonarr_episode_id, or radarr_movie_id
        file_path: File path for media server item lookup
    """
    if not context or not file_path:
        return

    item_type = ""
    if context.get("sonarr_series_id") or context.get("sonarr_episode_id"):
        item_type = "episode"
    elif context.get("radarr_movie_id"):
        item_type = "movie"

    try:
        from mediaserver import get_media_server_manager
        manager = get_media_server_manager()
        results = manager.refresh_all(file_path, item_type)
        for r in results:
            if r.success:
                logger.info("Media server refresh: %s", r.message)
            else:
                logger.warning("Media server refresh failed: %s", r.message)
    except Exception as e:
        logger.warning("Media server notification failed: %s", e)


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
