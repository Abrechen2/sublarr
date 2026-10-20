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

logger = logging.getLogger(__name__)

# ``S02E07`` / ``s2.e7`` / ``S02 E07`` / ``S01E01E02`` / ``S01E01-E03`` / ``S01E01-03``.
_SEASON_EPISODE_RE = re.compile(
    r"(?<![a-z0-9])s(\d{1,3})[ ._-]?e(\d{1,4})((?:(?:[ ._]?e|-e?)\d{1,4}(?![\dp]))*)",
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
# Anime-style bare numbers: "Show - 12", "Show - 12v2", "Show E12", "Show EP12", "Episode 12".
_BARE_RE = re.compile(
    r"(?:\s-\s|_-_|(?<![a-z0-9])(?:ep?|episode)[ ._]?)(\d{1,4})(?:v\d)?(?=$|[\s._\[\](),-])",
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

    @property
    def empty(self) -> bool:
        return not (self.season_episodes or self.seasons or self.bare)


def _episodes(first: str, rest: str) -> set[int]:
    numbers = [int(first), *(int(n) for n in re.findall(r"\d+", rest or ""))]
    if rest and "-" in rest and len(numbers) == 2 and numbers[0] < numbers[1]:
        return set(range(numbers[0], numbers[1] + 1))
    return set(numbers)


def parse_claims(text: str) -> _Claims:
    """Season/episode numbering named in ``text`` (empty claims when none)."""
    claims = _Claims()
    text = text or ""
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
    claims.bare.update(
        number
        for number in (int(m.group(1)) for m in _BARE_RE.finditer(rest))
        # "Show - 2024 [1080p]" is a year, not episode 2024.
        if not _YEARS[0] <= number <= _YEARS[1]
    )
    return claims


def contradicts_query_numbering(query: VideoQuery, season: int, episodes: set[int]) -> bool:
    """True when ``SxxEyy`` names another episode than the query.

    The one sanctioned mismatch is anime numbered as a single long season:
    S01E<absolute> is the queried episode when the query knows its absolute
    number.
    """
    if season == query.season:
        return not episodes & _wanted_episodes(query)
    absolute = query.matching_absolute_episode
    return not (season == 1 and absolute is not None and absolute in episodes)


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
    if contradiction:
        return f"names {contradiction}, query is {_wanted_label(query)}"
    if "episode" in result.matches or "season" in kinds or _resolves_pack(result):
        return ""
    return "no episode evidence (no episode match and no numbering in the name)"


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
    if kind != "contradict":
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
