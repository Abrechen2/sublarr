"""Tracks routes."""

import logging
import os
import re
import tempfile

from flask import Blueprint, current_app, jsonify, request

from ass_utils import extract_subtitle_stream, get_media_streams
from config import map_path
from events import emit_event
from remux import RemuxError, remove_subtitle_streams
from services.background_tasks import submit_background

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

# ISO 639 language tag — 2/3 letter primary, optional region/script subtag
# (e.g. "de", "eng", "pt-BR", "zh-Hant"). Anything outside this shape is
# rejected to prevent path-traversal via crafted language strings (the
# language is interpolated into the sidecar output path).
_LANG_RE = re.compile(r"^[a-zA-Z]{2,3}(-[A-Za-z]{2,4})?$")
_LANG_FALLBACK = "und"


def _safe_language(raw: object) -> str:
    """Return raw if it matches ISO-639 shape, else 'und'.

    Defends against attacker-controlled values like '../../etc/passwd'
    being baked into output_path = base + '.' + language + '.' + ext.
    """
    if not raw or not isinstance(raw, str):
        return _LANG_FALLBACK
    raw = raw.strip()
    if not raw or not _LANG_RE.match(raw):
        return _LANG_FALLBACK
    return raw


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
        logger.warning("Video file not found on disk: %s", video_path)
        return jsonify({"error": "Video file not found on disk"}), 404
    try:
        probe = get_media_streams(video_path)
    except RuntimeError as exc:
        logger.exception("Stream probe failed for ep %d (%s): %s", ep_id, video_path, exc)
        return jsonify({"error": "Failed to probe video file"}), 500
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
        logger.warning("Video file not found on disk: %s", video_path)
        return jsonify({"error": "Video file not found on disk"}), 404
    try:
        probe = get_media_streams(video_path)
    except RuntimeError as exc:
        logger.exception("Failed to probe video file: %s", exc)
        return jsonify({"error": "Failed to probe video file"}), 500
    except Exception:
        return jsonify({"error": "Internal server error"}), 500
    tracks = _build_track_list(probe.get("streams", []))
    track = _find_track(tracks, index)
    if track is None:
        return jsonify({"error": "Track index " + str(index) + " not found"}), 404
    if track["codec_type"] != "subtitle":
        return jsonify({"error": "Only subtitle tracks can be extracted"}), 400
    language = _safe_language(body.get("language") or track["language"])
    ext = _CODEC_EXT.get(track["codec"], "ass")
    base, _ = os.path.splitext(video_path)
    output_path = base + "." + language + "." + ext
    # Defence-in-depth: even with the language regex, ensure the resolved
    # output path stays inside the same directory as the source video. This
    # also catches a video_path that itself escapes media_path via symlink.
    if os.path.realpath(os.path.dirname(output_path)) != os.path.realpath(
        os.path.dirname(video_path)
    ):
        return jsonify({"error": "Output path resolved outside video directory"}), 403
    stream_info = {"sub_index": track["sub_index"], "format": ext}
    try:
        extract_subtitle_stream(video_path, stream_info, output_path)
    except RuntimeError as exc:
        logger.exception("Extraction failed: %s", exc)
        return jsonify({"error": "Extraction failed"}), 500
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
        logger.warning("Video file not found on disk: %s", video_path)
        return jsonify({"error": "Video file not found on disk"}), 404
    try:
        probe = get_media_streams(video_path)
    except RuntimeError as exc:
        logger.exception("Failed to probe video file: %s", exc)
        return jsonify({"error": "Failed to probe video file"}), 500
    except Exception:
        return jsonify({"error": "Internal server error"}), 500
    tracks = _build_track_list(probe.get("streams", []))
    track = _find_track(tracks, index)
    if track is None:
        return jsonify({"error": "Track index " + str(index) + " not found"}), 404
    if track["codec_type"] != "subtitle":
        return jsonify({"error": "Only subtitle tracks can be used as source"}), 400
    ext = _CODEC_EXT.get(track["codec"], "ass")
    language = _safe_language(track["language"])
    stream_info = {"sub_index": track["sub_index"], "format": ext}
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(suffix="." + ext)
        os.close(fd)
        extract_subtitle_stream(video_path, stream_info, tmp_path)
        with open(tmp_path, encoding="utf-8", errors="replace") as fh:
            content = fh.read()
    except RuntimeError as exc:
        logger.exception("Extraction failed: %s", exc)
        return jsonify({"error": "Extraction failed"}), 500
    except OSError as exc:
        logger.exception("File I/O error: %s", exc)
        return jsonify({"error": "File I/O error"}), 500
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


@bp.route("/library/episodes/<int:ep_id>/dubtitle/detect", methods=["POST"])
def detect_episode_dubtitle(ep_id):
    """Identify the dubtitle among the file's embedded English subtitle tracks.

    Read-only: extracts streams to tempfiles and samples audio, never writes
    to the library. Tier-1 (heuristics) always runs; Tier-2 (Whisper audio
    match) runs only when several full-text English tracks remain ambiguous
    and ``run_tier2`` is true. The response suggests a dubtitle but applies
    nothing — extract/strip/set-default stay explicit user actions.
    """
    from services.dubtitle import detect_dubtitle, result_to_dict, store_detection

    body = request.get_json(silent=True) or {}
    run_tier2 = bool(body.get("run_tier2", True))
    min_score = body.get("min_score")
    if min_score is not None:
        try:
            min_score = float(min_score)
        except (TypeError, ValueError):
            return jsonify({"error": "min_score must be a number"}), 400

    video_path = _get_video_path(ep_id)
    if not video_path:
        return jsonify({"error": "Episode has no video file or Sonarr is not configured"}), 404
    if not os.path.exists(video_path):
        logger.warning("Video file not found on disk: %s", video_path)
        return jsonify({"error": "Video file not found on disk"}), 404

    try:
        result = detect_dubtitle(video_path, min_score=min_score, run_tier2=run_tier2)
    except Exception:
        logger.exception("Dubtitle detection failed for ep %d", ep_id)
        return jsonify({"error": "Dubtitle detection failed"}), 500

    payload = result_to_dict(result)
    # Persist so the UI can re-render the flag without re-detecting, and a
    # later sweep skips this file at the same mtime.
    store_detection(video_path, payload)
    return jsonify({"video_path": video_path, "cached": False, **payload}), 200


@bp.route("/library/episodes/<int:ep_id>/dubtitle", methods=["GET"])
def get_episode_dubtitle(ep_id):
    """Return the cached dubtitle-detection result for an episode, if any.

    Lets the track panel show the dubtitle flag on load without re-running
    detection. 200 with the cached payload when present (and still fresh for
    the file's mtime), 204 when nothing has been detected/cached yet.
    """
    from services.dubtitle import get_cached_detection

    video_path = _get_video_path(ep_id)
    if not video_path:
        return jsonify({"error": "Episode has no video file or Sonarr is not configured"}), 404
    cached = get_cached_detection(video_path)
    if cached is None:
        return "", 204
    return jsonify({"video_path": video_path, "cached": True, **cached}), 200


@bp.route("/library/episodes/<int:ep_id>/health/scan", methods=["POST"])
def scan_episode_health(ep_id):
    """Read-only subtitle-health scan for one episode.

    Inspects embedded subtitle tracks (raw, via -c:s copy) and sidecar files,
    runs the registered checkers, and returns the findings. Writes nothing.
    """
    from routes.subtitles import scan_subtitle_sidecars
    from services.subtitle_health import scan_episode

    video_path = _get_video_path(ep_id)
    if not video_path:
        return jsonify({"error": "Episode has no video file or Sonarr is not configured"}), 404
    if not os.path.exists(video_path):
        return jsonify({"error": "Video file not found on disk"}), 404

    sidecars = []
    try:
        for sc in scan_subtitle_sidecars(video_path):
            sidecars.append({"path": sc.get("path"), "lang": sc.get("language", "und")})
    except Exception:
        logger.warning("subtitle_health: sidecar scan failed for %s", video_path)

    try:
        result = scan_episode(episode_id=ep_id, video_path=video_path, sidecars=sidecars)
    except Exception:
        logger.exception("subtitle_health: scan failed for ep %d", ep_id)
        return jsonify({"error": "Subtitle health scan failed"}), 500

    return jsonify(result.to_dict()), 200


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

            # Collect video file paths — from Sonarr or standalone DB
            if client is not None:
                try:
                    episode_files = client.get_episode_files_by_series(series_id)
                except Exception as exc:
                    logger.error(
                        "[batch-extract-tracks] Sonarr error for series %d: %s", series_id, exc
                    )
                    emit_event(
                        "batch_extract_completed",
                        {
                            "series_id": series_id,
                            "total": 0,
                            "succeeded": 0,
                            "failed": 0,
                            "skipped": 0,
                        },
                    )
                    return
                video_paths = (
                    [
                        map_path(fi.get("path", ""))
                        for fi in episode_files.values()
                        if fi.get("path")
                    ]
                    if episode_files
                    else []
                )
            else:
                # Standalone fallback: read file paths directly from wanted_items table
                from sqlalchemy import text as _text

                from db import get_db

                db = get_db()
                rows = db.execute(
                    _text(
                        "SELECT DISTINCT file_path FROM wanted_items"
                        " WHERE standalone_series_id=:sid AND file_path != ''"
                        " ORDER BY file_path"
                    ),
                    {"sid": series_id},
                ).fetchall()
                video_paths = [r[0] for r in rows if r[0]]
                logger.info(
                    "[batch-extract-tracks] standalone mode: %d files for series %d",
                    len(video_paths),
                    series_id,
                )

            if not video_paths:
                logger.info("[batch-extract-tracks] no files found for series %d", series_id)
                emit_event(
                    "batch_extract_completed",
                    {"series_id": series_id, "total": 0, "succeeded": 0, "failed": 0, "skipped": 0},
                )
                return

            succeeded = 0
            failed = 0
            skipped = 0

            total_files = len(video_paths)

            # Create an activity job so the extraction is visible on the Activity page
            _job_id = None
            try:
                from db.jobs import create_job, update_job as _update_job  # noqa: I001

                _series_title = f"Serie {series_id}"
                try:
                    if client is not None:
                        _series_info = client.get_series_by_id(series_id)
                        if isinstance(_series_info, dict) and _series_info.get("title"):
                            _series_title = _series_info["title"]
                except Exception as exc:
                    logger.debug(
                        "Could not fetch series title for job display (series %s): %s",
                        series_id,
                        exc,
                    )

                _job = create_job(
                    f"batch-extract: {_series_title} ({total_files} Dateien)",
                )
                _job_id = _job["id"]
                _update_job(_job_id, "running")
            except Exception:
                logger.debug("[batch-extract-tracks] could not create activity job")

            for file_idx, video_path in enumerate(video_paths):
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
                extracted_streams: list[tuple[int, int]] = []  # (global_index, sub_index)
                for track in subtitle_tracks:
                    # MKV "language" tag is container-controlled; sanitise the
                    # same way as the single-track route to stop a crafted
                    # tag from steering the sidecar write outside the video
                    # directory.
                    lang = _safe_language(track["language"])
                    ext = _CODEC_EXT.get(track["codec"], "ass")
                    base, _ = os.path.splitext(video_path)
                    output_path = f"{base}.{lang}.{ext}"

                    if os.path.realpath(os.path.dirname(output_path)) != os.path.realpath(
                        os.path.dirname(video_path)
                    ):
                        logger.warning(
                            "[batch-extract-tracks] refusing to extract: %s lands outside %s",
                            output_path,
                            os.path.dirname(video_path),
                        )
                        skipped += 1
                        continue

                    if os.path.exists(output_path):
                        skipped += 1
                        continue

                    stream_info = {"sub_index": track["sub_index"], "format": ext}
                    try:
                        extract_subtitle_stream(video_path, stream_info, output_path)
                        sidecar_size = (
                            os.path.getsize(output_path) if os.path.exists(output_path) else 0
                        )
                        if sidecar_size < 10:
                            logger.warning(
                                "[batch-extract-tracks] sidecar %s is empty (%d bytes) — skipping removal for track %d",
                                output_path,
                                sidecar_size,
                                track["index"],
                            )
                            try:
                                os.unlink(output_path)
                            except OSError:
                                pass
                            failed += 1
                        else:
                            logger.debug(
                                "[batch-extract-tracks] extracted %s (%d bytes, track %d)",
                                output_path,
                                sidecar_size,
                                track["index"],
                            )
                            succeeded += 1
                            file_extracted += 1
                            extracted_streams.append((track["index"], track["sub_index"]))
                    except Exception as exc:
                        logger.warning(
                            "[batch-extract-tracks] extract failed (%s track %d): %s",
                            video_path,
                            track["index"],
                            exc,
                        )
                        failed += 1

                # Remove all successfully-extracted subtitle streams from the container
                if extracted_streams:
                    try:
                        bak = remove_subtitle_streams(video_path, extracted_streams)
                        logger.info(
                            "[batch-extract-tracks] removed %d stream(s) from %s (backup: %s)",
                            len(extracted_streams),
                            video_path,
                            bak,
                        )
                    except RemuxError as exc:
                        logger.warning(
                            "[batch-extract-tracks] could not remove streams from %s: %s",
                            video_path,
                            exc,
                        )

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
                    # _cleanup_series_sidecars expects {id: {path: ...}} — build from video_paths
                    _pseudo_files = {i: {"path": p} for i, p in enumerate(video_paths)}
                    _cleaned = _cleanup_series_sidecars(_pseudo_files, _keep_langs, _keep_fmt)
                    logger.info(
                        "[batch-extract-tracks] auto-cleanup: removed %d sidecar(s)", _cleaned
                    )

    submit_background(_run, app)
    return jsonify({"status": "started", "series_id": series_id}), 202
