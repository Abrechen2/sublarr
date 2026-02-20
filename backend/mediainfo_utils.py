"""MediaInfo-based media stream metadata extraction.

Provides run_mediainfo() which returns the same normalized format as run_ffprobe()
in ass_utils.py — {"streams": [...]} with ffprobe-compatible field names.
"""

import json
import shutil
import logging
import subprocess
import functools

logger = logging.getLogger(__name__)

# MediaInfo Format field → ffprobe codec_name
MEDIAINFO_CODEC_MAP = {
    # Subtitle formats
    "advanced substation alpha": "ass",
    "ass": "ass",
    "substation alpha": "ssa",
    "ssa": "ssa",
    "utf-8": "subrip",
    "subrip": "subrip",
    "srt": "subrip",
    "vobsub": "dvd_subtitle",
    "pgs": "hdmv_pgs_subtitle",
    "pgssub": "hdmv_pgs_subtitle",
    "dvb subtitle": "dvb_subtitle",
    "webvtt": "webvtt",
    "timed text": "mov_text",
    # Audio formats
    "aac": "aac",
    "ac-3": "ac3",
    "e-ac-3": "eac3",
    "dts": "dts",
    "dts-hd ma": "dts",
    "truehd": "truehd",
    "flac": "flac",
    "mp3": "mp3",
    "opus": "opus",
    "vorbis": "vorbis",
    "pcm": "pcm_s16le",
}


@functools.lru_cache(maxsize=1)
def _is_mediainfo_available() -> bool:
    """Check once per process whether mediainfo is on PATH. Thread-safe via lru_cache."""
    return shutil.which("mediainfo") is not None


def run_mediainfo(file_path: str) -> dict:
    """Run mediainfo and return normalized stream data in ffprobe-compatible format.

    Args:
        file_path: Path to the video file. Passed as a list argument to subprocess
                   (no shell=True) to prevent command injection.

    Returns:
        dict: {"streams": [...]} normalized to ffprobe format. Each stream has:
              codec_type, codec_name, index, tags (language, title), disposition (forced).

    Raises:
        FileNotFoundError: If mediainfo is not installed / not on PATH.
        RuntimeError: If mediainfo fails, times out, or returns invalid JSON.
    """
    if not _is_mediainfo_available():
        raise FileNotFoundError("mediainfo not found in PATH — install mediainfo or switch engine to ffprobe")

    cmd = ["mediainfo", "--Output=JSON", file_path]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"mediainfo timed out after 30s: {file_path}")

    if result.returncode != 0:
        raise RuntimeError(f"mediainfo failed (exit {result.returncode}): {result.stderr.strip()}")

    try:
        raw = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"mediainfo returned invalid JSON: {e}")

    return _normalize_mediainfo(raw)


def _normalize_mediainfo(raw: dict) -> dict:
    """Convert MediaInfo JSON output to ffprobe-compatible stream format.

    MediaInfo JSON structure:
        {"media": {"track": [
            {"@type": "General", ...},
            {"@type": "Video",   ...},
            {"@type": "Audio",   "Format": "AAC", "Language": "en", ...},
            {"@type": "Text",    "Format": "ASS", "Language": "jpn", "Forced": "No", ...},
        ]}}

    Only Audio (@type: Audio) and Subtitle (@type: Text) tracks are included.
    General and Video tracks are skipped.

    Returns:
        dict: {"streams": [...]} matching the ffprobe contract used by ass_utils consumers.
    """
    tracks = raw.get("media", {}).get("track", [])
    streams = []
    stream_index = 0

    for track in tracks:
        track_type = track.get("@type", "")

        if track_type == "Audio":
            streams.append({
                "codec_type": "audio",
                "codec_name": _map_codec(track.get("Format", "")),
                "index": stream_index,
                "tags": {
                    "language": _normalize_language(track.get("Language", "")),
                    "title": track.get("Title", ""),
                },
                "disposition": {},
            })
            stream_index += 1

        elif track_type == "Text":
            # Forced: MediaInfo uses "Yes"/"No" string; ffprobe uses int 0/1
            forced = track.get("Forced", "No").strip().lower() == "yes"
            streams.append({
                "codec_type": "subtitle",
                "codec_name": _map_codec(track.get("Format", "")),
                "index": stream_index,
                "tags": {
                    "language": _normalize_language(track.get("Language", "")),
                    "title": track.get("Title", ""),
                },
                "disposition": {"forced": 1 if forced else 0},
            })
            stream_index += 1

    return {"streams": streams}


def _map_codec(format_str: str) -> str:
    """Map a MediaInfo Format string to ffprobe codec_name.

    Falls back to the lowercase original if no mapping is found.
    """
    return MEDIAINFO_CODEC_MAP.get(format_str.strip().lower(), format_str.strip().lower())


def _normalize_language(lang: str) -> str:
    """Normalize a MediaInfo language value to a lowercase trimmed string.

    MediaInfo may return ISO 639-1 (2-letter), ISO 639-2 (3-letter), or full names.
    We pass through as-is (lowercased) since ass_utils language matching already
    handles both 2- and 3-letter codes via get_source_lang_tags / get_target_lang_tags.
    """
    return lang.strip().lower()
