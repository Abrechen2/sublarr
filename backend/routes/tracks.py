"""Tracks routes."""

import logging
import os
import tempfile
import threading

from flask import Blueprint, current_app, jsonify, request

from ass_utils import extract_subtitle_stream, get_media_streams
from config import map_path
from events import emit_event

bp = Blueprint("tracks", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)
_CODEC_EXT = {
    "ass": "ass",
    "ssa": "ass",
    "srt": "srt",
    "subrip": "srt",
    "webvtt": "vtt",
    "mov_text": "srt",
    "microdvd": "srt",
    "text": "srt",
}


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
    return {
        "index": stream_index,
        "sub_index": type_index,
        "codec_type": stream.get("codec_type", ""),
        "codec": codec,
        "language": tags.get("language") or tags.get("lang") or "",
        "title": tags.get("title") or tags.get("handler_name") or "",
        "forced": bool(disposition.get("forced")),
        "default": bool(disposition.get("default")),
    }


def _build_track_list(streams):
    tracks, subtitle_index, audio_index, seen_indices = [], 0, 0, set()
    for raw_index, stream in enumerate(streams):
        codec_type = (stream.get("codec_type") or "").lower()
        if codec_type not in ("audio", "subtitle"):
            continue
        abs_index = stream.get("index", raw_index)
        if abs_index in seen_indices:
            abs_index = raw_index
        seen_indices.add(abs_index)
        if codec_type == "subtitle":
            track = _normalise_stream(stream, abs_index, subtitle_index)
            subtitle_index += 1
        else:
            track = _normalise_stream(stream, abs_index, audio_index)
            audio_index += 1
        tracks.append(track)
    return tracks


def _find_track(tracks, index):
    for t in tracks:
        if t["index"] == index:
            return t
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
    return jsonify(
        {"output_path": output_path, "language": language, "format": ext, "track": track}
    ), 200


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
        with open(tmp_path, encoding="utf-8", errors="replace") as fh:
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
    return jsonify(
        {"content": content, "format": ext, "language": language, "title": track.get("title", "")}
    ), 200


def _cleanup_series_sidecars(episode_files: dict, keep_langs: set, keep_format: str) -> int:
    """Remove sidecar subtitle files that are not in keep_langs after batch-extract.

    Args:
        episode_files: dict of episode_id -> {path: ...} from Sonarr
        keep_langs: set of ISO-639-1 language codes to keep (e.g. {"de", "en"})
        keep_format: "ass" | "srt" | "any" — if "ass", delete SRT when ASS exists for same lang

    Returns:
        Number of files deleted.
    """
    from routes.subtitles import scan_subtitle_sidecars  # noqa: I001

    deleted = 0

    for file_info in episode_files.values():
        raw_path = file_info.get("path")
        if not raw_path:
            continue
        video_path = map_path(raw_path)
        if not os.path.exists(video_path):
            continue

        sidecars = scan_subtitle_sidecars(video_path)

        # Build a set of (lang, format) for existing sidecars to support prefer-ass logic
        existing = {(s["language"], s["format"]): s["path"] for s in sidecars}

        for sidecar in sidecars:
            lang = sidecar["language"]
            fmt = sidecar["format"]
            path = sidecar["path"]

            # Delete if language not in keep list
            if lang not in keep_langs:
                try:
                    os.unlink(path)
                    deleted += 1
                    logger.debug("[auto-cleanup] removed %s (not in keep_languages)", path)
                except OSError as exc:
                    logger.warning("[auto-cleanup] could not remove %s: %s", path, exc)
                continue

            # Prefer-ASS: delete SRT when ASS exists for same language
            if keep_format == "ass" and fmt == "srt":
                if (lang, "ass") in existing:
                    try:
                        os.unlink(path)
                        deleted += 1
                        logger.debug("[auto-cleanup] removed SRT %s (ASS exists)", path)
                    except OSError as exc:
                        logger.warning("[auto-cleanup] could not remove %s: %s", path, exc)

    return deleted


@bp.route("/library/series/<int:series_id>/batch-extract-tracks", methods=["POST"])
def batch_extract_series_tracks(series_id):
    """Extract all embedded subtitle tracks from every episode file in a series.

    Runs in background. Returns 202 immediately. Skips files where the output
    subtitle already exists on disk. Per-track errors do not abort the batch.
    """
    app = current_app._get_current_object()

    def _run(app):
        from sonarr_client import get_sonarr_client

        with app.app_context():
            client = get_sonarr_client()
            if client is None:
                logger.error("[batch-extract-tracks] Sonarr not configured")
                return

            episode_files = client.get_episode_files_by_series(series_id)
            if not episode_files:
                logger.info("[batch-extract-tracks] no episode files for series %d", series_id)
                return

            succeeded = 0
            failed = 0
            skipped = 0

            episode_files_list = list(episode_files.values())
            total_files = len(episode_files_list)

            # Create an activity job so the extraction is visible on the Activity page
            _job_id = None
            try:
                from db.jobs import create_job, update_job as _update_job  # noqa: I001

                _job = create_job(
                    f"batch-extract: Serie {series_id} ({total_files} Dateien)",
                )
                _job_id = _job["id"]
                _update_job(_job_id, "running")
            except Exception:
                logger.debug("[batch-extract-tracks] could not create activity job")

            for file_idx, file_info in enumerate(episode_files_list):
                raw_path = file_info.get("path")
                if not raw_path:
                    skipped += 1
                    emit_event(
                        "batch_extract_progress",
                        {
                            "series_id": series_id,
                            "current": file_idx + 1,
                            "total": total_files,
                            "filename": "",
                            "status": "skipped",
                        },
                    )
                    continue
                video_path = map_path(raw_path)
                fname = os.path.basename(video_path)
                if not os.path.exists(video_path):
                    logger.debug("[batch-extract-tracks] file not found: %s", video_path)
                    skipped += 1
                    emit_event(
                        "batch_extract_progress",
                        {
                            "series_id": series_id,
                            "current": file_idx + 1,
                            "total": total_files,
                            "filename": fname,
                            "status": "skipped",
                        },
                    )
                    continue

                try:
                    probe = get_media_streams(video_path)
                except Exception as exc:
                    logger.warning(
                        "[batch-extract-tracks] probe failed for %s: %s", video_path, exc
                    )
                    failed += 1
                    emit_event(
                        "batch_extract_progress",
                        {
                            "series_id": series_id,
                            "current": file_idx + 1,
                            "total": total_files,
                            "filename": fname,
                            "status": "failed",
                        },
                    )
                    continue

                tracks = _build_track_list(probe.get("streams", []))
                subtitle_tracks = [t for t in tracks if t["codec_type"] == "subtitle"]

                file_extracted = 0
                for track in subtitle_tracks:
                    lang = track["language"] or "und"
                    ext = _CODEC_EXT.get(track["codec"], "ass")
                    base, _ = os.path.splitext(video_path)
                    output_path = f"{base}.{lang}.{ext}"

                    if os.path.exists(output_path):
                        skipped += 1
                        continue

                    stream_info = {"sub_index": track["sub_index"], "format": ext}
                    try:
                        extract_subtitle_stream(video_path, stream_info, output_path)
                        logger.debug(
                            "[batch-extract-tracks] extracted %s (track %d)",
                            output_path,
                            track["index"],
                        )
                        succeeded += 1
                        file_extracted += 1
                    except Exception as exc:
                        logger.warning(
                            "[batch-extract-tracks] extract failed (%s track %d): %s",
                            video_path,
                            track["index"],
                            exc,
                        )
                        failed += 1

                emit_event(
                    "batch_extract_progress",
                    {
                        "series_id": series_id,
                        "current": file_idx + 1,
                        "total": total_files,
                        "filename": fname,
                        "status": "ok" if file_extracted > 0 else "skipped",
                    },
                )

            logger.info(
                "[batch-extract-tracks] series %d done — %d extracted, %d failed, %d skipped",
                series_id,
                succeeded,
                failed,
                skipped,
            )

            emit_event(
                "batch_extract_completed",
                {
                    "series_id": series_id,
                    "total": total_files,
                    "succeeded": succeeded,
                    "failed": failed,
                    "skipped": skipped,
                },
            )

            # Finalize the activity job
            if _job_id:
                try:
                    _final_status = "failed" if succeeded == 0 and failed > 0 else "completed"
                    _update_job(
                        _job_id,
                        _final_status,
                        result={
                            "stats": {
                                "succeeded": succeeded,
                                "failed": failed,
                                "skipped": skipped,
                                "total": total_files,
                            }
                        },
                    )
                except Exception:
                    logger.debug("[batch-extract-tracks] could not finalize activity job")

            # Auto-cleanup: remove extra-language sidecars if configured
            from config import get_settings as _get_settings

            _settings = _get_settings()
            if getattr(_settings, "auto_cleanup_after_extract", False):
                _keep_raw = getattr(_settings, "auto_cleanup_keep_languages", "").strip()
                if _keep_raw:
                    _keep_langs = {l.strip() for l in _keep_raw.split(",") if l.strip()}
                    _keep_fmt = getattr(_settings, "auto_cleanup_keep_formats", "any").lower()
                    _cleaned = _cleanup_series_sidecars(episode_files, _keep_langs, _keep_fmt)
                    logger.info(
                        "[batch-extract-tracks] auto-cleanup: removed %d sidecar(s)", _cleaned
                    )

    threading.Thread(target=_run, args=(app,), daemon=True).start()
    return jsonify({"status": "started", "series_id": series_id}), 202
