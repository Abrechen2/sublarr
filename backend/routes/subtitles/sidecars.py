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


@bp.route("/library/episodes/<int(signed=True):ep_id>/subtitles", methods=["GET"])
def list_episode_subtitles(ep_id: int):
    """Return all subtitle sidecar files found next to this episode's video file."""
    # Sonarr or standalone (wanted_items row id) — same resolver the track,
    # combine and upload endpoints use; None covers "no file" and "not found".
    from services.episode_video_path import resolve_episode_video_path

    video_path = resolve_episode_video_path(ep_id)
    if not video_path:
        return jsonify({"error": "Episode video file not found"}), 404

    sidecars = scan_subtitle_sidecars(video_path)
    return jsonify({"subtitles": sidecars, "video_path": video_path}), 200


@bp.route("/library/movies/<int(signed=True):movie_id>/subtitles", methods=["GET"])
def list_movie_subtitles(movie_id: int):
    """Return sidecars for a standalone or Radarr movie's video file."""
    from services.movie_video_path import resolve_movie_video_path

    file_path = resolve_movie_video_path(movie_id)
    if not file_path:
        return jsonify({"error": "Movie video file not found"}), 404

    sidecars = scan_subtitle_sidecars(file_path)
    return jsonify({"subtitles": sidecars, "video_path": file_path}), 200


@bp.route("/library/series/<int(signed=True):series_id>/subtitles", methods=["GET"])
def list_series_subtitles(series_id: int):
    """Return all subtitle sidecar files for every episode in a series.

    Uses a single Sonarr call to get all episode file paths, then scans in parallel.
    Response: { subtitles: { "<sonarr_ep_id>": [SidecarSubtitle, ...] } }
    """
    from services.media_ids import resolve_series_ref
    from sonarr_client import get_sonarr_client

    ref = resolve_series_ref(series_id)
    if ref.is_standalone:
        # Every episode file of the folder, keyed by its stable episode id —
        # the id the series detail hands out (also for satisfied episodes,
        # which the old wanted_items-based map left out).
        from services.standalone_library import episode_path_in_series, series_episode_files

        files = series_episode_files(ref.id)
        if files is None:
            if series_id < 0:
                return jsonify({"error": "Series not found"}), 404
            return jsonify({"error": "Sonarr not configured"}), 503
        result: dict[str, list[dict]] = {}
        for ep in files:
            if episode_path_in_series(ep.file_path, ref.id) is None:
                continue  # resolves outside the series folder or media_path
            sidecars = scan_subtitle_sidecars(ep.file_path)
            if sidecars:
                result[str(ep.wire_id)] = sidecars
        return jsonify({"subtitles": result})

    client = get_sonarr_client()

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
