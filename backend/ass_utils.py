"""ASS/SRT subtitle utilities: style classification, tag handling, stream selection.

All language-specific logic is parameterized via config.py settings.
"""

import json
import logging
import os
import re
import subprocess

from config import get_settings

logger = logging.getLogger(__name__)

# Patterns for style classification
SIGNS_PATTERNS = re.compile(
    r"sign|^op$|^ed$|song|karaoke|title|note|insert|logo|screen|board|card|letter",
    re.IGNORECASE,
)
DIALOG_PATTERNS = re.compile(
    r"default|main|dialogue|italic|flashback|narrat|top|alt|internal|thought",
    re.IGNORECASE,
)

# ASS override tag pattern - matches {...} blocks
OVERRIDE_TAG_RE = re.compile(r"\{[^}]*\}")

# Position/movement tags that indicate signs
POS_MOVE_RE = re.compile(r"\\(?:pos|move|org)\s*\(")


def has_target_language_stream(ffprobe_data, target_language=None):
    """Check if the file has an embedded target language subtitle stream.

    Args:
        ffprobe_data: dict from ffprobe JSON output
        target_language: Language code (e.g., "de"). If None, uses default from settings.

    Returns:
        str or None: "ass" if target lang ASS found, "srt" if SRT found, None otherwise.
        ASS takes priority over SRT.
    """
    if target_language is None:
        settings = get_settings()
        target_tags = settings.get_target_lang_tags()
    else:
        from config import _get_language_tags

        target_tags = _get_language_tags(target_language)

    target_ass = False
    target_srt = False

    for stream in ffprobe_data.get("streams", []):
        if stream.get("codec_type") != "subtitle":
            continue
        lang = stream.get("tags", {}).get("language", "").lower()
        if lang not in target_tags:
            continue
        codec = stream.get("codec_name", "").lower()
        if codec in ("ass", "ssa"):
            target_ass = True
        elif codec in ("subrip", "srt"):
            target_srt = True

    if target_ass:
        return "ass"
    if target_srt:
        return "srt"
    return None


def has_target_language_audio(ffprobe_data, target_language=None):
    """Check if the file has an audio track in the target language.

    Args:
        ffprobe_data: dict from ffprobe JSON output
        target_language: Language code (e.g., "de"). If None, uses default from settings.

    Returns:
        bool: True if a target language audio track is found.
    """
    if target_language is None:
        settings = get_settings()
        target_tags = settings.get_target_lang_tags()
    else:
        from config import _get_language_tags

        target_tags = _get_language_tags(target_language)

    for stream in ffprobe_data.get("streams", []):
        if stream.get("codec_type") != "audio":
            continue
        lang = stream.get("tags", {}).get("language", "").lower()
        if lang in target_tags:
            return True
    return False


def classify_styles(subs):
    """Classify subtitle styles into dialog (translate) and signs/songs (keep).

    Args:
        subs: pysubs2.SSAFile object

    Returns:
        tuple: (dialog_styles: set, signs_styles: set)
    """
    dialog_styles = set()
    signs_styles = set()

    # Collect lines per style for heuristic analysis
    style_lines = {}
    for event in subs.events:
        if event.is_comment:
            continue
        style_name = event.style
        if style_name not in style_lines:
            style_lines[style_name] = []
        style_lines[style_name].append(event.text)

    for style_name in style_lines:
        # Check explicit patterns first
        if SIGNS_PATTERNS.search(style_name):
            signs_styles.add(style_name)
            continue

        if DIALOG_PATTERNS.search(style_name):
            dialog_styles.add(style_name)
            continue

        # Heuristic: check if >80% of lines have \pos() or \move() tags
        lines = style_lines[style_name]
        if lines:
            pos_count = sum(1 for line in lines if POS_MOVE_RE.search(line))
            if pos_count / len(lines) > 0.8:
                signs_styles.add(style_name)
                continue

        # Default: treat as dialog
        dialog_styles.add(style_name)

    logger.info(
        "Style classification - Dialog: %s, Signs/Songs: %s",
        dialog_styles,
        signs_styles,
    )
    return dialog_styles, signs_styles


def extract_tags(text):
    """Extract ASS override tags from text, return clean text, tag info, and original length.

    Args:
        text: ASS dialog text with potential override tags

    Returns:
        tuple: (clean_text, tag_info, original_clean_length) where tag_info is a list of
               (position, tag_string) tuples for restoration
    """
    if not OVERRIDE_TAG_RE.search(text):
        return text, [], len(text)

    tag_info = []
    parts = OVERRIDE_TAG_RE.split(text)
    tags = OVERRIDE_TAG_RE.findall(text)

    clean_parts = []
    current_clean_pos = 0

    for i, part in enumerate(parts):
        if i > 0 and i - 1 < len(tags):
            tag_info.append((current_clean_pos, tags[i - 1]))
        clean_parts.append(part)
        current_clean_pos += len(part)

    clean_text = "".join(clean_parts)
    return clean_text, tag_info, len(clean_text)


def restore_tags(translated_text, tag_info, original_clean_length=None):
    """Restore ASS override tags into translated text using proportional positioning.

    Position-0 tags (prefix) stay at the beginning. Other tags are placed
    proportionally based on original/translated length ratio, snapped to the
    nearest word boundary within +/- 3 characters.

    Args:
        translated_text: Translated text without tags
        tag_info: List of (position, tag_string) from extract_tags()
        original_clean_length: Length of original clean text (for proportional calc)

    Returns:
        Text with override tags restored
    """
    if not tag_info:
        return translated_text

    result = []
    text_pos = 0
    trans_len = len(translated_text)
    orig_len = original_clean_length or trans_len

    sorted_tags = sorted(tag_info, key=lambda x: x[0])

    for pos, tag in sorted_tags:
        if pos == 0:
            insert_pos = 0
        elif orig_len > 0:
            ratio = pos / orig_len
            insert_pos = int(ratio * trans_len)
            # Snap to nearest word boundary within +/- 3 chars
            best = insert_pos
            for offset in range(-3, 4):
                check = insert_pos + offset
                if 0 <= check <= trans_len:
                    if check == trans_len or translated_text[check] in (" ", "\\"):
                        best = check
                        break
            insert_pos = best
        else:
            insert_pos = min(pos, trans_len)

        # Never go backwards
        insert_pos = max(insert_pos, text_pos)
        insert_pos = min(insert_pos, trans_len)

        if insert_pos > text_pos:
            result.append(translated_text[text_pos:insert_pos])
            text_pos = insert_pos
        result.append(tag)

    if text_pos < trans_len:
        result.append(translated_text[text_pos:])

    return "".join(result)


def fix_line_breaks(text):
    """Fix line breaks after translation.

    The model sometimes converts \\N to \\n or literal newlines.
    """
    text = text.replace("\n", "\\N")
    text = re.sub(r"(?<!\\)\\n", r"\\N", text)
    text = re.sub(r"  +", " ", text)
    return text.strip()


def select_best_subtitle_stream(ffprobe_data, format_filter=None):
    """Select the best source language subtitle stream from ffprobe data.

    Priority (ASS preferred over SRT):
    1. Source lang ASS with "Full" in title (not Signs/Songs)
    2. First source lang ASS without "sign"/"song"
    3. First source lang ASS
    4. ASS without target lang tag, not "sign"/"song"
    5. First source lang SRT (fallback)
    6. First SRT without target lang tag
    7. None

    Args:
        ffprobe_data: dict from ffprobe JSON output
        format_filter: "ass" to only search ASS, "srt" for only SRT, None for all

    Returns:
        dict with sub_index, format, language, title — or None
    """
    settings = get_settings()
    source_tags = settings.get_source_lang_tags()
    target_tags = settings.get_target_lang_tags()

    streams = ffprobe_data.get("streams", [])
    ass_streams = []
    srt_streams = []

    sub_index = 0
    for stream in streams:
        if stream.get("codec_type") != "subtitle":
            continue
        codec = stream.get("codec_name", "").lower()
        title = stream.get("tags", {}).get("title", "").lower()
        language = stream.get("tags", {}).get("language", "").lower()

        info = {
            "sub_index": sub_index,
            "stream_index": stream.get("index"),
            "title": title,
            "language": language,
        }

        if codec in ("ass", "ssa") and format_filter != "srt":
            info["format"] = "ass"
            ass_streams.append(info)
        elif (
            codec in ("subrip", "srt", "mov_text", "webvtt", "text", "microdvd")
            and format_filter != "ass"
        ):
            info["format"] = "srt"
            srt_streams.append(info)

        sub_index += 1

    # --- ASS Priority ---
    if ass_streams:
        # P1: "Full" subtitle (not signs/songs only)
        for s in ass_streams:
            if "full" in s["title"] and "sign" not in s["title"] and "song" not in s["title"]:
                logger.info("Selected stream %d: '%s' (Full ASS)", s["sub_index"], s["title"])
                return s

        # P2: Source language, non-signs
        src = [s for s in ass_streams if s["language"] in source_tags]
        for s in src:
            if "sign" not in s["title"] and "song" not in s["title"]:
                logger.info(
                    "Selected stream %d: '%s' (Source lang ASS, non-signs)",
                    s["sub_index"],
                    s["title"],
                )
                return s

        # P3: Any source language ASS
        if src:
            logger.info(
                "Selected stream %d: '%s' (Source lang ASS)", src[0]["sub_index"], src[0]["title"]
            )
            return src[0]

        # P4: Non-signs ASS without target lang tag
        for s in ass_streams:
            if (
                s["language"] not in target_tags
                and "sign" not in s["title"]
                and "song" not in s["title"]
            ):
                logger.info("Selected stream %d: '%s' (non-signs ASS)", s["sub_index"], s["title"])
                return s

    # --- SRT Fallback ---
    if srt_streams:
        # P5: Source language SRT
        src_srt = [s for s in srt_streams if s["language"] in source_tags]
        if src_srt:
            logger.info(
                "Selected stream %d: '%s' (Source lang SRT fallback)",
                src_srt[0]["sub_index"],
                src_srt[0]["title"],
            )
            return src_srt[0]

        # P6: Any SRT without target lang tag
        for s in srt_streams:
            if s["language"] not in target_tags:
                logger.info("Selected stream %d: '%s' (SRT fallback)", s["sub_index"], s["title"])
                return s

    # P7: target-language SRT as last resort (e.g. German dub in MP4)
    if srt_streams:
        tgt_srt = [s for s in srt_streams if s["language"] in target_tags]
        if tgt_srt:
            logger.info(
                "Selected stream %d: '%s' (Target lang SRT last resort)",
                tgt_srt[0]["sub_index"],
                tgt_srt[0]["title"],
            )
            return tgt_srt[0]

    # Last resort: any ASS stream at all
    if ass_streams:
        logger.warning("No ideal stream, using first ASS: %s", ass_streams[0]["title"])
        return ass_streams[0]

    return None


def run_ffprobe(file_path, use_cache=True):
    """Run ffprobe and return parsed JSON data for audio and subtitle streams.

    Uses cache if available and file hasn't changed (mtime check).

    Args:
        file_path: Path to the video file
        use_cache: If True, check cache first and store result

    Returns:
        dict: Parsed ffprobe JSON data with {"streams": [...]} containing both
              audio and subtitle streams (codec_type "audio" / "subtitle").

    Raises:
        RuntimeError: If ffprobe fails, times out, or returns invalid JSON
    """
    import os

    from db.cache import get_ffprobe_cache, set_ffprobe_cache

    # Check cache if enabled
    if use_cache:
        try:
            mtime = os.path.getmtime(file_path)
            cached = get_ffprobe_cache(file_path, mtime)
            if cached:
                logger.debug("Using cached ffprobe data for %s", file_path)
                return cached
        except (OSError, Exception) as e:
            logger.debug("Cache check failed for %s: %s", file_path, e)

    # Run ffprobe — no -select_streams filter so both audio and subtitle streams
    # are returned. Consumers filter by codec_type themselves. Previously this used
    # -select_streams s which caused has_target_language_audio() to never find
    # audio streams (bug fix).
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_streams",
        file_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"ffprobe timed out after 30s: {file_path}")
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")
    try:
        probe_data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"ffprobe returned invalid JSON: {e}")

    # Cache the result
    if use_cache:
        try:
            mtime = os.path.getmtime(file_path)
            set_ffprobe_cache(file_path, mtime, probe_data)
        except (OSError, Exception) as e:
            logger.debug("Cache store failed for %s: %s", file_path, e)

    return probe_data


def get_media_streams(file_path, use_cache=True):
    """Unified entry point for media stream metadata — engine-agnostic.

    Reads scan_metadata_engine from config and routes to ffprobe or mediainfo.
    Both engines return the same normalized {"streams": [...]} format, so the
    cache is engine-agnostic: an entry written by one engine is valid for another.

    Args:
        file_path: Path to the video file
        use_cache: If True, check cache before probing and store result after

    Returns:
        dict: {"streams": [...]} with audio and subtitle stream objects.

    Raises:
        RuntimeError: On probe failure (engine-specific errors propagate).
        FileNotFoundError: If engine=mediainfo and mediainfo is not installed.
    """
    import os

    from config import get_settings
    from db.cache import get_ffprobe_cache, set_ffprobe_cache

    settings = get_settings()
    engine = getattr(settings, "scan_metadata_engine", "auto")

    # Cache check — shared across all engines (same format, engine-agnostic)
    if use_cache:
        try:
            mtime = os.path.getmtime(file_path)
            cached = get_ffprobe_cache(file_path, mtime)
            if cached:
                logger.debug("Cache hit for %s (engine=%s)", file_path, engine)
                return cached
        except (OSError, Exception) as e:
            logger.debug("Cache check failed for %s: %s", file_path, e)

    probe_data = _run_engine(file_path, engine)

    if use_cache:
        try:
            mtime = os.path.getmtime(file_path)
            set_ffprobe_cache(file_path, mtime, probe_data)
        except (OSError, Exception) as e:
            logger.debug("Cache store failed for %s: %s", file_path, e)

    return probe_data


def _run_engine(file_path, engine):
    """Dispatch to the configured metadata engine with fallback logic for 'auto'."""
    from mediainfo_utils import _is_mediainfo_available, run_mediainfo

    if engine == "mediainfo":
        return run_mediainfo(file_path)

    if engine == "auto":
        if _is_mediainfo_available():
            try:
                return run_mediainfo(file_path)
            except Exception as e:
                logger.warning("MediaInfo failed for %s, falling back to ffprobe: %s", file_path, e)
        return run_ffprobe(file_path, use_cache=False)

    # engine == "ffprobe" or unknown
    return run_ffprobe(file_path, use_cache=False)


def extract_subtitle_stream(mkv_path, stream_info, output_path):
    """Extract a subtitle stream (ASS or SRT) from an MKV file.

    Args:
        mkv_path: Path to the MKV file
        stream_info: dict from select_best_subtitle_stream() (needs sub_index, format)
        output_path: Path to write the extracted file

    Raises:
        RuntimeError: If ffmpeg fails
    """
    ext = os.path.splitext(output_path)[1].lower().lstrip(".")
    _encoder_map = {"srt": "srt", "ass": "ass", "ssa": "ass", "vtt": "webvtt"}
    encoder = _encoder_map.get(ext, "copy")
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        mkv_path,
        "-map",
        f"0:s:{stream_info['sub_index']}",
        "-c:s",
        encoder,
        output_path,
    ]
    from config import get_settings

    _timeout = getattr(get_settings(), "ffmpeg_timeout", 120)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=_timeout)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg extraction failed: {result.stderr}")
    logger.info(
        "Extracted %s stream %d to %s",
        stream_info.get("format", "?"),
        stream_info["sub_index"],
        output_path,
    )
