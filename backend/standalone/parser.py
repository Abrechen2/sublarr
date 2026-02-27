"""Media file parser -- extracts metadata from video filenames using guessit.

Handles both standard naming (S01E02) and anime naming (absolute episodes,
[Group] prefixes). Uses the full file path for series name context from
parent directories.
"""

import logging
import os
import re

from guessit import guessit

logger = logging.getLogger(__name__)

# Supported video file extensions (lowercase, with dot)
VIDEO_EXTENSIONS: set[str] = {
    ".mkv",
    ".mp4",
    ".avi",
    ".m4v",
    ".wmv",
    ".flv",
    ".webm",
    ".ts",
}

# Known anime fansub release groups for detection
ANIME_RELEASE_GROUPS: set[str] = {
    "SubsPlease",
    "Erai-raws",
    "HorribleSubs",
    "Judas",
    "EMBER",
    "ASW",
    "Tsundere-Raws",
    "DameDesuYo",
    "GJM",
    "Commie",
    "Underwater",
    "Coalgirls",
    "Kametsu",
    "MTBB",
    "Vivid",
    "Chihiro",
    "UTW",
    "FFF",
    "Mazui",
    "WhyNot",
    "Doki",
    "Cleo",
    "Nep_Blanc",
    "SmallSizedAnimations",
    "YuiSubs",
    "Anime Time",
    "SSA",
}

# Regex patterns for anime detection
_RE_BRACKET_GROUP = re.compile(r"^\[([^\]]+)\]")
_RE_CRC32 = re.compile(r"\[([0-9A-Fa-f]{8})\]")
_RE_ABSOLUTE_EP = re.compile(r" - (\d{1,4})(?:\s|\.|\[|$)")


def is_video_file(path: str) -> bool:
    """Check if a file path has a recognized video extension.

    Args:
        path: File path or filename to check.

    Returns:
        True if the extension is in VIDEO_EXTENSIONS.
    """
    _, ext = os.path.splitext(path)
    return ext.lower() in VIDEO_EXTENSIONS


def detect_anime_indicators(filename: str) -> bool:
    """Detect whether a filename has anime-style naming indicators.

    Checks for:
    - Square bracket group prefix: [GroupName]
    - Known anime release group in ANIME_RELEASE_GROUPS
    - Absolute episode numbering without season (e.g., "Title - 153.mkv")
    - CRC32 hash in brackets: [A1B2C3D4]

    Args:
        filename: Just the filename (not full path).

    Returns:
        True if anime indicators are detected.
    """
    # Check for [Group] prefix
    bracket_match = _RE_BRACKET_GROUP.search(filename)
    if bracket_match:
        group_name = bracket_match.group(1).strip()
        # Known anime release group
        if group_name in ANIME_RELEASE_GROUPS:
            return True
        # Any bracket group prefix is a moderate indicator -- combine with others
        has_bracket_group = True
    else:
        has_bracket_group = False

    # CRC32 hash in brackets (e.g., [A1B2C3D4])
    has_crc32 = bool(_RE_CRC32.search(filename))

    # Absolute episode numbering: "Title - 153.mkv" pattern
    has_absolute_ep = bool(_RE_ABSOLUTE_EP.search(filename))

    # Bracket group + CRC32 is strong anime indicator
    if has_bracket_group and has_crc32:
        return True

    # Bracket group + absolute numbering
    if has_bracket_group and has_absolute_ep:
        return True

    # Absolute numbering alone (without S01E01 pattern) is a moderate indicator
    # Only flag as anime if there's no SxxExx pattern present
    return bool(has_absolute_ep and not re.search(r"S\d{1,2}E\d{1,2}", filename, re.IGNORECASE))


def parse_media_file(file_path: str) -> dict:
    """Parse a media file path into structured metadata using guessit.

    Extracts title, season, episode, year, release group, and other metadata.
    Uses anime-specific guessit options when anime indicators are detected.
    Falls back to parent directory name for series title when guessit cannot
    extract it from the filename alone.

    Args:
        file_path: Full path to the media file.

    Returns:
        Dict with keys: type, title, season, episode, absolute_episode,
        year, release_group, source, resolution, video_codec, is_anime,
        confidence.
    """
    filename = os.path.basename(file_path)
    parent_dir = os.path.basename(os.path.dirname(file_path))

    is_anime = detect_anime_indicators(filename)

    # Parse with guessit
    if is_anime:
        guess = guessit(filename, {"type": "episode", "episode_prefer_number": True})
    else:
        guess = guessit(filename, {"type": "episode"})
        # If no episode info found, try as movie
        if "episode" not in guess and "season" not in guess:
            movie_guess = guessit(filename, {"type": "movie"})
            # Use movie guess if it looks more like a movie (has year, no episode)
            if "year" in movie_guess or movie_guess.get("type") == "movie":
                guess = movie_guess

    # Determine media type
    guess_type = guess.get("type", "episode")
    media_type = "movie" if guess_type == "movie" else "episode"

    # Extract title with parent directory fallback
    title = _extract_title(guess, parent_dir)

    # Extract episode info
    episode = _normalize_episode(guess.get("episode"))
    season = guess.get("season")
    absolute_episode = guess.get("absolute_episode") or guess.get("episode_number")

    # For anime with absolute numbering, episode might be the absolute episode
    if is_anime and episode is not None and season is None:
        absolute_episode = absolute_episode or episode

    # Normalize season to int or None
    if isinstance(season, list):
        season = season[0] if season else None

    # Extract release group
    release_group = guess.get("release_group", "")

    # Calculate confidence
    confidence = _calculate_confidence(title, season, episode, media_type, guess)

    result = {
        "type": media_type,
        "title": title,
        "season": season,
        "episode": episode,
        "absolute_episode": absolute_episode,
        "year": guess.get("year"),
        "release_group": release_group,
        "source": guess.get("source", ""),
        "resolution": guess.get("screen_size", ""),
        "video_codec": guess.get("video_codec", ""),
        "is_anime": is_anime,
        "confidence": confidence,
    }

    logger.debug("Parsed %s -> %s", filename, result)
    return result


def group_files_by_series(file_paths: list[str]) -> dict[str, list[dict]]:
    """Group parsed media files by normalized series title.

    Parses each file path and groups them by a lowercase, stripped version
    of the title. Only includes episode-type files (movies are excluded).

    Args:
        file_paths: List of full file paths to parse and group.

    Returns:
        Dict mapping normalized title to list of parsed file info dicts
        (each dict includes an additional 'file_path' key).
    """
    groups: dict[str, list[dict]] = {}

    for path in file_paths:
        try:
            parsed = parse_media_file(path)
            if parsed["type"] != "episode":
                continue

            normalized = parsed["title"].lower().strip()
            if not normalized:
                continue

            entry = {**parsed, "file_path": path}
            groups.setdefault(normalized, []).append(entry)
        except Exception as e:
            logger.warning("Failed to parse %s: %s", path, e)

    return groups


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_title(guess: dict, parent_dir: str) -> str:
    """Extract the best title from guessit result with fallback to parent dir."""
    title = guess.get("title", "")

    # guessit may return a list for title in rare cases
    if isinstance(title, list):
        title = title[0] if title else ""

    title = str(title).strip()

    # Fallback to parent directory name if title is empty or generic
    if not title or title.lower() in ("", "video", "movie"):
        title = parent_dir.strip()

    return title


def _normalize_episode(episode_val) -> int | None:
    """Normalize episode value from guessit (may be int, list, or None)."""
    if episode_val is None:
        return None
    if isinstance(episode_val, list):
        return episode_val[0] if episode_val else None
    return int(episode_val)


def _calculate_confidence(
    title: str, season: int | None, episode: int | None, media_type: str, guess: dict
) -> str:
    """Calculate parsing confidence level.

    Returns:
        'high', 'medium', or 'low' based on how much was parsed.
    """
    score = 0

    if title:
        score += 1
    if media_type == "episode":
        if season is not None:
            score += 1
        if episode is not None:
            score += 1
    else:
        # Movie
        if guess.get("year"):
            score += 1
        score += 1  # Movies need less info

    if guess.get("release_group"):
        score += 1
    if guess.get("screen_size"):
        score += 1

    if score >= 4:
        return "high"
    elif score >= 2:
        return "medium"
    return "low"
