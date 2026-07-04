"""Combined/bilingual subtitle endpoints for episodes and standalone movies.

  POST /api/v1/library/episodes/<ep_id>/subtitles/combine
  POST /api/v1/library/movies/<movie_id>/subtitles/combine
  POST /api/v1/library/subtitles/combine-batch

Body: { languages: ["de","en"], format: "ass"|"srt", position?: {...},
        translate_missing?: bool }
"""

from __future__ import annotations

import os
import re

from flask import jsonify, request

from config import map_path
from routes.subtitles import bp
from services.subtitle_combine import CombineError

_LANGUAGE_RE = re.compile(r"^[a-z]{2,3}\Z")
_VALID_FORMATS = frozenset({"ass", "srt"})
_MAX_COMBINE_LANGUAGES = 3
_MAX_BATCH_ITEMS = 500


class _CombineRequest:
    """Validated combine request body."""

    def __init__(self, languages: list[str], fmt: str, position: dict | None, translate: bool):
        self.languages = languages
        self.format = fmt
        self.position = position
        self.translate_missing = translate


def _parse_combine_body(data: dict) -> _CombineRequest:
    """Validate a combine request body. Raises CombineError(400) on bad input."""
    languages = data.get("languages") or []
    if not isinstance(languages, list) or not (2 <= len(languages) <= _MAX_COMBINE_LANGUAGES):
        raise CombineError(400, "languages must be a list of 2–3 language codes")
    languages = [str(lang).strip().lower() for lang in languages]
    if any(not _LANGUAGE_RE.match(lang) for lang in languages):
        raise CombineError(400, "languages must be 2–3 letter language codes")
    if len(set(languages)) != len(languages):
        raise CombineError(400, "languages must be unique")

    fmt = (data.get("format") or "ass").strip().lower()
    if fmt not in _VALID_FORMATS:
        raise CombineError(400, "format must be 'ass' or 'srt'")

    position = data.get("position")
    if position is not None and not isinstance(position, dict):
        raise CombineError(400, "position must be an object")

    return _CombineRequest(languages, fmt, position, bool(data.get("translate_missing")))


def _do_combine(video_path: str):
    from services.combine_service import combine_for_video
    from services.trash_locations import media_paths

    try:
        req = _parse_combine_body(request.get_json(silent=True) or {})
        result = combine_for_video(
            video_path,
            req.languages,
            req.format,
            req.position,
            media_paths(),
            translate_missing=req.translate_missing,
        )
    except CombineError as exc:
        return jsonify({"error": exc.message}), exc.status

    return jsonify(result), 201


def _episode_video_path(ep_id: int) -> tuple[str | None, tuple]:
    """Resolve an episode's on-disk video path. Returns (path, error_response)."""
    from sonarr_client import get_sonarr_client

    client = get_sonarr_client()
    if client is None:
        return None, (jsonify({"error": "Sonarr not configured"}), 503)
    raw_path = client.get_episode_file_path(ep_id)
    if not raw_path:
        return None, (jsonify({"error": "Episode has no video file"}), 404)
    video_path = map_path(raw_path)
    if not os.path.exists(video_path):
        return None, (jsonify({"error": "Video file not found"}), 404)
    return video_path, ()


def _movie_video_path(movie_id: int) -> tuple[str | None, tuple]:
    """Resolve a standalone movie's on-disk video path. Returns (path, error_response)."""
    from db.standalone import get_standalone_movies

    movie = get_standalone_movies(movie_id)
    if movie is None:
        return None, (jsonify({"error": "Movie not found"}), 404)
    file_path = (
        movie.get("file_path") if isinstance(movie, dict) else getattr(movie, "file_path", None)
    )
    if not file_path or not os.path.exists(file_path):
        return None, (jsonify({"error": "Video file not found"}), 404)
    return file_path, ()


@bp.route("/library/episodes/<int:ep_id>/subtitles/combine", methods=["POST"])
def combine_episode_subtitles(ep_id: int):
    video_path, err = _episode_video_path(ep_id)
    if video_path is None:
        return err
    return _do_combine(video_path)


@bp.route("/library/movies/<int:movie_id>/subtitles/combine", methods=["POST"])
def combine_movie_subtitles(movie_id: int):
    video_path, err = _movie_video_path(movie_id)
    if video_path is None:
        return err
    return _do_combine(video_path)


@bp.route("/library/subtitles/combine-batch", methods=["POST"])
def combine_batch():
    """Mass-combine across explicit episode/movie ids for list pages.

    Body adds ``episode_ids`` / ``movie_ids`` to the combine body. Each item is
    combined independently; a missing language for one item is reported as
    ``skipped`` (not a hard failure of the whole batch).
    """
    from services.combine_service import combine_for_video
    from services.trash_locations import media_paths

    data = request.get_json(silent=True) or {}
    episode_ids = data.get("episode_ids") or []
    movie_ids = data.get("movie_ids") or []
    if not isinstance(episode_ids, list) or not isinstance(movie_ids, list):
        return jsonify({"error": "episode_ids and movie_ids must be lists"}), 400
    if len(episode_ids) + len(movie_ids) > _MAX_BATCH_ITEMS:
        return jsonify({"error": f"Maximum {_MAX_BATCH_ITEMS} items per batch"}), 400

    try:
        req = _parse_combine_body(data)
    except CombineError as exc:
        return jsonify({"error": exc.message}), exc.status

    roots = media_paths()
    results: list[dict] = []

    def _run(item_type: str, item_id: int, resolver):
        video_path, _err = resolver(item_id)
        if video_path is None:
            results.append(
                {"type": item_type, "id": item_id, "status": "failed", "error": "video not found"}
            )
            return
        try:
            out = combine_for_video(
                video_path,
                req.languages,
                req.format,
                req.position,
                roots,
                translate_missing=req.translate_missing,
            )
            results.append(
                {
                    "type": item_type,
                    "id": item_id,
                    "status": "combined",
                    "combined_path": out["combined_path"],
                }
            )
        except CombineError as exc:
            status = "skipped" if exc.status == 422 else "failed"
            results.append(
                {"type": item_type, "id": item_id, "status": status, "error": exc.message}
            )

    for ep_id in episode_ids:
        _run("episode", ep_id, _episode_video_path)
    for movie_id in movie_ids:
        _run("movie", movie_id, _movie_video_path)

    summary = {"combined": 0, "skipped": 0, "failed": 0}
    for r in results:
        summary[r["status"]] = summary.get(r["status"], 0) + 1
    return jsonify({"results": results, **summary})
