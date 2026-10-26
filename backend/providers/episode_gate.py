"""Drop results that name another episode than the episode query asks for.

Missing the ``season`` scoring bonus is not enough: series (180) or year (90)
plus episode (30) still clear min_score, and that is how Clevatess S02E12
got ``Clevatess - S01E12 [CR WEB-DL 1080p]`` from OpenSubtitles and
``[SubsPlease] Clevatess - 12`` from AnimeTosho in prod, and subtitlecat
gave Overgeared S01E04 an ``S01E03`` release on a "series" match alone.
A result naming a different episode is a different episode; it is dropped
before scoring can rank it, for every provider including hub bundles.

What a name may say and still be the queried episode:

- ``S02E12`` (or ``2x12``) for S02E12, including multi-episode files;
- ``S01E24`` or a bare ``- 24`` when the query's absolute number is 24
  (Shoko / AniDB mapping, else Sonarr's ``absoluteEpisodeNumber``);
- a season pack (``S02``) of the queried season;
- a bare ``- 12`` when no absolute number is known, or when the name marks
  a season — it may be this season's twelfth.

A hash match identifies the file itself and is never second-guessed. A
result whose names carry no numbering at all keeps its current behaviour,
but only when something else proves the episode: an ``episode`` match, a
hash match, or a pack the provider resolves at download time.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from providers.base import SubtitleResult, VideoQuery
from providers.series_aliases import release_title_words, title_scope

logger = logging.getLogger(__name__)

# ``S02E07`` / ``s2.e7`` / ``S02 E07`` / ``S01E01E02`` / ``S01E01-E03`` / ``S01E01-03`` /
# ``S01 E01~E12`` / ``S01E 07``.
_SEASON_EPISODE_RE = re.compile(
    r"(?<![a-z0-9])s(\d{1,3})[ ._-]?e ?(\d{1,4})((?:(?:[ ._]?e ?|-e?|\s*~\s*e?)\d{1,4}(?![\dp]))*)",
    re.IGNORECASE,
)
# ``2x07`` / ``1x5``; four-digit sides (``1920x1080``) are resolutions, not episodes.
_CROSS_RE = re.compile(r"(?<![a-z0-9])(\d{1,2})x(\d{1,3})(?![a-z0-9])", re.IGNORECASE)
# ``S02`` / ``Season 2`` / ``S01-S02`` with no episode after it.
_SEASON_RE = re.compile(
    r"(?<![a-z0-9])(?:s|season[ ._-]?)(\d{1,2})(?:\s?-\s?(?:s|season[ ._-]?)(\d{1,2}))?(?![0-9])",
    re.IGNORECASE,
)
# A season named without a number: "The Final Season", "2nd Season", "Part 2", "II".
_VAGUE_SEASON_RE = re.compile(
    r"(?<![a-z0-9])(?:season|\d+(?:st|nd|rd|th)|part[ ._-]?\d|ii|iii|iv|vi)(?![a-z0-9])",
    re.IGNORECASE,
)
# Batch ranges: "Show - 13-24", "Show - 01 ~ 22", "Show - Ep. 01 - 19", "Episode 1 - 14",
# "Show - E01-03". A range names every episode in it, not its first or last.
_EP = r"(?:(?:ep?|episodes?)\.?[ ._]?)"
_BARE_RANGE_RE = re.compile(
    r"(?:\s-\s|_-_|(?<![a-z0-9])(?=e))" + _EP + r"?(\d{1,4})(?:v\d)?"
    r"\s*[-~\u2013]\s*" + _EP + r"?(\d{1,4})(?:v\d)?(?![.-]\d)(?=$|[\s._\[\](),-])",
    re.IGNORECASE,
)
_MAX_RANGE = 500
# Anime-style bare numbers: "Show - 12", "Show - 12v2", "Show E12", "Show EP12", "Episode 12".
_BARE_RE = re.compile(
    r"(?:\s-\s|_-_|(?<![a-z0-9])(?:ep?|episode)[ ._]?)(\d{1,4})(?:v\d)?(?!\.\d)"
    r"(?=$|[\s._\[\](),-])",
    re.IGNORECASE,
)
# A recap between two episodes: "Show - 11.5". It is no regular episode at all.
# Right before a file extension (and language tags such as ".en" / ".pt-br")
# only ".5" counts ("Show - 11.5.en.srt"): there
# "Show - 2.0.srt" is more likely a subtitle version than a recap.
_FRACTION_RE = re.compile(
    r"(?:\s-\s|_-_)(\d{1,4}\.\d)(?=$|[\s_\[\](),-])"
    r"|(?:\s-\s|_-_)(\d{1,4}\.5)"
    r"(?=(?:\.[a-z]{2,8}(?:-[a-z0-9]{2,4})?)*\.(?:srt|ass|ssa|vtt|sub|idx|sup|mkv|mp4|avi|zip|rar|7z)$)",
    re.IGNORECASE,
)

_YEARS = (1900, 2099)


@dataclass
class _Claims:
    """What one name says about season and episode."""

    season_episodes: list[tuple[int, set[int]]] = field(default_factory=list)
    seasons: set[int] = field(default_factory=set)
    vague_season: bool = False
    bare: set[int] = field(default_factory=set)
    fractions: set[str] = field(default_factory=set)
    # The words of the series title the name opens with (see series_aliases).
    title_words: tuple[str, ...] = ()

    @property
    def empty(self) -> bool:
        return not (self.season_episodes or self.seasons or self.bare or self.fractions)


def _episodes(first: str, rest: str) -> set[int]:
    numbers = [int(first), *(int(n) for n in re.findall(r"\d+", rest or ""))]
    if (
        rest
        and re.search(r"[-~]", rest)
        and len(numbers) == 2
        and 0 < numbers[1] - numbers[0] <= _MAX_RANGE
    ):
        return set(range(numbers[0], numbers[1] + 1))
    return set(numbers)


def _is_year(number: int) -> bool:
    return _YEARS[0] <= number <= _YEARS[1]


def _take_range(match: re.Match, bare: set[int]) -> str:
    """Add a batch range's episodes to ``bare``; leave anything else for _BARE_RE."""
    low, high = int(match.group(1)), int(match.group(2))
    if low >= high or high - low > _MAX_RANGE or _is_year(low) or _is_year(high):
        return match.group(0)
    bare.update(range(low, high + 1))
    return " "


def parse_claims(text: str) -> _Claims:
    """Season/episode numbering named in ``text`` (empty claims when none)."""
    claims = _Claims()
    text = text or ""
    claims.title_words = release_title_words(text)
    for match in _SEASON_EPISODE_RE.finditer(text):
        claims.season_episodes.append(
            (int(match.group(1)), _episodes(match.group(2), match.group(3)))
        )
    rest = _SEASON_EPISODE_RE.sub(" ", text)
    for match in _CROSS_RE.finditer(rest):
        claims.season_episodes.append((int(match.group(1)), {int(match.group(2))}))
    rest = _CROSS_RE.sub(" ", rest)
    for match in _SEASON_RE.finditer(rest):
        low = int(match.group(1))
        high = int(match.group(2)) if match.group(2) else low
        claims.seasons.update(range(min(low, high), max(low, high) + 1))
    rest = _SEASON_RE.sub(" ", rest)
    claims.vague_season = bool(_VAGUE_SEASON_RE.search(rest))
    rest = _BARE_RANGE_RE.sub(lambda m: _take_range(m, claims.bare), rest)
    claims.fractions.update(m.group(1) or m.group(2) for m in _FRACTION_RE.finditer(rest))
    claims.bare.update(
        number
        for number in (int(m.group(1)) for m in _BARE_RE.finditer(rest))
        # "Show - 2024 [1080p]" is a year, not episode 2024.
        if not _is_year(number)
    )
    return claims


def contradicts_query_numbering(query: VideoQuery, season: int, episodes: set[int]) -> bool:
    """True when ``SxxEyy`` names another episode than the query.

    The one sanctioned mismatch is continuous numbering: S01E<absolute> for
    anime numbered as one long season, and Crunchyroll's S03E39 for S03E01
    (absolute 39) or S02E25 for S02E01. Only season 1 or the queried season
    may carry the absolute number: "S02E05" for S01E05 (absolute 5) is
    season 2's fifth, and "S02E25" for S03E01 (absolute 25) may be season
    2's own twenty-fifth.
    """
    if season == query.season and episodes & _wanted_episodes(query):
        return False
    absolute = query.matching_absolute_episode
    return not (absolute is not None and absolute in episodes and season in {1, query.season})


def _wanted_episodes(query: VideoQuery) -> set[int]:
    return {query.episode, *(query.episodes or [])} - {None}


def _verdict(claims: _Claims, query: VideoQuery) -> tuple[str, str]:
    """("match" | "season" | "contradict" | "", detail) for one name."""
    if claims.season_episodes:
        for season, episodes in claims.season_episodes:
            if not contradicts_query_numbering(query, season, episodes):
                return "match", ""
        season, episodes = claims.season_episodes[0]
        return "contradict", f"S{season:02d}E{min(episodes):02d}"
    scope = title_scope(claims.title_words, query)
    if scope is not None and not claims.seasons and claims.bare:
        # "Road to Berlin - 05": the title names season 3, the number is its own
        # and is not checked against the absolute number.
        if scope != "this":
            return "contradict", f"{scope} by its title"
        if claims.bare & _wanted_episodes(query):
            return "match", ""
        # "Shingeki no Kyojin (The Final Season) - 60" for S04E01: a number the
        # season cannot hold is its absolute one; "Show II - 13" for a season of
        # unknown or 13+ episodes may be its own thirteenth.
        absolute = query.matching_absolute_episode
        size = getattr(query, "season_size", None)
        if absolute in claims.bare and size is not None and absolute > size:
            return "match", ""
        return "contradict", f"episode {min(claims.bare)}"
    absolute = query.matching_absolute_episode
    if claims.seasons and query.season not in claims.seasons:
        if absolute is not None and absolute in claims.bare:
            return "match", ""
        return "contradict", f"season {min(claims.seasons)}"
    if claims.bare:
        allowed = {absolute} - {None}
        # Without an absolute number, or with the season in the name, a bare
        # number may be this season's. With a known absolute and no season
        # anywhere, "12" for S02E12 (absolute 24) is season 1's twelfth.
        if absolute is None or claims.seasons or claims.vague_season or query.season == 1:
            allowed |= _wanted_episodes(query)
        if claims.bare & allowed:
            return "match", ""
        return "contradict", f"episode {min(claims.bare)}"
    if claims.fractions:
        return "contradict", f"episode {min(claims.fractions)}"
    if claims.seasons:
        return "season", ""
    return "", ""


def _resolves_pack(result: SubtitleResult) -> bool:
    """The provider picks the episode out of an archive at download time."""
    data = result.provider_data or {}
    return bool(data.get("is_pack") or data.get("is_archive"))


def episode_gate_reason(result: SubtitleResult, query: VideoQuery) -> str:
    """Why ``result`` is not the queried episode; empty string when it may be."""
    if not query.is_episode or "hash" in result.matches:
        return ""
    verdicts = [
        _verdict(parse_claims(text), query)
        for text in (result.filename, result.release_info)
        if text
    ]
    kinds = {kind for kind, _ in verdicts}
    if "match" in kinds:
        return ""
    contradiction = next((detail for kind, detail in verdicts if kind == "contradict"), "")
    if contradiction and _names_episode_title(query, result):
        return ""
    if contradiction:
        return f"names {contradiction}, query is {_wanted_label(query)}"
    if "episode" in result.matches or "season" in kinds or _resolves_pack(result):
        return ""
    return "no episode evidence (no episode match and no numbering in the name)"


_GENERIC_TITLE_RE = re.compile(r"(?:episode|folge|ep|chapter|kapitel|part|teil|tba|tbd)?\s*\d*")
_MIN_TITLE = 8


def _normalise(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (text or "").casefold()))


# Where a release's own episode title ends: a tag, a bracket or a quality marker.
_TITLE_END_RE = re.compile(
    r"[\[(]|_\[|\b(?:\d{3,4}p|web(?:-?dl|rip)?|bluray|bdrip|hdtv|x26[45]|h\.?26[45]|hevc|"
    r"aac|amzn|cr|nf|dsnp|multi|dual|eng|ger|german|english)\b",
    re.IGNORECASE,
)


def _release_title(text: str) -> str:
    """The episode title a release names right after its ``SxxEyy``, normalised."""
    match = _SEASON_EPISODE_RE.search(text or "")
    if not match:
        return ""
    tail = text[match.end() :]
    end = _TITLE_END_RE.search(tail)
    return _normalise(tail[: end.start()] if end else tail)


def _names_episode_title(query: VideoQuery, result: SubtitleResult) -> bool:
    """The release's own title is the queried episode's title, so it is that episode.

    Releases number by their own scheme ("My Hero Academia S03E39 Game Start"
    for Sonarr's S03E01 "Game Start"); the title does not change with it.
    The whole title must match ("The Beginning" is not "The Beginning of the
    End"); generic, short and series-name titles prove nothing.
    """
    title = _normalise(query.title) if query.is_episode else ""
    if (
        len(title) < _MIN_TITLE
        or _GENERIC_TITLE_RE.fullmatch(title)
        or title == _normalise(query.series_title)
    ):
        return False
    return any(_release_title(text) == title for text in (result.filename, result.release_info))


def _wanted_label(query: VideoQuery) -> str:
    wanted = f"S{query.season:02d}E{query.episode:02d}"
    absolute = query.matching_absolute_episode
    if absolute is not None:
        wanted += f" (absolute {absolute})"
    return wanted


def archive_member_reason(result: SubtitleResult, member: str, query: VideoQuery) -> str:
    """Why the file a provider took out of an archive is not the queried episode.

    The gate before download only sees the listing: a ``Show.S02E05.zip``
    whose one member is ``Show.S01E05.srt`` passed it (VM 191, RC 1.17.0-rc.1).
    Only a name that contradicts the query rejects; a member without
    numbering is left to the listing that already passed.
    """
    if not member or not query.is_episode or "hash" in result.matches:
        return ""
    kind, detail = _verdict(parse_claims(member), query)
    if kind != "contradict" or _names_episode_title(query, result):
        return ""
    return f"archive member {member!r} names {detail}, query is {_wanted_label(query)}"


def apply_episode_gate(
    results: list[SubtitleResult], query: VideoQuery
) -> tuple[list[SubtitleResult], list[tuple[SubtitleResult, str]]]:
    """Split ``results`` into (kept, [(rejected, reason), ...])."""
    if not query.is_episode:
        return list(results), []
    kept: list[SubtitleResult] = []
    rejected: list[tuple[SubtitleResult, str]] = []
    for result in results:
        reason = episode_gate_reason(result, query)
        if reason:
            logger.debug(
                "Episode gate: dropping %s/%s (%s) for %s — %s",
                result.provider_name,
                result.subtitle_id,
                result.filename or result.release_info,
                query.display_name,
                reason,
            )
            rejected.append((result, reason))
        else:
            kept.append(result)
    return kept, rejected
