"""Tracks routes."""

import logging, os, tempfile
from flask import Blueprint, jsonify, request
from ass_utils import get_media_streams, extract_subtitle_stream
from config import map_path

bp = Blueprint("tracks", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)
_CODEC_EXT = {"ass": "ass", "ssa": "ass", "srt": "srt", "subrip": "srt", "webvtt": "vtt", "mov_text": "srt", "microdvd": "srt", "text": "srt"}

def _get_video_path(ep_id):
    from sonarr_client import get_sonarr_client
    client = get_sonarr_client()
    if client is None:
        return None
    path = client.get_episode_file_path(ep_id)
    if not path:
        return None
    return map_path(path)

def _normalise_stream(stream, stream_index, type_index):
    tags = stream.get("tags") or {}
    codec = (stream.get("codec_name") or "").lower()
    disposition = stream.get("disposition") or {}
    return {"index": stream_index, "sub_index": type_index, "codec_type": stream.get("codec_type", ""), "codec": codec, "language": tags.get("language") or tags.get("lang") or "", "title": tags.get("title") or tags.get("handler_name") or "", "forced": bool(disposition.get("forced")), "default": bool(disposition.get("default"))}

def _build_track_list(streams):
    tracks, subtitle_index, audio_index, seen_indices = [], 0, 0, set()
    for raw_index, stream in enumerate(streams):
        codec_type = (stream.get("codec_type") or "").lower()
        if codec_type not in ("audio", "subtitle"): continue
        abs_index = stream.get("index", raw_index)
        if abs_index in seen_indices: abs_index = raw_index
        seen_indices.add(abs_index)
        if codec_type == "subtitle":
            track = _normalise_stream(stream, abs_index, subtitle_index); subtitle_index += 1
        else:
            track = _normalise_stream(stream, abs_index, audio_index); audio_index += 1
        tracks.append(track)
    return tracks

def _find_track(tracks, index):
    for t in tracks:
        if t["index"] == index: return t
    return None


@bp.route("/library/episodes/<int:ep_id>/tracks", methods=["GET"])
def list_tracks(ep_id):
    """Return all audio and subtitle tracks embedded in the episode video file."""
    video_path = _get_video_path(ep_id)
    if not video_path:
        return jsonify({"error": "Episode has no video file or Sonarr is not configured"}), 404
    if not os.path.exists(video_path):
        return jsonify({"error": "Video file not found on disk: " + video_path}), 404
    try:
        probe = get_media_streams(video_path)
    except RuntimeError as exc:
        logger.error("Stream probe failed for ep %d (%s): %s", ep_id, video_path, exc)
        return jsonify({"error": "Failed to probe video file: " + str(exc)}), 500
    except Exception:
        logger.exception("Unexpected error probing ep %d", ep_id)
        return jsonify({"error": "Internal server error"}), 500
    raw_streams = probe.get("streams", [])
    tracks = _build_track_list(raw_streams)
    return jsonify({"tracks": tracks, "video_path": video_path}), 200


@bp.route("/library/episodes/<int:ep_id>/tracks/<int:index>/extract", methods=["POST"])
def extract_track(ep_id, index):
    """Extract a subtitle track as a sidecar file. Audio tracks return 400."""
    body = request.get_json(force=True, silent=True) or {}
    video_path = _get_video_path(ep_id)
    if not video_path:
        return jsonify({"error": "Episode has no video file or Sonarr is not configured"}), 404
    if not os.path.exists(video_path):
        return jsonify({"error": "Video file not found on disk: " + video_path}), 404
    try:
        probe = get_media_streams(video_path)
    except RuntimeError as exc:
        return jsonify({"error": "Failed to probe video file: " + str(exc)}), 500
    except Exception:
        return jsonify({"error": "Internal server error"}), 500
    tracks = _build_track_list(probe.get("streams", []))
    track = _find_track(tracks, index)
    if track is None:
        return jsonify({"error": "Track index " + str(index) + " not found"}), 404
    if track["codec_type"] != "subtitle":
        return jsonify({"error": "Only subtitle tracks can be extracted"}), 400
    language = body.get("language") or track["language"] or "und"
    ext = _CODEC_EXT.get(track["codec"], "ass")
    base, _ = os.path.splitext(video_path)
    output_path = base + "." + language + "." + ext
    stream_info = {"sub_index": track["sub_index"], "format": ext}
    try:
        extract_subtitle_stream(video_path, stream_info, output_path)
    except RuntimeError as exc:
        return jsonify({"error": "Extraction failed: " + str(exc)}), 500
    except Exception:
        return jsonify({"error": "Internal server error"}), 500
    return jsonify({"output_path": output_path, "language": language, "format": ext, "track": track}), 200


@bp.route("/library/episodes/<int:ep_id>/tracks/<int:index>/use-as-source", methods=["POST"])
def use_track_as_source(ep_id, index):
    """Extract subtitle track content to a tempfile, read it inline. Audio tracks return 400."""
    video_path = _get_video_path(ep_id)
    if not video_path:
        return jsonify({"error": "Episode has no video file or Sonarr is not configured"}), 404
    if not os.path.exists(video_path):
        return jsonify({"error": "Video file not found on disk: " + video_path}), 404
    try:
        probe = get_media_streams(video_path)
    except RuntimeError as exc:
        return jsonify({"error": "Failed to probe video file: " + str(exc)}), 500
    except Exception:
        return jsonify({"error": "Internal server error"}), 500
    tracks = _build_track_list(probe.get("streams", []))
    track = _find_track(tracks, index)
    if track is None:
        return jsonify({"error": "Track index " + str(index) + " not found"}), 404
    if track["codec_type"] != "subtitle":
        return jsonify({"error": "Only subtitle tracks can be used as source"}), 400
    ext = _CODEC_EXT.get(track["codec"], "ass")
    language = track["language"] or "und"
    stream_info = {"sub_index": track["sub_index"], "format": ext}
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(suffix="." + ext)
        os.close(fd)
        extract_subtitle_stream(video_path, stream_info, tmp_path)
        with open(tmp_path, "r", encoding="utf-8", errors="replace") as fh:
            content = fh.read()
    except RuntimeError as exc:
        return jsonify({"error": "Extraction failed: " + str(exc)}), 500
    except OSError as exc:
        return jsonify({"error": "File I/O error: " + str(exc)}), 500
    except Exception:
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError as exc:
                logger.warning("Could not remove tempfile %s: %s", tmp_path, exc)
    return jsonify({"content": content, "format": ext, "language": language, "title": track.get("title", "")}), 200
