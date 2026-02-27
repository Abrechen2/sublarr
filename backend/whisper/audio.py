"""Audio extraction utilities for Whisper speech-to-text.

Provides ffprobe-based audio stream selection and ffmpeg-based audio
extraction to 16kHz mono WAV (optimal for Whisper models).
"""

import json
import logging
import os
import subprocess

logger = logging.getLogger(__name__)

# ISO 639 language tag mapping: maps short codes to all known variants.
# Covers common anime/media languages to avoid external dependency.
LANGUAGE_TAG_MAP: dict[str, list[str]] = {
    "ja": ["ja", "jpn"],
    "en": ["en", "eng"],
    "de": ["de", "deu", "ger"],
    "fr": ["fr", "fra", "fre"],
    "es": ["es", "spa"],
    "zh": ["zh", "zho", "chi"],
    "ko": ["ko", "kor"],
    "pt": ["pt", "por"],
    "ru": ["ru", "rus"],
    "it": ["it", "ita"],
    "ar": ["ar", "ara"],
    "nl": ["nl", "nld", "dut"],
    "pl": ["pl", "pol"],
    "sv": ["sv", "swe"],
}

# Build reverse map: any tag -> canonical short code
_TAG_TO_CANONICAL: dict[str, str] = {}
for _short, _variants in LANGUAGE_TAG_MAP.items():
    for _tag in _variants:
        _TAG_TO_CANONICAL[_tag.lower()] = _short


def get_audio_streams(file_path: str) -> list[dict]:
    """Get audio stream information from a media file using ffprobe.

    Args:
        file_path: Path to the media file

    Returns:
        List of audio stream dicts with index, language, codec, channels

    Raises:
        RuntimeError: If ffprobe fails or is not available
    """
    if not os.path.exists(file_path):
        raise RuntimeError(f"File not found: {file_path}")

    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-select_streams",
        "a",
        "-print_format",
        "json",
        "-show_streams",
        file_path,
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=30,
        )
    except FileNotFoundError:
        raise RuntimeError("ffprobe not found. Install ffmpeg to enable audio analysis.")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"ffprobe timed out analyzing: {file_path}")

    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"ffprobe failed (code {proc.returncode}): {stderr}")

    try:
        data = json.loads(proc.stdout.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as e:
        raise RuntimeError(f"ffprobe returned invalid JSON: {e}")

    streams = data.get("streams", [])
    result = []
    for idx, stream in enumerate(streams):
        tags = stream.get("tags", {})
        language = tags.get("language", "und")
        result.append(
            {
                "stream_index": idx,
                "codec": stream.get("codec_name", "unknown"),
                "channels": stream.get("channels", 0),
                "language": language,
                "title": tags.get("title", ""),
            }
        )

    return result


def select_audio_track(
    file_path: str,
    preferred_language: str = "ja",
) -> dict:
    """Select the best audio track for transcription.

    Matches preferred_language against audio stream language tags using
    both ISO 639-1 and 639-2 codes. Falls back to the first audio stream
    if no language match is found.

    Args:
        file_path: Path to the media file
        preferred_language: ISO 639-1 language code (default: "ja" for anime)

    Returns:
        Dict with stream_index, language, codec, channels

    Raises:
        RuntimeError: If no audio streams are found
    """
    streams = get_audio_streams(file_path)

    if not streams:
        raise RuntimeError(f"No audio streams found in: {file_path}")

    # Build set of acceptable tags for the preferred language
    preferred_lower = preferred_language.lower()
    acceptable_tags = set()

    # If the preferred language is in our map, use all variants
    if preferred_lower in LANGUAGE_TAG_MAP:
        acceptable_tags = {t.lower() for t in LANGUAGE_TAG_MAP[preferred_lower]}
    else:
        # Check if the preferred language is itself a variant (e.g., "jpn")
        canonical = _TAG_TO_CANONICAL.get(preferred_lower)
        if canonical and canonical in LANGUAGE_TAG_MAP:
            acceptable_tags = {t.lower() for t in LANGUAGE_TAG_MAP[canonical]}
        else:
            # Unknown language -- match exact only
            acceptable_tags = {preferred_lower}

    # Try to match a stream by language
    for stream in streams:
        stream_lang = stream["language"].lower()
        if stream_lang in acceptable_tags:
            logger.info(
                "Selected audio track %d (%s, %s, %dch) matching language '%s'",
                stream["stream_index"],
                stream["language"],
                stream["codec"],
                stream["channels"],
                preferred_language,
            )
            return stream

    # Fallback: first audio stream
    fallback = streams[0]
    logger.info(
        "No audio track matching '%s' found, falling back to track %d (%s, %s, %dch)",
        preferred_language,
        fallback["stream_index"],
        fallback["language"],
        fallback["codec"],
        fallback["channels"],
    )
    return fallback


def extract_audio_to_wav(
    file_path: str,
    stream_index: int,
    output_path: str,
) -> str:
    """Extract an audio track to 16kHz mono WAV (optimal for Whisper).

    Args:
        file_path: Path to the media file
        stream_index: Audio stream index to extract
        output_path: Path to write the WAV file

    Returns:
        The output_path on success

    Raises:
        RuntimeError: If ffmpeg fails or is not available
    """
    cmd = [
        "ffmpeg",
        "-i",
        file_path,
        "-map",
        f"0:a:{stream_index}",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        "-y",  # Overwrite output
        output_path,
    ]

    logger.info(
        "Extracting audio track %d from %s to %s",
        stream_index,
        os.path.basename(file_path),
        os.path.basename(output_path),
    )

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=300,  # 5 minutes for long files
        )
    except FileNotFoundError:
        raise RuntimeError("ffmpeg not found. Install ffmpeg to enable audio extraction.")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"ffmpeg audio extraction timed out (300s): {file_path}")

    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"ffmpeg failed (code {proc.returncode}): {stderr}")

    if not os.path.exists(output_path):
        raise RuntimeError(f"ffmpeg did not produce output file: {output_path}")

    file_size = os.path.getsize(output_path)
    logger.info(
        "Extracted audio: %s (%.1f MB)",
        os.path.basename(output_path),
        file_size / (1024 * 1024),
    )

    return output_path
