"""Manual subtitle upload endpoints for episodes and standalone movies."""

from __future__ import annotations

import os

from flask import jsonify, request

from config import map_path
from routes.subtitles import bp
from services.subtitle_upload import (
    MAX_UPLOAD_BYTES,
    UploadError,
    prepare_upload,
    save_manual_subtitle,
)

# Reject obviously-oversized requests before reading the body into memory.
_MAX_REQUEST_BYTES = MAX_UPLOAD_BYTES + 1024 * 1024  # subtitle cap + multipart overhead


def _modifier_from_form() -> str | None:
    if request.form.get("hi", "").lower() in ("1", "true", "yes", "on"):
        return "hi"
    if request.form.get("forced", "").lower() in ("1", "true", "yes", "on"):
        return "forced"
    mod = (request.form.get("modifier") or "").strip().lower()
    return mod or None


def _do_upload(video_path: str):
    # DoS guard: refuse an oversized request before reading its body.
    if request.content_length and request.content_length > _MAX_REQUEST_BYTES:
        return jsonify({"error": "Upload too large"}), 413

    upload = request.files.get("file")
    if upload is None or not upload.filename:
        return jsonify({"error": "No file provided"}), 400
    language = (request.form.get("language") or "").strip().lower()
    if not language:
        return jsonify({"error": "Missing 'language'"}), 400
    overwrite = request.form.get("overwrite", "").lower() in ("1", "true", "yes", "on")
    modifier = _modifier_from_form()

    try:
        from services.trash_locations import media_paths

        content, ext = prepare_upload(upload.filename, upload.read())
        saved = save_manual_subtitle(
            video_path, content, ext, language, modifier, overwrite, media_paths()
        )
    except UploadError as e:
        return jsonify({"error": e.message}), e.status

    return jsonify({"saved_path": saved, "language": language, "format": ext}), 201


@bp.route("/library/episodes/<int:ep_id>/subtitles/upload", methods=["POST"])
def upload_episode_subtitle(ep_id: int):
    from sonarr_client import get_sonarr_client

    client = get_sonarr_client()
    if client is None:
        return jsonify({"error": "Sonarr not configured"}), 503
    raw_path = client.get_episode_file_path(ep_id)
    if not raw_path:
        return jsonify({"error": "Episode has no video file"}), 404
    video_path = map_path(raw_path)
    if not os.path.exists(video_path):
        return jsonify({"error": "Video file not found"}), 404
    return _do_upload(video_path)


@bp.route("/library/movies/<int:movie_id>/subtitles/upload", methods=["POST"])
def upload_movie_subtitle(movie_id: int):
    from db.standalone import get_standalone_movies

    movie = get_standalone_movies(movie_id)
    if movie is None:
        return jsonify({"error": "Movie not found"}), 404
    file_path = (
        movie.get("file_path") if isinstance(movie, dict) else getattr(movie, "file_path", None)
    )
    if not file_path or not os.path.exists(file_path):
        return jsonify({"error": "Video file not found"}), 404
    return _do_upload(file_path)
