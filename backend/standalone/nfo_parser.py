"""NFO metadata parser for standalone mode.

Reads Kodi/Emby/Jellyfin-style NFO sidecar files (tvshow.nfo, movie.nfo)
from media folders and extracts structured metadata.

Priority chain in scanner:
  1. NFO file (local, complete, offline)
  2. MetadataResolver (online API) — only for fields missing from NFO
  3. Filename parsing (fallback)
"""

import logging
import os
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

# Genres that indicate anime content
_ANIME_GENRES = {"anime", "animation (japan)", "japanimation"}

# NFO filenames checked in order
_SERIES_NFO_NAMES = ("tvshow.nfo",)
_MOVIE_NFO_NAMES = ("movie.nfo",)

# Poster filenames checked in order (prefer poster.jpg)
_POSTER_NAMES = ("poster.jpg", "poster.png", "folder.jpg", "folder.png", "thumb.jpg")


def _find_file(folder: str, candidates: tuple) -> str | None:
    """Return first existing file path from candidates, or None."""
    for name in candidates:
        path = os.path.join(folder, name)
        if os.path.isfile(path):
            return path
    return None


def _text(element, tag: str, default=None):
    """Extract text from a child tag, stripping whitespace."""
    child = element.find(tag)
    if child is not None and child.text:
        return child.text.strip()
    return default


def _int_or_none(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _parse_genres(root) -> list[str]:
    """Extract all genre strings from the NFO."""
    return [g.text.strip() for g in root.findall("genre") if g.text]


def _is_anime_from_genres(genres: list[str]) -> bool:
    """Return True if any genre indicates anime."""
    lower = {g.lower() for g in genres}
    return bool(lower & _ANIME_GENRES)


def _parse_unique_ids(root) -> dict:
    """Extract <uniqueid type="x"> entries into a dict."""
    ids: dict = {}
    for uid in root.findall("uniqueid"):
        id_type = uid.get("type", "").lower()
        if uid.text and id_type:
            ids[id_type] = uid.text.strip()
    return ids


def parse_series_nfo(folder_path: str) -> dict | None:
    """Parse tvshow.nfo from a series folder.

    Searches folder_path first, then its parent (handles the common case
    where episodes live in Season subfolders but NFO is in the series root).

    Args:
        folder_path: Path to the common parent of episode files (may be a
            Season subfolder).

    Returns:
        Dict with metadata keys, or None if no NFO found / parse error.
        Keys: title, year, tvdb_id, tmdb_id, imdb_id, anilist_id,
              is_anime, status, metadata_source, local_poster
    """
    # Try current folder, then parent (Season subfolder → series root)
    nfo_path = _find_file(folder_path, _SERIES_NFO_NAMES)
    nfo_folder = folder_path
    if nfo_path is None:
        parent = os.path.dirname(folder_path)
        if parent != folder_path:
            nfo_path = _find_file(parent, _SERIES_NFO_NAMES)
            nfo_folder = parent
    if nfo_path is None:
        return None

    try:
        tree = ET.parse(nfo_path)
        root = tree.getroot()

        # Some NFOs use <tvshow> as root, others are bare
        if root.tag != "tvshow":
            root = root.find("tvshow") or root

        genres = _parse_genres(root)
        unique_ids = _parse_unique_ids(root)

        # IDs — prefer <tvdbid>/<tmdbid> tags, fall back to <uniqueid type="...">
        tvdb_id = _int_or_none(_text(root, "tvdbid") or unique_ids.get("tvdb"))
        tmdb_id = _int_or_none(_text(root, "tmdbid") or unique_ids.get("tmdb"))
        imdb_id = _text(root, "imdb_id") or unique_ids.get("imdb")

        # AniDB ID (present in some anime NFOs)
        anidb_raw = unique_ids.get("anidb") or _text(root, "anidbid")
        anidb_id = _int_or_none(anidb_raw)

        year_raw = _text(root, "year") or _text(root, "premiered", "")[:4] or None
        year = _int_or_none(year_raw)

        status_raw = _text(root, "status", "")
        status = status_raw.lower() if status_raw else None

        is_anime = _is_anime_from_genres(genres) or anidb_id is not None

        # Poster lives in the same folder as the NFO (series root, not Season subfolder)
        local_poster = _find_file(nfo_folder, _POSTER_NAMES)

        result = {
            "title": _text(root, "title") or _text(root, "sorttitle"),
            "year": year,
            "tvdb_id": tvdb_id,
            "tmdb_id": tmdb_id,
            "imdb_id": imdb_id or "",
            "anilist_id": None,  # NFO does not carry AniList ID
            "is_anime": is_anime,
            "status": status,
            "metadata_source": "nfo",
            "local_poster": local_poster,
        }

        logger.debug(
            "NFO parsed for %s: title=%r year=%s tvdb=%s tmdb=%s anime=%s",
            folder_path,
            result["title"],
            year,
            tvdb_id,
            tmdb_id,
            is_anime,
        )
        return result

    except ET.ParseError as e:
        logger.warning("Failed to parse NFO at %s: %s", nfo_path, e)
        return None
    except Exception as e:
        logger.warning("Unexpected error reading NFO at %s: %s", nfo_path, e)
        return None


def parse_movie_nfo(folder_path: str) -> dict | None:
    """Parse movie.nfo from a movie folder.

    Args:
        folder_path: Path to the movie root folder.

    Returns:
        Dict with metadata keys, or None if no NFO found / parse error.
        Keys: title, year, tmdb_id, imdb_id, metadata_source, local_poster
    """
    nfo_path = _find_file(folder_path, _MOVIE_NFO_NAMES)
    if nfo_path is None:
        return None

    try:
        tree = ET.parse(nfo_path)
        root = tree.getroot()

        if root.tag != "movie":
            root = root.find("movie") or root

        unique_ids = _parse_unique_ids(root)

        tmdb_id = _int_or_none(_text(root, "tmdbid") or unique_ids.get("tmdb"))
        imdb_id = _text(root, "imdb_id") or _text(root, "imdbid") or unique_ids.get("imdb")

        year_raw = _text(root, "year") or _text(root, "premiered", "")[:4] or None
        year = _int_or_none(year_raw)

        local_poster = _find_file(folder_path, _POSTER_NAMES)

        result = {
            "title": _text(root, "title") or _text(root, "sorttitle"),
            "year": year,
            "tmdb_id": tmdb_id,
            "imdb_id": imdb_id or "",
            "metadata_source": "nfo",
            "local_poster": local_poster,
        }

        logger.debug(
            "NFO parsed for movie %s: title=%r year=%s tmdb=%s",
            folder_path,
            result["title"],
            year,
            tmdb_id,
        )
        return result

    except ET.ParseError as e:
        logger.warning("Failed to parse movie NFO at %s: %s", nfo_path, e)
        return None
    except Exception as e:
        logger.warning("Unexpected error reading movie NFO at %s: %s", nfo_path, e)
        return None


def find_local_poster(folder_path: str) -> str | None:
    """Find a poster image in a media folder without parsing NFO.

    Checks folder_path first, then parent (handles Season subfolder layout).

    Args:
        folder_path: Path to the media folder (may be a Season subfolder).

    Returns:
        Absolute path to poster file, or None.
    """
    poster = _find_file(folder_path, _POSTER_NAMES)
    if poster is None:
        parent = os.path.dirname(folder_path)
        if parent != folder_path:
            poster = _find_file(parent, _POSTER_NAMES)
    return poster
