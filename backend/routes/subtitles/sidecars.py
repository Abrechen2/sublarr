"""Sidecar-discovery endpoints: list subtitles next to episode/movie/series."""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from flask import jsonify

from config import map_path
from routes.subtitles import bp
from routes.subtitles.helpers import scan_subtitle_sidecars

logger = logging.getLogger(__name__)


@bp.route("/library/episodes/<int:ep_id>/subtitles", methods=["GET"])
def list_episode_subtitles(ep_id: int):
    """Return all subtitle sidecar files found next to this episode's video file."""
    from sonarr_client import get_sonarr_client

    client = get_sonarr_client()
    if client is None:
        return jsonify({"error": "Sonarr not configured"}), 503

    raw_path = client.get_episode_file_path(ep_id)
    if not raw_path:
        return jsonify({"error": "Episode has no video file"}), 404

    video_path = map_path(raw_path)
    if not os.path.exists(video_path):
        return jsonify({"error": "Video file not found: " + video_path}), 404

    sidecars = scan_subtitle_sidecars(video_path)
    return jsonify({"subtitles": sidecars, "video_path": video_path}), 200


@bp.route("/library/movies/<int:movie_id>/subtitles", methods=["GET"])
def list_movie_subtitles(movie_id: int):
    """Return all subtitle sidecar files found next to this standalone movie's video file."""
    from db.standalone import get_standalone_movies

    movie = get_standalone_movies(movie_id)
    if movie is None:
        return jsonify({"error": "Movie not found"}), 404

    file_path = (
        movie.get("file_path") if isinstance(movie, dict) else getattr(movie, "file_path", None)
    )
    if not file_path:
        return jsonify({"error": "Movie has no video file"}), 404

    if not os.path.exists(file_path):
        return jsonify({"error": f"Video file not found: {file_path}"}), 404

    sidecars = scan_subtitle_sidecars(file_path)
    return jsonify({"subtitles": sidecars, "video_path": file_path}), 200


@bp.route("/library/series/<int:series_id>/subtitles", methods=["GET"])
def list_series_subtitles(series_id: int):
    """Return all subtitle sidecar files for every episode in a series.

    Uses a single Sonarr call to get all episode file paths, then scans in parallel.
    Response: { subtitles: { "<sonarr_ep_id>": [SidecarSubtitle, ...] } }
    """
    from sonarr_client import get_sonarr_client

    client = get_sonarr_client()
    if client is None:
        # Standalone fallback: scan wanted_items for this series
        from sqlalchemy import text

        from db import get_db
        from db.standalone import get_standalone_series

        if get_standalone_series(series_id) is None:
            return jsonify({"error": "Sonarr not configured"}), 503

        db = get_db()
        rows = db.execute(
            text("SELECT id, file_path FROM wanted_items WHERE standalone_series_id=:sid"),
            {"sid": series_id},
        ).fetchall()
        result: dict[str, list[dict]] = {}
        for row in rows:
            sidecars = scan_subtitle_sidecars(row.file_path)
            if sidecars:
                result[str(row.id)] = sidecars
        return jsonify({"subtitles": result})

    episode_files = client.get_episode_files_by_series(series_id)
    if not episode_files:
        return jsonify({"subtitles": {}}), 200

    # Build file_id -> sonarr_episode_id map so results are keyed by episode ID
    # (frontend uses ep.id = Sonarr episode ID, not episode file ID)
    episodes_raw = client.get_episodes(series_id) or []
    file_id_to_ep_id: dict[int, int] = {
        ep["episodeFileId"]: ep["id"]
        for ep in episodes_raw
        if ep.get("hasFile") and ep.get("episodeFileId") and ep.get("id")
    }

    result: dict[str, list[dict]] = {}

    def _scan_one(file_id: int, file_info: dict):
        raw_path = file_info.get("path")
        if not raw_path:
            return file_id, []
        video_path = map_path(raw_path)
        if not os.path.exists(video_path):
            return file_id, []
        return file_id, scan_subtitle_sidecars(video_path)

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {
            pool.submit(_scan_one, file_id, file_info): file_id
            for file_id, file_info in episode_files.items()
        }
        for future in as_completed(futures):
            try:
                file_id, sidecars = future.result()
                if sidecars:
                    ep_id = file_id_to_ep_id.get(file_id, file_id)
                    result[str(ep_id)] = sidecars
            except Exception as exc:
                logger.warning("Error scanning sidecars for file %s: %s", futures[future], exc)

    return jsonify({"subtitles": result}), 200
