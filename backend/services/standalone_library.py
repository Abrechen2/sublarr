"""Standalone library files: which episode files a series has, their stable
ids, and whether a recorded path may be used.

The series folder on disk is the source of truth for "which episodes exist";
``wanted_items`` only holds episodes still missing a subtitle. Every episode
file gets a ``standalone_episodes`` row whose negated id is the episode's API
id (docs/specs/standalone-ids.md).

Recorded paths are not trusted by themselves: the scanner follows directory
symlinks, and a file can be swapped for a symlink after the scan. A path is
only used when it is an existing video file that resolves (symlinks and
``..`` resolved) inside the folder of the series that owns it, or, for a
movie, inside a watched folder.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StandaloneEpisodeFile:
    """One episode file of a standalone series with its API id."""

    wire_id: int
    row_id: int
    series_id: int
    file_path: str
    season: int
    episode: int


def enumerate_series_episode_files(folder_path: str) -> list[tuple[str, dict]]:
    """``(file_path, parsed)`` for every episode video under a series folder.

    Extras (trailers/samples/…) are skipped. ``[]`` when the folder is
    missing or unreachable, so callers can fall back to ``wanted_items``.
    """
    from standalone.parser import is_video_file, parse_media_file
    from standalone.scanner import _is_extra_file

    if not folder_path or not os.path.isdir(folder_path):
        return []

    out: list[tuple[str, dict]] = []
    try:
        for root, _dirs, files in os.walk(folder_path):
            for filename in files:
                fp = os.path.join(root, filename)
                if not is_video_file(fp) or _is_extra_file(fp):
                    continue
                try:
                    parsed = parse_media_file(fp)
                except Exception:  # pragma: no cover - guessit hiccup on odd names
                    parsed = {}
                out.append((fp, parsed))
    except OSError as exc:
        logger.warning("Standalone episode enumeration failed for %s: %s", folder_path, exc)
        return []
    return out


def _wanted_paths(series_id: int) -> list[str]:
    from sqlalchemy import text

    from db import get_db

    rows = (
        get_db()
        .execute(
            text(
                "SELECT DISTINCT file_path FROM wanted_items"
                " WHERE standalone_series_id=:sid AND file_path != ''"
                " ORDER BY file_path"
            ),
            {"sid": series_id},
        )
        .fetchall()
    )
    return [r[0] for r in rows if r[0]]


def standalone_series_video_paths(series_id: int) -> list[str] | None:
    """Every episode video of a standalone series (row id), or None if unknown.

    Falls back to the ``wanted_items`` paths while the folder is unreachable.
    """
    from db.standalone import get_standalone_series

    series = get_standalone_series(series_id)
    if not series:
        return None
    paths = [fp for fp, _ in enumerate_series_episode_files(series.get("folder_path", ""))]
    if paths:
        return sorted(paths)
    return _wanted_paths(series_id)


def _numbers(parsed: dict | None) -> tuple[int | None, int | None]:
    if not parsed or parsed.get("episode") is None:
        return None, None
    season = parsed.get("season")
    return (int(season) if season is not None else None), int(parsed["episode"])


def ensure_episode_ids(series_id: int, files: list[tuple[str, dict]]) -> dict[str, int]:
    """Make sure every file has a ``standalone_episodes`` row; return path -> row id.

    Reads the series' rows once and only writes for new or changed files, so
    a series page view after the first one is a single SELECT.
    """
    from db.repositories.standalone_episodes import StandaloneEpisodeRepository

    repo = StandaloneEpisodeRepository()
    known = {r["file_path"]: r for r in repo.get_episodes_for_series(series_id)}
    out: dict[str, int] = {}
    for fp, parsed in files:
        if not fp or fp in out:
            continue
        season, episode = _numbers(parsed)
        row = known.get(fp)
        # No parse result (folder unreachable, wanted-row fallback) keeps the
        # numbers a row already has.
        if row is None or (parsed and (row["season"], row["episode"]) != (season, episode)):
            row = repo.upsert_episode(series_id, fp, season, episode)
        out[fp] = row["id"]
    return out


def series_episode_files(series_id: int) -> list[StandaloneEpisodeFile] | None:
    """Episode files of a standalone series (row id) with their ids; None if unknown."""
    from db.standalone import get_standalone_series
    from services.media_ids import standalone_key

    series = get_standalone_series(series_id)
    if not series:
        return None
    files = enumerate_series_episode_files(series.get("folder_path", ""))
    if not files:
        files = [(fp, {}) for fp in _wanted_paths(series_id)]
    ids = ensure_episode_ids(series_id, files)
    out = []
    for fp, parsed in files:
        season, episode = _numbers(parsed)
        out.append(
            StandaloneEpisodeFile(
                wire_id=standalone_key(ids[fp]),
                row_id=ids[fp],
                series_id=series_id,
                file_path=fp,
                season=season or 0,
                episode=episode or 0,
            )
        )
    out.sort(key=lambda e: (e.season, e.episode, e.file_path))
    return out


# ---------------------------------------------------------------------------
# Path checks
# ---------------------------------------------------------------------------


def _usable_video(path: str | None) -> str | None:
    from standalone.parser import is_video_file

    if not path or "\x00" in path or not os.path.isabs(path):
        return None
    candidate = os.path.normpath(path)
    if not os.path.isfile(candidate) or not is_video_file(candidate):
        return None
    return candidate


def episode_path_in_series(path: str | None, series_id: int | None) -> str | None:
    """``path`` when it is a video file inside the folder of standalone series ``series_id``."""
    from db.standalone import get_standalone_series
    from security_utils import is_safe_path

    candidate = _usable_video(path)
    if candidate is None or not series_id:
        return None
    series = get_standalone_series(int(series_id))
    folder = (series or {}).get("folder_path") or ""
    if not folder or not is_safe_path(candidate, folder):
        return None
    return candidate


def movie_path_in_watched_folder(path: str | None) -> str | None:
    """``path`` when it is a video file inside any watched folder."""
    from db.standalone import get_watched_folders
    from security_utils import is_safe_path

    candidate = _usable_video(path)
    if candidate is None:
        return None
    for folder in get_watched_folders(enabled_only=False) or []:
        root = folder.get("path") or ""
        if root and is_safe_path(candidate, root):
            return candidate
    return None


def episode_file_for_wire_id(wire_id: int) -> tuple[dict, str] | None:
    """``(episode row, usable path)`` for a negative episode id, else None."""
    from db.repositories.standalone_episodes import StandaloneEpisodeRepository
    from services.media_ids import standalone_id_from

    row_id = standalone_id_from(wire_id)
    if row_id is None:
        return None
    row = StandaloneEpisodeRepository().get_episode(row_id)
    if not row:
        return None
    path = episode_path_in_series(row["file_path"], row["standalone_series_id"])
    return (row, path) if path else None
