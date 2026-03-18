"""Subtitle convert routes: spell-check, convert, waveform-extract, waveform-audio."""

import contextlib
import logging
import os
import re
import subprocess
import tempfile
from collections import OrderedDict

from flask import jsonify, request

from routes.tools import bp
from routes.tools._helpers import PYSUBS2_EXT, SUPPORTED_FORMATS, _validate_file_path

logger = logging.getLogger(__name__)

_WAVEFORM_CACHE_MAX = 100
WAVEFORM_CACHE: OrderedDict = OrderedDict()  # (video_path, mtime) -> temp_opus_file_path


def _get_waveform_duration(video_path: str) -> float:
    """Get video duration in seconds via ffprobe."""
    import json as _json

    cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", video_path]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        data = _json.loads(r.stdout)
        return float(data.get("format", {}).get("duration", 0))
    except Exception:
        return 0.0


@bp.route("/spell-check", methods=["POST"])
def spell_check():
    """Spell-check a subtitle file using hunspell. Returns misspelled words.
    ---
    post:
      summary: Spell-check subtitle
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [file_path]
              properties:
                file_path:
                  type: string
                language:
                  type: string
                  default: de_DE
    """
    import pysubs2

    data = request.get_json(force=True, silent=True) or {}
    error, result = _validate_file_path(data.get("file_path", ""))
    if error:
        return jsonify({"error": error}), result

    abs_path = result
    language = data.get("language", "de_DE")

    try:
        import hunspell

        hobj = hunspell.HunSpell(
            f"/usr/share/hunspell/{language}.dic",
            f"/usr/share/hunspell/{language}.aff",
        )
    except Exception as e:
        return jsonify({"error": f"Hunspell not available for {language}: {e}"}), 503

    subs = pysubs2.load(abs_path)
    errors = []
    word_re = re.compile(r"\b[a-zA-ZäöüÄÖÜß]+\b")
    for cue in subs:
        clean = re.sub(r"\{[^}]+\}", "", cue.text)  # strip ASS override tags
        for word in word_re.findall(clean):
            if not hobj.spell(word):
                errors.append({"word": word, "start_ms": cue.start, "text": cue.text})

    logger.info("spell-check: %d errors in %s", len(errors), abs_path)
    return jsonify({"errors": errors, "total": len(errors)})


# -- Format Conversion ---------------------------------------------------------


@bp.route("/convert", methods=["POST"])
def convert_format():
    """Convert a subtitle file to a different format via pysubs2.
    ---
    post:
      summary: Convert subtitle format
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                file_path:
                  type: string
                  description: Path to an existing subtitle file
                track_index:
                  type: integer
                  description: Embedded track index (requires video_path)
                video_path:
                  type: string
                  description: Video file path (required when track_index is set)
                target_format:
                  type: string
                  enum: [srt, ass, ssa, vtt]
      responses:
        200:
          description: Conversion successful
          content:
            application/json:
              schema:
                type: object
                properties:
                  output_path:
                    type: string
                  format:
                    type: string
        400:
          description: Invalid request
        404:
          description: File or track not found
        500:
          description: Conversion failed
    """
    import pysubs2

    from config import map_path

    data = request.get_json(force=True, silent=True) or {}
    target_format = data.get("target_format", "").lower()
    file_path = data.get("file_path", "")
    track_index = data.get("track_index")
    video_path = data.get("video_path", "")

    if target_format not in SUPPORTED_FORMATS:
        return jsonify({"error": f"target_format must be one of {sorted(SUPPORTED_FORMATS)}"}), 400

    cleanup_source = False

    if track_index is not None:
        # Convert embedded subtitle track
        if not video_path:
            return jsonify({"error": "video_path required when track_index is set"}), 400
        video_path = map_path(video_path)
        if not os.path.exists(video_path):
            return jsonify({"error": f"Video not found: {video_path}"}), 404

        from ass_utils import extract_subtitle_stream, get_media_streams

        probe = get_media_streams(video_path)
        stream = next(
            (s for s in probe.get("streams", []) if s.get("index") == track_index),
            None,
        )
        if not stream:
            return jsonify({"error": f"Track {track_index} not found"}), 404

        codec = stream.get("codec_name", "subrip")
        ext = "ass" if codec in ("ass", "ssa") else "srt"
        tmp = tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False)
        tmp.close()
        extract_subtitle_stream(video_path, {"sub_index": track_index, "format": codec}, tmp.name)
        source_path = tmp.name
        cleanup_source = True
        base_output = os.path.splitext(video_path)[0]
    else:
        if not file_path:
            return jsonify({"error": "file_path or track_index required"}), 400
        source_path = map_path(file_path)
        if not os.path.exists(source_path):
            return jsonify({"error": f"File not found: {source_path}"}), 404
        base_output = os.path.splitext(source_path)[0]

    output_path = f"{base_output}.converted.{PYSUBS2_EXT[target_format]}"

    try:
        subs = pysubs2.load(source_path)
        subs.save(output_path, format_=target_format)
    except Exception as e:
        return jsonify({"error": f"Conversion failed: {e}"}), 500
    finally:
        if cleanup_source:
            with contextlib.suppress(OSError):
                os.unlink(source_path)

    logger.info("Converted %s -> %s (%s)", source_path, output_path, target_format)
    return jsonify({"output_path": output_path, "format": target_format})


# -- Waveform extraction -------------------------------------------------------


@bp.route("/waveform-extract", methods=["POST"])
def waveform_extract():
    """Extract audio from a video file as Opus for waveform display.
    ---
    post:
      summary: Extract waveform audio
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [video_path]
              properties:
                video_path:
                  type: string
      responses:
        200:
          description: Audio URL and duration
          content:
            application/json:
              schema:
                type: object
                properties:
                  audio_url:
                    type: string
                  duration_s:
                    type: number
        400:
          description: Missing video_path
        404:
          description: Video file not found
        500:
          description: ffmpeg extraction failed
    """
    data = request.get_json(force=True, silent=True) or {}
    video_path = data.get("video_path", "")

    if not video_path:
        return jsonify({"error": "video_path is required"}), 400

    from config import get_settings, map_path

    video_path = map_path(video_path)

    # Security: ensure video_path is under media_path
    _s = get_settings()
    _media_path = os.path.abspath(_s.media_path)
    _abs_video = os.path.abspath(video_path)
    if not _abs_video.startswith(_media_path + os.sep):
        return jsonify({"error": "video_path must be under the configured media_path"}), 403

    if not os.path.exists(video_path):
        return jsonify({"error": f"Video not found: {video_path}"}), 404

    mtime = os.path.getmtime(video_path)
    cache_key = (video_path, mtime)

    if cache_key in WAVEFORM_CACHE and os.path.exists(WAVEFORM_CACHE[cache_key]):
        audio_path = WAVEFORM_CACHE[cache_key]
        logger.debug("Waveform cache hit: %s", audio_path)
    else:
        # Extract audio as Opus (mono, 22 kHz — sufficient for waveform display)
        tmp = tempfile.NamedTemporaryFile(suffix=".opus", delete=False)
        tmp.close()
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            video_path,
            "-vn",
            "-ac",
            "1",
            "-ar",
            "22050",
            "-c:a",
            "libopus",
            "-b:a",
            "32k",
            tmp.name,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=120)
        except subprocess.TimeoutExpired:
            return jsonify({"error": "Audio extraction timed out"}), 500

        if result.returncode != 0:
            logger.error(
                "ffmpeg waveform extraction failed: %s", result.stderr.decode(errors="replace")
            )
            return jsonify({"error": "ffmpeg audio extraction failed"}), 500

        WAVEFORM_CACHE[cache_key] = tmp.name
        # Evict oldest entry if over capacity, delete its orphaned temp file
        if len(WAVEFORM_CACHE) > _WAVEFORM_CACHE_MAX:
            _, evicted_path = WAVEFORM_CACHE.popitem(last=False)
            try:
                if os.path.exists(evicted_path):
                    os.remove(evicted_path)
            except OSError as e:
                logger.debug("Waveform cache eviction cleanup failed: %s", e)
        audio_path = tmp.name
        logger.info("Waveform extracted: %s -> %s", video_path, audio_path)

    filename = os.path.basename(audio_path)
    return jsonify(
        {
            "audio_url": f"/api/v1/tools/waveform-audio/{filename}",
            "duration_s": _get_waveform_duration(video_path),
        }
    )


@bp.route("/waveform-audio/<filename>", methods=["GET"])
def serve_waveform_audio(filename: str):
    """Serve an extracted waveform audio file from the temp directory."""
    from flask import send_file

    if not filename.endswith(".opus"):
        return jsonify({"error": "Not found"}), 404

    # Security: prevent path traversal via filename
    safe_filename = os.path.basename(filename)
    if not safe_filename or safe_filename != filename:
        return jsonify({"error": "Invalid filename"}), 400
    audio_path = os.path.join(tempfile.gettempdir(), safe_filename)
    # Verify resolved path stays within tempdir
    if not os.path.realpath(audio_path).startswith(
        os.path.realpath(tempfile.gettempdir()) + os.sep
    ):
        return jsonify({"error": "Invalid filename"}), 400
    if not os.path.exists(audio_path):
        return jsonify({"error": "Not found"}), 404

    return send_file(audio_path, mimetype="audio/ogg")
