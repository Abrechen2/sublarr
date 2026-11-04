"""Which Jimaku entries and files belong to the queried episode.

Jimaku's name search returns every entry that looks alike — all seasons of a
series and unrelated titles ("Frieren" also found Dragon Ball) — and an entry
lists every file of every episode. Until 1.20.0 the provider offered all of
them (440 files for Mushoku Tensei S01E05), and a season 3 file outranked the
right ones, which carried no episode match at all.
"""

from __future__ import annotations

import re
import unicodedata

from guessit import guessit

from providers.base import VideoQuery
from providers.series_aliases import normalise

_ROMAN = {"ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "ⅱ": 2, "ⅲ": 3, "ⅳ": 4, "ⅴ": 5}
_SEASON_PATTERNS = (
    re.compile(r"\bseason\s*(\d{1,2})\b", re.IGNORECASE),
    re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)\s+season\b", re.IGNORECASE),
    re.compile(r"第\s*(\d{1,2})\s*期"),
)
_ROMAN_RE = re.compile(r"(?:^|[\s:])(ii|iii|iv|v|vi|ⅱ|ⅲ|ⅳ|ⅴ)(?=$|[\s:～~])", re.IGNORECASE)
# A split cour of one season: same season, its own episode numbering.
_PART_RE = re.compile(r"\b(?:part|cour)\s*([2-9])\b|第\s*([2-9])\s*クール", re.IGNORECASE)
_MARKERS_RE = re.compile(
    r"\bseason\s*\d{1,2}\b|\b\d{1,2}(?:st|nd|rd|th)\s+season\b|第\s*\d{1,2}\s*期"
    r"|\b(?:part|cour)\s*\d\b|(?:^|(?<=[\s:]))(?:ii|iii|iv|v|vi|ⅱ|ⅲ|ⅳ|ⅴ)(?=$|[\s:～~])",
    re.IGNORECASE,
)


def _names(entry: dict) -> list[str]:
    return [n for n in (entry.get("name"), entry.get("english_name")) if n]


def entry_season(entry: dict) -> int | None:
    """The season an entry's title names (II, Season 2, 2nd Season, 第2期), or None."""
    for name in (*_names(entry), entry.get("japanese_name") or ""):
        text = unicodedata.normalize("NFKC", name)  # "Ⅱ" -> "II", full-width digits
        for pattern in _SEASON_PATTERNS:
            found = pattern.search(text)
            if found:
                return int(found.group(1))
        roman = _ROMAN_RE.search(text)
        if roman:
            return _ROMAN[roman.group(1).lower()]
    return None


def is_later_part(entry: dict) -> bool:
    """True for the second (or later) cour of a season: "Part 2", "Cour 2", 第2クール."""
    return any(_PART_RE.search(name) for name in (*_names(entry), entry.get("japanese_name") or ""))


def _query_titles(query: VideoQuery) -> list[str]:
    titles = [query.series_title or query.title]
    titles += [alias[0] for alias in getattr(query, "series_aliases", None) or ()]
    return [normalise(t) for t in titles if t and normalise(t)]


def matches_title(entry: dict, query: VideoQuery) -> bool:
    """True when an entry's title, without its season markers, is the series'."""
    wanted = _query_titles(query)
    for name in _names(entry):
        bare = normalise(_MARKERS_RE.sub(" ", name))
        if bare and any(bare.startswith(t) or t.startswith(bare) for t in wanted):
            return True
    return False


def select_entries(entries: list[dict], query: VideoQuery) -> list[dict]:
    """The entries of the queried series and season, best first.

    Unchanged when no entry carries the series' title (a Sonarr title in
    another language), so such a search keeps finding what it found before.
    """
    titled = [e for e in entries if matches_title(e, query)]
    if not titled:
        return entries
    if query.season is None or getattr(query, "absolute_episode", None) is not None:
        return titled
    same = [e for e in titled if entry_season(e) == query.season]
    unmarked = [e for e in titled if entry_season(e) is None]
    if query.season == 1:
        same = same + unmarked
    chosen = same or unmarked
    return sorted(chosen, key=is_later_part)


def file_episodes(filename: str) -> tuple[int | None, list[int]]:
    """(season, episodes) a subtitle file name states; ``[]`` when it names none."""
    # "Show - 05" reads as a title to GuessIt; mark the number as an episode.
    stem = re.sub(r"(\s-\s)(\d{1,4})(?=v\d|[\s.\[(]|$)", r"\1E\2", filename)
    try:
        parsed = guessit(stem, options={"type": "episode"})
    except Exception:  # noqa: BLE001 — an unparsable name names no episode
        return None, []
    episode = parsed.get("episode")
    episodes = episode if isinstance(episode, list) else [episode] if episode is not None else []
    season = parsed.get("season")
    return (season if isinstance(season, int) else None), [
        e for e in episodes if isinstance(e, int)
    ]


def file_matches_episode(filename: str, query: VideoQuery, episode: int) -> bool:
    """True when a subtitle file is for exactly this episode (or this multi-episode file).

    A file for several episodes ("01-04 TVSP") only fits a video of the same
    episodes; a stated season must be the queried one (absolute numbering
    has none).
    """
    file_season, episodes = file_episodes(filename)
    if episode not in episodes:
        return False
    if len(episodes) > 1 and set(episodes) != set(query.episodes or [episode]):
        return False
    absolute = getattr(query, "absolute_episode", None) is not None
    return not (
        file_season is not None
        and not absolute
        and query.season is not None
        and file_season != query.season
    )


_LANGUAGE_TAGS = {
    "ja": "ja", "jp": "ja", "jpn": "ja", "japanese": "ja",
    "en": "en", "eng": "en", "english": "en",
    "de": "de", "deu": "de", "ger": "de", "german": "de",
    "fr": "fr", "fra": "fr", "fre": "fr", "french": "fr",
    "es": "es", "spa": "es", "spanish": "es",
    "zh": "zh", "chi": "zh", "chs": "zh", "cht": "zh", "chinese": "zh",
}  # fmt: skip
_TAG_GROUP_RE = re.compile(
    r"\[([^\]]+)\]|(?<=[._])([a-z]{2,8}(?:-[a-z]{2,8})*)(?=[._\[])", re.IGNORECASE
)


def language_from_tags(filename: str) -> str | None:
    """The one language a file name's tags state; None when none or several."""
    stem = filename.rsplit(".", 1)[0] + "."
    found = set()
    for bracket, dotted in _TAG_GROUP_RE.findall(stem):
        parts = re.split(r"[,\s/+-]+", bracket or dotted)
        tags = {_LANGUAGE_TAGS.get(part.lower()) for part in parts if part}
        if bracket and None in tags:
            continue  # "[1080p]", "[Web]": a bracket that is not a language list
        found |= {tag for tag in tags if tag}
    return found.pop() if len(found) == 1 else None


MAX_NAME_SEARCHES = 3


def search_names(query: VideoQuery) -> list[str]:
    """Names to search Jimaku for, in turn: the title, Sonarr's aliases, the main title."""
    title = query.series_title or query.title
    names = [title, *(alias[0] for alias in getattr(query, "series_aliases", None) or ())]
    if title and ":" in title:
        names.append(title.split(":", 1)[0])
    unique, seen = [], set()
    for name in names:
        key = normalise(name or "")
        if key and key not in seen:
            seen.add(key)
            unique.append(name.strip())
    return unique[:MAX_NAME_SEARCHES]
