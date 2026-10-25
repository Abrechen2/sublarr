"""Resolve a standalone-mode episode id to its file and ``wanted_items`` row.

Since 1.18.0 a standalone episode's API id is ``-standalone_episodes.id``
(stable, see docs/specs/standalone-ids.md). Older ids still resolve:

* a positive id without Sonarr is a standalone ``wanted_items`` row id
  (<= 1.17.2 clients);
* the 1.17.3 stand-in ``-(index + 1)`` comes with the episode's
  ``file_path``; when the id's row does not name that file, the path decides.

The episode search / interactive search / download-selected endpoints need a
wanted item, because they reuse the exact ``wanted_search`` functions the
Wanted page uses. This module finds that row, or creates it for a satisfied
episode from the standalone records (series title, SxxEyy from the filename,
first target language of the series' profile).

No path is used unless it is an existing video file that resolves (symlinks
and ``..`` included) inside the folder of the standalone series that owns it
(``services.standalone_library``), whether it came from our own records or
from the client's ``file_path``.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class StandaloneEpisodeNotFoundError(LookupError):
    """The id/file_path pair does not identify a standalone episode."""


@dataclass(frozen=True)
class _SeriesFile:
    series_id: int
    series_title: str
    file_path: str


def _standalone_wanted_row(episode_id: int) -> dict | None:
    """Return the standalone episode wanted row with this id, else ``None``."""
    if episode_id <= 0:
        return None
    from db.wanted import get_wanted_item

    row = get_wanted_item(episode_id)
    if not row or not row.get("standalone_series_id") or row.get("item_type") != "episode":
        return None
    return row


def _same_file(row_path: str, file_path: str | None) -> bool:
    """True when no ``file_path`` was sent, or it names the row's file."""
    return not file_path or os.path.normpath(row_path) == os.path.normpath(file_path)


def _locate_series_file(file_path: str) -> _SeriesFile | None:
    """Validate ``file_path`` and find the standalone series that owns it.

    The path must be absolute, contain no NUL, be an existing video file and
    resolve (``security_utils.is_safe_path``: symlinks and ``..`` resolved)
    inside a standalone series folder. The deepest matching folder wins.
    """
    from db.standalone import get_standalone_series
    from security_utils import is_safe_path
    from standalone.parser import is_video_file

    if not file_path or "\x00" in file_path or not os.path.isabs(file_path):
        return None
    candidate = os.path.normpath(file_path)
    if not os.path.isfile(candidate) or not is_video_file(candidate):
        return None

    best: _SeriesFile | None = None
    best_len = -1
    for series in get_standalone_series() or []:
        series_dir = series.get("folder_path") or ""
        if not series_dir or len(series_dir) <= best_len:
            continue
        if is_safe_path(candidate, series_dir):
            best_len = len(series_dir)
            best = _SeriesFile(
                series_id=series["id"],
                series_title=series.get("title") or "",
                file_path=candidate,
            )
    return best


def _target_languages(series_id: int) -> list[str]:
    from config import get_settings
    from db.profiles import get_default_profile

    settings = get_settings()
    profile = get_default_profile()
    langs = (profile or {}).get("target_languages") or []
    return list(langs) or [settings.target_language]


def _existing_row_for_file(file_path: str, languages: list[str]) -> dict | None:
    """Pick the file's standalone wanted row, preferring profile language order."""
    from sqlalchemy import text

    from extensions import db

    rows = db.session.execute(
        text(
            "SELECT id, target_language FROM wanted_items "
            "WHERE file_path = :fp AND standalone_series_id IS NOT NULL "
            "AND item_type = 'episode' ORDER BY id"
        ),
        {"fp": file_path},
    ).fetchall()
    if not rows:
        return None
    order = {lang: i for i, lang in enumerate(languages)}
    best = min(rows, key=lambda r: order.get(r[1] or "", len(order)))
    return {"id": best[0], "target_language": best[1]}


def _season_episode(file_path: str) -> str:
    from standalone.parser import parse_media_file

    try:
        parsed = parse_media_file(file_path)
    except Exception:  # pragma: no cover - guessit hiccup on odd names
        return ""
    season, episode = parsed.get("season"), parsed.get("episode")
    if season is not None and episode is not None:
        return f"S{int(season):02d}E{int(episode):02d}"
    if episode is not None:
        return f"E{int(episode):02d}"
    return ""


def _identity(episode_id: int, file_path: str | None) -> tuple[_SeriesFile, int | None] | None:
    """``(series file, legacy wanted row id or None)`` for an episode id/path pair."""
    from db.standalone import get_standalone_series
    from services.standalone_library import episode_file_for_wire_id, episode_path_in_series

    if episode_id < 0:
        hit = episode_file_for_wire_id(episode_id)
        if hit is not None and _same_file(hit[1], file_path):
            row, path = hit
            series = get_standalone_series(row["standalone_series_id"]) or {}
            return (
                _SeriesFile(
                    series_id=row["standalone_series_id"],
                    series_title=series.get("title") or "",
                    file_path=path,
                ),
                None,
            )
    else:
        row = _standalone_wanted_row(episode_id)
        if row and _same_file(row.get("file_path") or "", file_path):
            path = episode_path_in_series(row.get("file_path"), row["standalone_series_id"])
            if path:
                series = get_standalone_series(row["standalone_series_id"]) or {}
                return (
                    _SeriesFile(
                        series_id=row["standalone_series_id"],
                        series_title=series.get("title") or "",
                        file_path=path,
                    ),
                    row["id"],
                )

    located = _locate_series_file(file_path or "")
    return (located, None) if located else None


def resolve_standalone_episode_file(episode_id: int, file_path: str | None = None) -> str | None:
    """Return the video path of a standalone episode without creating anything."""
    found = _identity(episode_id, file_path)
    return found[0].file_path if found else None


def resolve_standalone_episode_wanted_id(episode_id: int, file_path: str | None = None) -> int:
    """Return the ``wanted_items`` id to search/download for a standalone episode.

    Order: the legacy wanted row ``episode_id`` names (positive id, matching
    ``file_path`` if given); else the existing row for the episode's file;
    else a new ``wanted`` row for the series profile's first target language.
    Raises :class:`StandaloneEpisodeNotFoundError` when neither the id nor the
    path identify a standalone episode.
    """
    found = _identity(episode_id, file_path)
    if found is None:
        raise StandaloneEpisodeNotFoundError(f"Standalone episode {episode_id} not found")
    located, legacy_row_id = found
    if legacy_row_id is not None:
        return legacy_row_id

    languages = _target_languages(located.series_id)
    existing = _existing_row_for_file(located.file_path, languages)
    if existing:
        return existing["id"]

    from db.wanted import upsert_wanted_item

    season_episode = _season_episode(located.file_path)
    title = located.series_title
    if season_episode:
        title = f"{title} -- {season_episode}"
    item_id, _ = upsert_wanted_item(
        item_type="episode",
        file_path=located.file_path,
        title=title,
        season_episode=season_episode,
        missing_languages=[languages[0]],
        target_language=languages[0],
        instance_name="standalone",
        standalone_series_id=located.series_id,
    )
    logger.info(
        "Created standalone wanted item %s for %s (series %s, %s)",
        item_id,
        located.file_path,
        located.series_id,
        languages[0],
    )
    return item_id
