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


def _standalone_movie_path(row_id: int) -> str | None:
    from db.standalone import get_standalone_movies
    from services.standalone_library import movie_path_in_watched_folder

    movie = get_standalone_movies(row_id)
    if movie is None:
        return None
    path = movie.get("file_path") if isinstance(movie, dict) else getattr(movie, "file_path", None)
    # Watched folders need not lie under media_path, but the file must still
    # resolve (symlinks included) inside one of them.
    return movie_path_in_watched_folder(path)


def resolve_movie_video_path(movie_id: int) -> str | None:
    """Video file of a movie id, same id rules as the movie detail.

    Negative: a standalone movie. Positive: Radarr's movie when Radarr is
    configured (falling back to a standalone row of that id when Radarr does
    not know it, as the detail does), else a legacy standalone row id.
    """
    from radarr_client import get_radarr_client
    from services.media_ids import standalone_id_from

    standalone_id = standalone_id_from(movie_id)
    if standalone_id is not None:
        return _standalone_movie_path(standalone_id)

    client = get_radarr_client()
    if client is None:
        return _standalone_movie_path(movie_id)
    movie = client.get_movie_by_id(movie_id)
    if not movie:
        return _standalone_movie_path(movie_id)
    path = radarr_movie_video_path(movie, client) if movie else None
    if not path or not os.path.isfile(path):
        return None
    # Radarr's path is external data and upload writes next to it: it must lie
    # under a configured media root, like every other file endpoint.
    return path if _under_media_root(path) else None
