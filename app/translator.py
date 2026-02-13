"""Core translation orchestration: extract, translate, reassemble subtitles.

Supports ASS (primary) and SRT (fallback) subtitle formats.
German ASS is always the goal — SRT output only when no ASS source exists.
"""

import os
import re
import shutil
import tempfile
import logging

import pysubs2

from ass_utils import (
    run_ffprobe,
    has_german_stream,
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

# Patterns for detecting existing German subtitle files
GERMAN_ASS_PATTERNS = [".de.ass", ".deu.ass", ".ger.ass", ".german.ass"]
GERMAN_SRT_PATTERNS = [".de.srt", ".deu.srt", ".ger.srt", ".german.srt"]

# Patterns for detecting existing English subtitle files
ENGLISH_SUB_PATTERNS = [
    ".en.srt", ".eng.srt", ".english.srt",
    ".en.ass", ".eng.ass", ".english.ass",
]

# Common English words that indicate a subtitle was not actually translated
ENGLISH_MARKER_WORDS = {
    "the", "and", "that", "have", "for", "not", "with", "you",
    "this", "but", "from", "they", "will", "what", "about",
}


def get_output_path(mkv_path, fmt="ass"):
    """Get the output path for a translated subtitle file."""
    base = os.path.splitext(mkv_path)[0]
    return f"{base}.de.{fmt}"


def detect_existing_german(mkv_path, probe_data=None):
    """Detect existing German subtitles (external files and embedded streams).

    Returns:
        str or None: "ass" if German ASS found, "srt" if only German SRT found,
        None if no German subtitle exists. ASS takes priority over SRT.
    """
    base = os.path.splitext(mkv_path)[0]

    # Check external files — ASS first (higher priority)
    for pattern in GERMAN_ASS_PATTERNS:
        if os.path.exists(base + pattern):
            return "ass"

    has_srt = False
    for pattern in GERMAN_SRT_PATTERNS:
        if os.path.exists(base + pattern):
            has_srt = True
            break

    # Check embedded streams
    if probe_data:
        embedded = has_german_stream(probe_data)
        if embedded == "ass":
            return "ass"
        if embedded == "srt":
            has_srt = True

    return "srt" if has_srt else None


def find_external_english_srt(mkv_path):
    """Find an external English subtitle file next to the MKV."""
    base = os.path.splitext(mkv_path)[0]
    for pattern in ENGLISH_SUB_PATTERNS:
        path = base + pattern
        if os.path.exists(path):
            logger.info("Found external English subtitle: %s", path)
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
    """Translate an ASS subtitle stream to German .de.ass."""
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

        info_title = subs.info.get("Title", "")
        if not info_title.startswith("[DE]"):
            subs.info["Title"] = f"[DE] {info_title}"

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
    """Translate an embedded SRT subtitle stream to German .de.srt."""
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
    """Translate an external SRT file to German .de.srt."""
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


def translate_file(mkv_path, force=False, bazarr_context=None):
    """Translate subtitles for a single MKV file.

    Three-case priority chain (German ASS is always the goal):

    FALL A: German ASS exists → Skip (goal achieved)
    FALL B: German SRT exists → Upgrade attempt:
        B1: Bazarr search for German ASS
        B2: English ASS embedded → translate to .de.ass
        B3: No upgrade possible → keep SRT
    FALL C: No German subtitle:
        C1: English ASS embedded → .de.ass
        C2: English SRT (embedded/external) → .de.srt
        C3: Bazarr fetch English SRT → .de.srt
        C4: Nothing → Fail

    After successful translation: notify Bazarr (scan-disk) if context provided.
    """
    if not os.path.exists(mkv_path):
        raise FileNotFoundError(f"File not found: {mkv_path}")

    logger.info("Processing: %s", mkv_path)
    probe_data = run_ffprobe(mkv_path)

    if not force:
        german_status = detect_existing_german(mkv_path, probe_data)
    else:
        german_status = None

    result = None

    # ═══ FALL A: German ASS exists → Done ═══
    if german_status == "ass":
        logger.info("Fall A: German ASS already exists, skipping")
        return _skip_result("German ASS already exists")

    # ═══ FALL B: German SRT exists → Upgrade attempt to ASS ═══
    if german_status == "srt":
        logger.info("Fall B: German SRT found, attempting upgrade to ASS")

        # B1: Bazarr search for German ASS
        if bazarr_context:
            try:
                from bazarr_client import get_bazarr_client
                bazarr = get_bazarr_client()
                if bazarr:
                    de_ass = bazarr.search_german_ass(
                        bazarr_context.get("sonarr_series_id"),
                        bazarr_context.get("sonarr_episode_id"),
                    )
                    if de_ass:
                        logger.info("Fall B1: Bazarr found German ASS (upgrade from SRT)")
                        return _skip_result("German ASS downloaded via Bazarr (upgraded from SRT)")
            except Exception as e:
                logger.warning("Bazarr search_german_ass failed: %s", e)

        # B2: English ASS embedded → translate to .de.ass
        best_ass = select_best_subtitle_stream(probe_data, format_filter="ass")
        if best_ass:
            logger.info("Fall B2: Upgrading — translating English ASS to German ASS")
            result = translate_ass(mkv_path, best_ass, probe_data)
            if result["success"]:
                result["stats"]["upgrade_from_srt"] = True
                _notify_bazarr(bazarr_context)
                return result

        # B3: No upgrade possible
        logger.info("Fall B3: No ASS upgrade available, keeping German SRT")
        return _skip_result("German SRT exists, no ASS upgrade available")

    # ═══ FALL C: No German subtitle → Full pipeline ═══

    # C1: English ASS embedded → .de.ass
    best_stream = select_best_subtitle_stream(probe_data)
    if best_stream and best_stream["format"] == "ass":
        logger.info("Fall C1: Translating English ASS to German ASS")
        result = translate_ass(mkv_path, best_stream, probe_data)
        if result["success"]:
            _notify_bazarr(bazarr_context)
        return result

    # C2: English SRT embedded → .de.srt
    if best_stream and best_stream["format"] == "srt":
        logger.info("Fall C2: Translating embedded English SRT to German SRT")
        result = translate_srt_from_stream(mkv_path, best_stream)
        if result["success"]:
            _notify_bazarr(bazarr_context)
        return result

    # C2b: External English SRT → .de.srt
    ext_srt = find_external_english_srt(mkv_path)
    if ext_srt:
        logger.info("Fall C2b: Translating external English SRT to German SRT")
        result = translate_srt_from_file(mkv_path, ext_srt)
        if result["success"]:
            _notify_bazarr(bazarr_context)
        return result

    # C3: Bazarr fetch English SRT → .de.srt
    if bazarr_context:
        try:
            from bazarr_client import get_bazarr_client
            bazarr = get_bazarr_client()
            if bazarr:
                logger.info("Fall C3: Asking Bazarr to fetch English SRT")
                eng_srt_path = bazarr.fetch_english_srt(
                    bazarr_context.get("sonarr_series_id"),
                    bazarr_context.get("sonarr_episode_id"),
                )
                if eng_srt_path:
                    result = translate_srt_from_file(
                        mkv_path, eng_srt_path, source="bazarr_english_srt"
                    )
                    if result["success"]:
                        _notify_bazarr(bazarr_context)
                    return result
        except Exception as e:
            logger.warning("Bazarr fetch_english_srt failed: %s", e)

    # C4: Nothing found
    logger.warning("Fall C4: No English subtitle source found for %s", mkv_path)
    return _fail_result("No English subtitle source found")


def _notify_bazarr(bazarr_context):
    """Notify Bazarr about new subtitle files (scan-disk)."""
    if not bazarr_context:
        return
    series_id = bazarr_context.get("sonarr_series_id")
    if not series_id:
        return
    try:
        from bazarr_client import get_bazarr_client
        bazarr = get_bazarr_client()
        if bazarr:
            bazarr.notify_scan_disk(series_id)
    except Exception as e:
        logger.warning("Bazarr scan-disk notification failed: %s", e)


def scan_directory(directory, force=False):
    """Scan a directory for MKV files that need translation.

    Returns:
        list: List of dicts with file info including german_status
    """
    files = []
    for root, _dirs, filenames in os.walk(directory):
        for filename in sorted(filenames):
            if not filename.lower().endswith(".mkv"):
                continue
            mkv_path = os.path.join(root, filename)

            # Check external German subs only (no ffprobe — too slow for scan)
            german_status = detect_existing_german(mkv_path)

            if german_status == "ass" and not force:
                continue  # Goal achieved, skip

            files.append({
                "path": mkv_path,
                "german_status": german_status,
                "size_mb": os.path.getsize(mkv_path) / (1024 * 1024),
            })
    return files
