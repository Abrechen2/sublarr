"""Resolve movie files consistently with the standalone/Radarr detail page."""

from __future__ import annotations

import os


def radarr_movie_video_path(movie: dict, client) -> str | None:
    """Use the video file, never Radarr's top-level movie directory."""
    from config import map_path

    movie_file = movie.get("movieFile") or {}
    raw_path = movie_file.get("path")
    file_id = movie.get("movieFileId")
    if not raw_path and file_id:
        raw_path = (client.get_movie_file(file_id) or {}).get("path")
    return map_path(raw_path) if raw_path else None


def _under_media_root(path: str) -> bool:
    from security_utils import is_safe_path
    from services.trash_locations import media_paths

    return any(is_safe_path(path, root) for root in media_paths() if root)


def resolve_movie_video_path(movie_id: int) -> str | None:
    from db.standalone import get_standalone_movies
    from radarr_client import get_radarr_client

    # Preserve the detail endpoint's standalone-first ID semantics.
    movie = get_standalone_movies(movie_id)
    if movie is not None:
        # Standalone paths come from our own scan of configured watched folders,
        # which need not lie under media_path — no root check here.
        path = (
            movie.get("file_path") if isinstance(movie, dict) else getattr(movie, "file_path", None)
        )
        return path if path and os.path.isfile(path) else None

    client = get_radarr_client()
    movie = client.get_movie_by_id(movie_id) if client else None
    path = radarr_movie_video_path(movie, client) if movie else None
    if not path or not os.path.isfile(path):
        return None
    # Radarr's path is external data and upload writes next to it: it must lie
    # under a configured media root, like every other file endpoint.
    return path if _under_media_root(path) else None
