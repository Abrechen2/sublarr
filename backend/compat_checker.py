"""Subtitle compatibility checker for Plex and Kodi media players.

Stateless validation functions that check subtitle file naming and placement
against media player conventions. Pure functions -- no Flask dependencies.

Plex docs: https://support.plex.tv/articles/200471133-adding-local-subtitles-to-your-media/
Kodi docs: https://kodi.wiki/view/Subtitles
"""

import os

# ---------------------------------------------------------------------------
# Common ISO 639 language codes (reasonable hardcoded set of ~50 common codes)
# ---------------------------------------------------------------------------

_ISO_639_1 = {
    "aa", "ab", "af", "am", "an", "ar", "as", "az",
    "ba", "be", "bg", "bn", "bo", "br", "bs",
    "ca", "ce", "co", "cs", "cy",
    "da", "de",
    "el", "en", "eo", "es", "et", "eu",
    "fa", "fi", "fo", "fr", "fy",
    "ga", "gd", "gl", "gu",
    "ha", "he", "hi", "hr", "hu", "hy",
    "id", "is", "it",
    "ja", "jv",
    "ka", "kk", "km", "kn", "ko", "ku", "ky",
    "la", "lb", "lo", "lt", "lv",
    "mg", "mi", "mk", "ml", "mn", "mr", "ms", "mt", "my",
    "nb", "ne", "nl", "nn", "no",
    "pa", "pl", "ps", "pt",
    "rm", "ro", "ru", "rw",
    "sa", "sd", "si", "sk", "sl", "so", "sq", "sr", "sv", "sw",
    "ta", "te", "tg", "th", "ti", "tk", "tl", "tr", "tt",
    "ug", "uk", "ur", "uz",
    "vi",
    "wo",
    "yi",
    "zh", "zu",
}

_ISO_639_2 = {
    "aar", "abk", "afr", "aka", "amh", "ara", "arg", "asm", "aze",
    "bak", "bel", "ben", "bih", "bos", "bre", "bul",
    "cat", "ces", "chi", "cos", "cze",
    "dan", "deu", "dut",
    "ell", "eng", "epo", "est", "eus",
    "fas", "fin", "fra", "fre", "fry",
    "geo", "ger", "gla", "gle", "glg", "gre", "guj",
    "hat", "hau", "hbs", "heb", "hin", "hrv", "hun", "hye",
    "ice", "iku", "ind", "isl", "ita",
    "jav", "jpn",
    "kal", "kan", "kat", "kaz", "khm", "kin", "kor", "kur",
    "lao", "lat", "lav", "lit", "ltz",
    "mac", "mal", "mar", "mkd", "mlg", "mlt", "mon", "mri", "msa", "may", "mya",
    "nep", "nld", "nno", "nob", "nor",
    "pan", "per", "pol", "por", "pus",
    "que",
    "roh", "ron", "rum", "run", "rus",
    "san", "sin", "slk", "slo", "slv", "snd", "som", "spa", "sqi", "srp",
    "swa", "swe",
    "tam", "tel", "tgk", "tha", "tir", "tur", "tuk",
    "uig", "ukr", "urd", "uzb",
    "vie", "vol",
    "wel", "wol",
    "yid", "yor",
    "zho", "zul",
}


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _extract_lang_code(subtitle_filename: str) -> str | None:
    """Extract language code from a subtitle filename.

    Supports patterns:
    - basename.lang.ext  (e.g., Movie.en.srt)
    - basename.lang.forced.ext
    - basename.lang.sdh.ext
    - basename.lang.hi.ext

    Returns:
        The language code string, or None if not found.
    """
    name = os.path.splitext(subtitle_filename)[0]  # remove extension

    # Split by dots to find potential lang code
    parts = name.rsplit(".", 3)  # up to 3 from end
    if len(parts) < 2:
        return None

    # Check for modifiers: forced, sdh, hi, cc
    modifiers = {"forced", "sdh", "hi", "cc"}

    # Check last part (before extension was removed)
    candidate = parts[-1].lower()
    if candidate in modifiers and len(parts) >= 3:
        # The lang code is one position further back
        return parts[-2]
    else:
        return parts[-1]


def _is_valid_iso639(code: str) -> bool:
    """Check if a code is a valid ISO 639-1 or 639-2 language code."""
    lower = code.lower()
    return lower in _ISO_639_1 or lower in _ISO_639_2


def _is_valid_bcp47_or_name(code: str) -> bool:
    """Check if a code is a valid BCP 47 tag (with _ separator) or English language name.

    Kodi accepts:
    - ISO 639-1 (en, de)
    - ISO 639-2 (eng, deu)
    - BCP 47 with _ separator (pt_BR, zh_Hans)
    - English language name (English, German)
    """
    if _is_valid_iso639(code):
        return True

    # BCP 47 with underscore separator (e.g., pt_BR, zh_Hans)
    if "_" in code:
        base = code.split("_")[0]
        return _is_valid_iso639(base)

    # English language names (common ones)
    _LANGUAGE_NAMES = {
        "afrikaans", "albanian", "arabic", "armenian", "azerbaijani",
        "basque", "belarusian", "bengali", "bosnian", "breton", "bulgarian",
        "catalan", "chinese", "croatian", "czech",
        "danish", "dutch",
        "english", "esperanto", "estonian",
        "finnish", "french",
        "galician", "georgian", "german", "greek",
        "hebrew", "hindi", "hungarian",
        "icelandic", "indonesian", "irish", "italian",
        "japanese",
        "kazakh", "korean", "kurdish",
        "latvian", "lithuanian", "luxembourgish",
        "macedonian", "malay", "malayalam", "maltese", "mongolian",
        "nepali", "norwegian",
        "persian", "polish", "portuguese",
        "romanian", "russian",
        "serbian", "slovak", "slovenian", "spanish", "swahili", "swedish",
        "tamil", "telugu", "thai", "turkish",
        "ukrainian", "urdu", "uzbek",
        "vietnamese",
        "welsh",
    }
    return code.lower() in _LANGUAGE_NAMES


def _check_naming_match(sub_basename: str, video_basename: str) -> bool:
    """Check if subtitle basename (before lang code) matches video basename (before ext).

    Example: "Movie (2024)" from "Movie (2024).en.srt" matches
             "Movie (2024)" from "Movie (2024).mkv"
    """
    return sub_basename.lower() == video_basename.lower()


def _get_video_basename(video_path: str) -> str:
    """Get the basename of a video file (name without extension)."""
    return os.path.splitext(os.path.basename(video_path))[0]


def _get_sub_basename(subtitle_filename: str) -> str:
    """Get the basename of a subtitle file (name without lang code and extension).

    Strips extension, then strips lang code and any modifiers (forced, sdh, hi, cc).
    """
    name = os.path.splitext(subtitle_filename)[0]  # remove .srt/.ass etc.
    parts = name.rsplit(".", 3)
    if len(parts) < 2:
        return name

    modifiers = {"forced", "sdh", "hi", "cc"}

    # Check how many trailing parts are modifiers or lang codes
    strip_count = 0
    for i in range(len(parts) - 1, 0, -1):
        part_lower = parts[i].lower()
        if part_lower in modifiers or _is_valid_iso639(part_lower) or _is_valid_bcp47_or_name(part_lower):
            strip_count += 1
        else:
            break

    if strip_count > 0:
        return ".".join(parts[:len(parts) - strip_count])
    return name


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_plex_compatibility(subtitle_path: str, video_path: str) -> dict:
    """Validate subtitle naming and placement against Plex conventions.

    Checks:
    a. Language code format (ISO 639-1 or 639-2, lowercase recommended)
    b. File extension (.srt, .ass, .ssa, .vtt, .smi)
    c. Placement (same dir as video, or Subtitles/Subs subfolder)
    d. Naming match (subtitle basename matches video basename)
    e. Uppercase language code warning

    Args:
        subtitle_path: Path to the subtitle file.
        video_path: Path to the video file.

    Returns:
        Dict with compatible (bool), issues (list), warnings (list),
        recommendations (list).
    """
    result = {
        "compatible": True,
        "issues": [],
        "warnings": [],
        "recommendations": [],
    }

    sub_filename = os.path.basename(subtitle_path)
    sub_dir = os.path.dirname(os.path.abspath(subtitle_path))
    video_dir = os.path.dirname(os.path.abspath(video_path))
    video_basename = _get_video_basename(video_path)
    sub_basename = _get_sub_basename(sub_filename)

    # a. Language code format
    lang_code = _extract_lang_code(sub_filename)
    if lang_code is None:
        result["issues"].append("No language code found in subtitle filename")
        result["compatible"] = False
    elif not _is_valid_iso639(lang_code):
        result["issues"].append(
            f"Language code '{lang_code}' is not a valid ISO 639-1 or 639-2 code"
        )
        result["compatible"] = False
    else:
        # e. Uppercase warning
        if lang_code != lang_code.lower():
            result["warnings"].append(
                f"Language code '{lang_code}' is not lowercase. "
                "Plex is case-sensitive on Linux; recommend lowercase for cross-platform compatibility."
            )

    # b. File extension
    _, ext = os.path.splitext(sub_filename)
    plex_extensions = {".srt", ".ass", ".ssa", ".vtt", ".smi"}
    if ext.lower() not in plex_extensions:
        result["issues"].append(
            f"File extension '{ext}' is not supported by Plex. "
            f"Supported: {', '.join(sorted(plex_extensions))}"
        )
        result["compatible"] = False

    # c. Placement: same directory or Subtitles/Subs subfolder
    if sub_dir != video_dir:
        # Check if subtitle is in a Subtitles or Subs subfolder relative to video
        relative = os.path.relpath(sub_dir, video_dir)
        valid_subfolders = {"subtitles", "subs"}
        if relative.lower() not in valid_subfolders:
            result["issues"].append(
                f"Subtitle is not in the same directory as the video or a "
                f"'Subtitles'/'Subs' subfolder. Relative path: '{relative}'"
            )
            result["compatible"] = False

    # d. Naming match
    if not _check_naming_match(sub_basename, video_basename):
        result["issues"].append(
            f"Subtitle basename '{sub_basename}' does not match video basename '{video_basename}'"
        )
        result["compatible"] = False

    # Recommendations
    if not result["issues"] and not result["warnings"]:
        result["recommendations"].append("Subtitle is fully Plex-compatible")

    return result


def check_kodi_compatibility(subtitle_path: str, video_path: str) -> dict:
    """Validate subtitle naming and placement against Kodi conventions.

    Checks:
    a. Language code (ISO 639-1, 639-2, BCP 47 with _, or English name)
    b. File extension (.srt, .ass, .ssa, .sub, .smi)
    c. Placement (must be same directory as video)
    d. Naming match

    Args:
        subtitle_path: Path to the subtitle file.
        video_path: Path to the video file.

    Returns:
        Dict with compatible (bool), issues (list), warnings (list),
        recommendations (list).
    """
    result = {
        "compatible": True,
        "issues": [],
        "warnings": [],
        "recommendations": [],
    }

    sub_filename = os.path.basename(subtitle_path)
    sub_dir = os.path.dirname(os.path.abspath(subtitle_path))
    video_dir = os.path.dirname(os.path.abspath(video_path))
    video_basename = _get_video_basename(video_path)
    sub_basename = _get_sub_basename(sub_filename)

    # a. Language code
    lang_code = _extract_lang_code(sub_filename)
    if lang_code is None:
        result["issues"].append("No language code found in subtitle filename")
        result["compatible"] = False
    elif not _is_valid_bcp47_or_name(lang_code):
        result["issues"].append(
            f"Language code '{lang_code}' is not a valid ISO 639-1, ISO 639-2, "
            f"BCP 47 (with _ separator), or English language name"
        )
        result["compatible"] = False

    # b. File extension
    _, ext = os.path.splitext(sub_filename)
    kodi_extensions = {".srt", ".ass", ".ssa", ".sub", ".smi"}
    if ext.lower() not in kodi_extensions:
        result["issues"].append(
            f"File extension '{ext}' is not supported by Kodi. "
            f"Supported: {', '.join(sorted(kodi_extensions))}"
        )
        result["compatible"] = False

    # c. Placement: must be same directory as video (Kodi does not support subfolder)
    if sub_dir != video_dir:
        result["issues"].append(
            "Subtitle must be in the same directory as the video file. "
            "Kodi does not support subtitle subfolders."
        )
        result["compatible"] = False

    # d. Naming match
    if not _check_naming_match(sub_basename, video_basename):
        result["issues"].append(
            f"Subtitle basename '{sub_basename}' does not match video basename '{video_basename}'"
        )
        result["compatible"] = False

    # Recommendations
    if not result["issues"] and not result["warnings"]:
        result["recommendations"].append("Subtitle is fully Kodi-compatible")

    return result


def batch_check_compatibility(
    subtitle_paths: list,
    video_path: str,
    target: str = "plex",
) -> dict:
    """Run compatibility check on multiple subtitle files.

    Args:
        subtitle_paths: List of subtitle file paths to check.
        video_path: Path to the associated video file.
        target: Target media player ("plex" or "kodi").

    Returns:
        Dict with results (list of individual results) and summary
        (total, compatible, incompatible counts).
    """
    checker = check_plex_compatibility if target == "plex" else check_kodi_compatibility

    results = []
    compatible_count = 0
    incompatible_count = 0

    for sub_path in subtitle_paths:
        check_result = checker(sub_path, video_path)
        results.append({
            "subtitle_path": sub_path,
            **check_result,
        })
        if check_result["compatible"]:
            compatible_count += 1
        else:
            incompatible_count += 1

    return {
        "results": results,
        "summary": {
            "total": len(subtitle_paths),
            "compatible": compatible_count,
            "incompatible": incompatible_count,
        },
    }
