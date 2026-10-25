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
movie, inside a watched folder — and, independently, inside ``media_path``
(``standalone_path_allowed``), so an owner folder that is itself a symlink
out of the media tree cannot vouch for its files.
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


def series_folder_allowed(folder_path: str | None) -> bool:
    """Whether a standalone series folder may be enumerated at all.

    The folder itself must resolve (symlinks and ``..``) inside
    ``media_path``: a folder symlinked out of the media tree is refused
    before anything below it is listed, parsed or inspected.
    """
    return bool(folder_path) and "\x00" not in folder_path and in_media_root(folder_path)


def enumerate_series_episode_files(folder_path: str) -> list[tuple[str, dict]]:
    """``(file_path, parsed)`` for every episode video under a series folder.

    Safe by construction: a folder outside ``media_path`` is never walked,
    and a file is only parsed after it passed ``standalone_path_allowed``
    (a file symlinked out of the folder or the media tree is left out).
    Extras (trailers/samples/...) are skipped. ``[]`` when the folder is
    refused, missing or unreachable.
    """
    from standalone.parser import is_video_file, parse_media_file
    from standalone.scanner import _is_extra_file

    if not series_folder_allowed(folder_path) or not os.path.isdir(folder_path):
        return []

    out: list[tuple[str, dict]] = []
    try:
        for root, _dirs, files in os.walk(folder_path):
            for filename in files:
                fp = os.path.join(root, filename)
                if not is_video_file(fp) or _is_extra_file(fp):
                    continue
                if not standalone_path_allowed(fp, folder_path):
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


def allowed_series_files(series: dict) -> list[tuple[str, dict]]:
    """The episode files of a standalone series row that may be used.

    The one enumerator for the series page, the bulk actions, the sidecar
    map and the health scans: the folder on disk, or - while it is
    unreachable - the ``wanted_items`` paths, each checked with
    ``standalone_path_allowed`` before it is returned. Nothing at all for a
    series whose folder resolves outside ``media_path``.
    """
    folder = series.get("folder_path") or ""
    if not series_folder_allowed(folder):
        if folder:
            logger.warning(
                "Standalone series %s: folder %s resolves outside the media folder - not listed",
                series.get("id"),
                folder,
            )
        return []
    files = enumerate_series_episode_files(folder)
    if files:
        return files
    return [(fp, {}) for fp in _wanted_paths(series["id"]) if standalone_path_allowed(fp, folder)]


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
    Paths that resolve outside the series folder or ``media_path`` (a
    symlink out of the media tree) are left out: the bulk actions using this
    list read, rewrite and trash files next to them.
    """
    from db.standalone import get_standalone_series

    series = get_standalone_series(series_id)
    if not series:
        return None
    return sorted(fp for fp, _ in allowed_series_files(series))


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
    files = allowed_series_files(series)
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


def in_media_root(path: str) -> bool:
    """True when ``path`` resolves (symlinks and ``..``) inside ``media_path``.

    ``media_path`` is resolved on its own, so a series folder or watched
    folder that is itself a symlink out of the media tree cannot vouch for
    the files under it. Without a ``media_path`` every path passes and the
    owner-folder check alone applies (behaviour before 1.18.0).
    """
    from config import get_settings
    from security_utils import is_safe_path

    media_path = getattr(get_settings(), "media_path", "") or ""
    if not media_path:
        return True
    return is_safe_path(path, media_path)


def standalone_path_allowed(path: str, owner_folder: str) -> bool:
    """The one containment check every standalone episode/movie path goes through.

    ``path`` must resolve inside ``owner_folder`` (the series folder, or a
    watched folder for a movie) **and** inside ``media_path``.
    """
    from security_utils import is_safe_path

    if not path or not owner_folder:
        return False
    return is_safe_path(path, owner_folder) and in_media_root(path)


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

    candidate = _usable_video(path)
    if candidate is None or not series_id:
        return None
    series = get_standalone_series(int(series_id))
    folder = (series or {}).get("folder_path") or ""
    if not standalone_path_allowed(candidate, folder):
        return None
    return candidate


def movie_path_in_watched_folder(path: str | None) -> str | None:
    """``path`` when it is a video file inside any watched folder."""
    from db.standalone import get_watched_folders

    candidate = _usable_video(path)
    if candidate is None:
        return None
    for folder in get_watched_folders(enabled_only=False) or []:
        if standalone_path_allowed(candidate, folder.get("path") or ""):
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


OUTSIDE_REASON = "standalone file lies outside its folder or the media folder"


def _standalone_roots(*, required: bool) -> list[str] | None:
    """Watched folders, then standalone series folders.

    ``None`` when they cannot be read and the row is not known to be
    standalone (no app context / database in a unit test, a transient DB
    error): an untagged row is then treated as before. For a standalone row
    the error propagates, so it is never used unchecked.
    """
    from db.standalone import get_standalone_series, get_watched_folders

    try:
        roots = [f.get("path") or "" for f in get_watched_folders(enabled_only=False) or []]
        if not required:
            roots += [s.get("folder_path") or "" for s in get_standalone_series() or []]
    except Exception:
        if required:
            raise
        logger.debug("standalone roots unreadable; untagged row not checked", exc_info=True)
        return None
    return [root for root in roots if root]


def _lexically_under(path: str, root: str) -> bool:
    """``path`` as written (no symlinks resolved) lies under ``root``."""
    if not path or not root:
        return False
    norm, base = os.path.normpath(path), os.path.normpath(root)
    return norm == base or norm.startswith(base.rstrip(os.sep) + os.sep)


def wanted_item_path_refusal(item: dict | None) -> str | None:
    """Why a standalone wanted row's file must not be used now, or ``None``.

    Checked before any preflight, probe, search, extraction or translation
    of a stored wanted row: its folder or file may have been swapped for a
    symlink out of the media tree since the scan. An episode must resolve
    inside its series folder, a movie inside a watched folder, and both
    inside ``media_path`` (``standalone_path_allowed``). Existence is not
    checked here; the pipeline reports a missing file as before.

    Sonarr/Radarr rows answer ``None``: their paths stay governed by the
    ``media_path`` checks at the call sites, unchanged.
    """
    if not item:
        return None
    path = item.get("file_path") or ""
    if item.get("standalone_series_id"):
        from db.standalone import get_standalone_series

        series = get_standalone_series(int(item["standalone_series_id"])) or {}
        allowed = standalone_path_allowed(path, series.get("folder_path") or "")
    elif (
        item.get("sonarr_series_id") or item.get("sonarr_episode_id") or item.get("radarr_movie_id")
    ):
        return None
    else:
        tagged = bool(item.get("standalone_movie_id")) or item.get("instance_name") == "standalone"
        roots = _standalone_roots(required=tagged)
        if roots is None:
            return None
        if tagged:
            allowed = any(standalone_path_allowed(path, root) for root in roots)
        else:
            # A row / job / queue task without ids may be a standalone file
            # when it lies (as written) under a watched folder or a standalone
            # series folder - or a Sonarr/Radarr file in the same tree. Only
            # the boundary both share is enforced: the resolved file must lie
            # inside media_path (what the arr paths are held to anyway).
            if not any(_lexically_under(path, root) for root in roots):
                return None
            allowed = in_media_root(path)
    if allowed:
        return None
    logger.warning("Wanted %s: %s (%s) - skipped, row kept", item.get("id"), OUTSIDE_REASON, path)
    return OUTSIDE_REASON
