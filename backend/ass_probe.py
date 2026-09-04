"""Media-stream probing utilities: ffprobe / mediainfo + stream selection.

Extracted from ass_utils.py. Covers anything that reads the container
(audio/subtitle stream metadata) or writes a subtitle stream out again:

- run_ffprobe / get_media_streams / _run_engine   — probe backends
- has_target_language_stream / has_target_language_audio
- get_all_subtitle_streams / select_best_subtitle_stream
- get_subtitle_stream_output_path / extract_subtitle_stream

The ASS tag-manipulation helpers (classify_styles, extract_tags,
restore_tags, fix_line_breaks) stay in ass_utils.py.
"""

import json
import logging
import os
import re
import subprocess

from config import get_settings

# 0.71.0 — SDH detection. Matches the common markers fansubs and studios
# use in track titles. Language codes never trigger this; we only inspect
# the `title` field (word-boundary) plus the ffprobe `hearing_impaired`
# disposition flag.
_SDH_TITLE_RE = re.compile(r"\b(sdh|cc|hi)\b", re.IGNORECASE)


def is_sdh_stream(stream: dict) -> bool:
    """Return True if the given ffprobe subtitle stream looks like SDH/CC/HI.

    Detection sources (either is sufficient):
      - `tags.title` matches /\b(sdh|cc|hi)\b/i
      - `disposition.hearing_impaired` is truthy
    """
    if not stream:
        return False
    tags = stream.get("tags") or {}
    title = tags.get("title") or ""
    if _SDH_TITLE_RE.search(title):
        return True
    disposition = stream.get("disposition") or {}
    return bool(disposition.get("hearing_impaired"))


logger = logging.getLogger(__name__)


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


def get_all_subtitle_streams(ffprobe_data: dict, exclude_language: str | None = None) -> list[dict]:
    """Return all embedded subtitle streams as a list of {lang, format} dicts.

    Args:
        ffprobe_data: dict from get_media_streams / ffprobe JSON output.
        exclude_language: ISO-639-1 code to exclude (typically the target language,
            already tracked separately in existing_sub). None = return all.

    Returns:
        Deduplicated list of dicts with 'lang' (raw language tag) and 'format'
        ('ass' or 'srt'). Unknown codecs (dvd_subtitle, etc.) are skipped.
    """
    exclude_tags: set[str] = set()
    if exclude_language:
        from config import _get_language_tags

        exclude_tags = _get_language_tags(exclude_language)

    seen: set[tuple] = set()
    result: list[dict] = []

    for stream in ffprobe_data.get("streams", []):
        if stream.get("codec_type") != "subtitle":
            continue
        lang = stream.get("tags", {}).get("language", "").lower()
        if not lang:
            continue
        if lang in exclude_tags:
            continue
        codec = stream.get("codec_name", "").lower()
        if codec in ("ass", "ssa"):
            fmt = "ass"
        elif codec in ("subrip", "srt"):
            fmt = "srt"
        else:
            continue
        key = (lang, fmt)
        if key not in seen:
            seen.add(key)
            result.append({"lang": lang, "format": fmt})

    return result


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

        # P4: Non-signs/songs/OP/ED ASS without target lang tag
        _SKIP_TITLE_PARTS = {"sign", "song", "op", "ed", "karaoke", "credit", "caption"}
        for s in ass_streams:
            if s["language"] not in target_tags and not any(
                part in s["title"] for part in _SKIP_TITLE_PARTS
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
    #
    # Audit Gemini-2026-05-09 R3: wrap ``file_path`` with ``_safe_arg_path``
    # so a leading ``-`` in the basename can't be interpreted as a flag by
    # ffprobe. Same defence ``extract_subtitle_stream`` already applied.
    # Loglevel is ``error``, not ``quiet``: ``quiet`` suppresses stderr entirely,
    # so the RuntimeError below interpolated an empty string and every failure
    # logged as a bare "ffprobe failed:" with no reason (prod 2026-08-01, where
    # the real cause — files deleted from disk — stayed invisible). ``error``
    # stays silent on success and only speaks up when something actually broke.
    from remux import _safe_arg_path

    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        _safe_arg_path(file_path),
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


def get_subtitle_stream_output_path(media_path: str, stream_info: dict) -> str:
    """Build sidecar output path: {basename}.{lang}.{format} next to media file.

    The container tag is ISO 639-2/B ("ger", "eng"); the name uses the
    canonical ISO 639-1 code the rest of Sublarr works in. Writing the raw tag
    grew a second German subtitle next to every existing ``.de`` one, and the
    caller's "already extracted" guard — which keys off this very path — never
    recognised the sidecar already sitting there. An unknown tag is passed
    through unchanged rather than guessed at.

    Uses 'und' (undetermined) if language tag is missing.
    """
    from config_language_data import normalize_language_code

    lang = normalize_language_code((stream_info.get("language") or "und").lower())
    fmt = stream_info.get("format", "ass")
    base = os.path.splitext(media_path)[0]
    return f"{base}.{lang}.{fmt}"


def get_legacy_subtitle_stream_output_path(media_path: str, stream_info: dict) -> str:
    """The name this sidecar had before the language code was canonicalised.

    Installs that ran the older code have their sidecars under the raw Matroska
    tag (``.ger.srt``). Callers check this path too, so canonicalising the name
    does not make Sublarr blind to a file it wrote itself and extract the same
    track a second time.
    """
    lang = (stream_info.get("language") or "und").lower()
    fmt = stream_info.get("format", "ass")
    base = os.path.splitext(media_path)[0]
    return f"{base}.{lang}.{fmt}"


def extract_subtitle_stream(mkv_path, stream_info, output_path):
    """Extract a subtitle stream (ASS or SRT) from an MKV file atomically.

    Audit G5 + G12: previously passed ``output_path`` straight into
    ``ffmpeg -y`` which writes incrementally to the destination. A crash,
    timeout, or ENOSPC mid-write left a partial sidecar at the final
    location that downstream code would treat as a complete file. The
    extraction now writes to a same-directory tempfile and only
    ``os.replace``s into place once ffmpeg exits zero. The temp file is
    unlinked on every error path so partial bytes never appear under the
    real name.

    Args:
        mkv_path: Path to the MKV file
        stream_info: dict from select_best_subtitle_stream() (needs sub_index, format)
        output_path: Path to write the extracted file

    Raises:
        RuntimeError: If ffmpeg fails. The destination is left untouched
            in this case — any pre-existing sidecar at ``output_path``
            stays intact.
    """
    import tempfile as _tempfile

    from remux import _safe_arg_path

    ext = os.path.splitext(output_path)[1].lower().lstrip(".")
    _encoder_map = {"srt": "srt", "ass": "ass", "ssa": "ass", "vtt": "webvtt"}
    encoder = _encoder_map.get(ext, "copy")

    out_dir = os.path.dirname(output_path) or "."
    out_suffix = os.path.splitext(output_path)[1] or ".tmp"
    fd, tmp_path = _tempfile.mkstemp(suffix=out_suffix, dir=out_dir)
    os.close(fd)

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        _safe_arg_path(mkv_path),
        "-map",
        f"0:s:{stream_info['sub_index']}",
        "-c:s",
        encoder,
        _safe_arg_path(tmp_path),
    ]
    _timeout = getattr(get_settings(), "ffmpeg_timeout", 300)
    from services.media_io_gate import MediaGateBusyError, media_io_gate

    try:
        try:
            with media_io_gate.slot("ffmpeg subtitle extraction"):
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=_timeout,
                )
        except MediaGateBusyError as exc:
            raise RuntimeError(str(exc)) from None
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg extraction failed: {result.stderr}")
        # Refuse zero-byte output — ffmpeg sometimes returns 0 on no-data
        # streams or when the disk filled mid-write but the buffer flushed
        # cleanly enough to get a successful exit code.
        if os.path.getsize(tmp_path) == 0:
            raise RuntimeError(
                "ffmpeg produced an empty sidecar (likely ENOSPC or unreadable stream)"
            )
        os.replace(tmp_path, output_path)
        tmp_path = ""  # ownership transferred — skip cleanup
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    logger.info(
        "Extracted %s stream %d to %s",
        stream_info.get("format", "?"),
        stream_info["sub_index"],
        output_path,
    )
