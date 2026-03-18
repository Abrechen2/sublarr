"""Output path detection functions for translated subtitle files."""

import logging
import os

from ass_utils import has_target_language_stream
from config import get_settings

logger = logging.getLogger(__name__)


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


def detect_existing_target_for_lang(
    mkv_path, target_language, probe_data=None, subtitle_type: str = "full"
):
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

    # Check embedded subtitle streams for the specific target language
    if probe_data:
        embedded = has_target_language_stream(probe_data, target_language)
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
