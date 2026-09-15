"""Validate AnimeTosho identities before candidates can earn scoring bonuses.

AniDB ids in the feed can be wrong (GH #210), and an SxxEyy episode number
is not an absolute number. Neither can override contradictory release names.
"""

import re
import unicodedata

from guessit import guessit

from providers.base import VideoQuery


def _normalise_title(title: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKC", title).casefold() if c.isalnum())


def match_release(
    title: str, query: VideoQuery, *, allow_pack: bool = False, require_title: bool = True
) -> set[str] | None:
    """Return proven matches, or None for a contradictory release.

    Packs may pass the feed filter, but only a matching individual file may
    supply an attachment. A missing episode is not an episode match.
    """
    # Four-digit absolute numbers otherwise look like compact SxxEyy to
    # GuessIt (0021 -> S00E21, 1080 -> S10E80).
    parse_title = re.sub(r"(\s-\s)(\d{1,4})(?=v\d|[\s.\[]|$)", r"\1E\2", title)
    parsed = guessit(
        parse_title, options={"type": "episode" if query.episode is not None else "movie"}
    )
    matches = set()
    expected_title = query.series_title or query.title
    parsed_title = parsed.get("title")
    alternative_title = parsed.get("alternative_title")
    if (
        isinstance(parsed_title, str)
        and alternative_title
        and not isinstance(parsed.get("episode"), list)
    ):
        # GuessIt calls the sequel suffix in "Bleach - Sennen Kessen-hen"
        # an alternative_title. It is still part of the series identity.
        # Named arc packs are checked through their individual files instead.
        parsed_title = f"{parsed_title} {alternative_title}"
    if parsed_title and expected_title:
        titles = parsed_title if isinstance(parsed_title, list) else [parsed_title]
        if _normalise_title(expected_title) not in {_normalise_title(t) for t in titles}:
            return None
        matches.add("series" if query.episode is not None else "title")
    elif require_title:
        return None

    if query.episode is None:
        if query.year and parsed.get("year") and parsed["year"] != query.year:
            return None
        return matches

    # GuessIt reads 21.5 as episode 21 + episode title "5". Recaps and
    # fractional episodes must never masquerade as the regular integer.
    if re.search(r"(?:\s-\s|\bEP?)[0-9]+\.[0-9]+\b", title, re.IGNORECASE):
        return None

    season = parsed.get("season")
    if season is not None and query.season is not None:
        if season != query.season:
            return None
        matches.add("season")

    episode = parsed.get("episode")
    target = (
        query.episode
        if season is not None
        else (query.absolute_episode if query.absolute_episode is not None else query.episode)
    )
    if isinstance(episode, list):
        # A feed title such as "01-366" is an invitation to inspect its files,
        # never proof that every attachment belongs to the requested episode.
        if not allow_pack or not min(episode) <= target <= max(episode):
            return None
    elif episode is not None:
        if episode != target:
            return None
        matches.add("episode")
    return matches


def match_entry(entry: dict, query: VideoQuery) -> set[str] | None:
    """Cross-check feed ids and release title; never trust a query id alone."""
    for field, expected in (
        ("anidb_aid", query.anidb_id),
        ("anidb_eid", query.anidb_episode_id),
    ):
        actual = entry.get(field)
        if expected and actual and str(actual) != str(expected):
            return None
    return match_release(entry.get("title", ""), query, allow_pack=True)
