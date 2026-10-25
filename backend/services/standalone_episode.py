"""Resolve a standalone-mode episode to its ``wanted_items`` row (#226).

Standalone libraries have no Sonarr. The standalone series detail
(``routes/library/series.py``) hands the UI one of two episode ids:

* the ``wanted_items`` row id while the episode still misses a subtitle, or
* a negative synthetic id once every target language is satisfied (there is no
  row to point at). For those the UI also sends the episode's ``file_path``.

The episode search / interactive search / download-selected endpoints need a
wanted item, because they reuse the exact ``wanted_search`` functions the
Wanted page uses. This module finds that row, or creates it for a satisfied
episode from the standalone records (series title, SxxEyy from the filename,
target language from the default profile — the standalone scanner has no
per-series profile binding either).

A client-supplied ``file_path`` is only accepted when it resolves (symlinks and
``..`` included) to an existing video file inside a known standalone series
folder, so the endpoint cannot be used to create wanted rows for arbitrary
paths.
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


def _target_languages() -> list[str]:
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


def resolve_standalone_episode_file(episode_id: int, file_path: str | None = None) -> str | None:
    """Return the video path of a standalone episode without creating anything."""
    row = _standalone_wanted_row(episode_id)
    if row and row.get("file_path") and _same_file(row["file_path"], file_path):
        return row["file_path"]
    located = _locate_series_file(file_path or "")
    return located.file_path if located else None


def resolve_standalone_episode_wanted_id(episode_id: int, file_path: str | None = None) -> int:
    """Return the ``wanted_items`` id to search/download for a standalone episode.

    Order: the row with ``episode_id`` (when it belongs to a standalone series
    and, if given, matches ``file_path``); else the existing row for
    ``file_path``; else a new ``wanted`` row for the profile's first target
    language. Raises :class:`StandaloneEpisodeNotFoundError` when neither the id nor
    the path identify a standalone episode.
    """
    row = _standalone_wanted_row(episode_id)
    if row and _same_file(row.get("file_path") or "", file_path):
        return row["id"]

    located = _locate_series_file(file_path or "")
    if located is None:
        raise StandaloneEpisodeNotFoundError(f"Standalone episode {episode_id} not found")

    languages = _target_languages()
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
