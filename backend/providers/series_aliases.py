"""Which season a release's own series title names, from Sonarr's aliases.

Sequels are often numbered per season with the season only in the title:
"Strike Witches - Road to Berlin - 05" is S03E05, "Psycho-Pass 2 - 01" is
S02E01. Sonarr lists such titles as alternateTitles with a ``seasonNumber``
(the library season) and/or a ``sceneSeasonNumber`` (the scene's season,
which may differ: "Criminal Minds Evolution" is scene season 1 but library
season 16). A title scoped to a season names it; -1 means every season.

Only an unambiguous match proves anything: the release's title, up to its
episode number, must be one alias word for word. Two aliases of one name for
different seasons (K-ON! / K-ON!!), the bare series title, or a longer name
("Dr Stone - New World Part 2", a split cour) prove nothing.
"""

from __future__ import annotations

import re
import unicodedata

from providers.base import VideoQuery

# Leading release-group tags: "[Erai-raws] ", "(Hi10)_".
_GROUP_RE = re.compile(r"^(?:\s*[\[(][^\])]*[\])][\s_.]*)+")
# Where the series title ends: the episode numbering the gate reads.
_NUMBERING_RE = re.compile(
    r"\s-\s*\d|_-_\d|(?<![a-z0-9])(?:s\d{1,3}[ ._-]?e\s?\d|\d{1,2}x\d{1,3}|(?:ep?|episode)[ ._]?\d)",
    re.IGNORECASE,
)

Alias = tuple[str, int | None, int | None]  # (title, library season, scene season)


def normalise(title: str) -> str:
    return "".join(words(title))


def words(text: str) -> list[str]:
    return re.findall(r"[0-9a-z]+", unicodedata.normalize("NFKC", text or "").casefold())


def release_title_words(text: str) -> tuple[str, ...]:
    """The words of the series title a release name opens with, up to its numbering."""
    name = _GROUP_RE.sub("", (text or "").replace("_", " ").replace(".", " "))
    end = _NUMBERING_RE.search(name)
    return tuple(words(name[: end.start()] if end else ""))


def _alias_season(alias: Alias, query: VideoQuery) -> str | None:
    """ "this" / "season N" / "scene season N" for one alias; None if it names none."""
    _title, library, scene = (*alias, None)[:3]
    if library is not None and library >= 0:
        return "this" if library == query.season else f"season {library}"
    if scene is not None and scene >= 0:
        # Without a scene mapping Sonarr's scene season is the library season.
        episode_scene = getattr(query, "scene_season", None)
        if episode_scene is None:
            episode_scene = query.season
        return "this" if scene == episode_scene else f"scene season {scene}"
    return None


def title_scope(name: tuple[str, ...], query: VideoQuery) -> str | None:
    """ "this" when ``name`` is the queried season's own title, "season N" for another.

    ``name`` must be an alias word for word (it ends where the numbering
    starts, so "Psycho-Pass - 2" is not "Psycho-Pass 2"). None when nothing
    proves a season: no such alias, the bare title, a longer name such as
    "New World Part 2", or aliases of this name for different seasons.
    """
    if not name:
        return None
    aliases = [(query.series_title, -1, None), *(getattr(query, "series_aliases", None) or ())]
    verdicts = {_alias_season(alias, query) for alias in aliases if tuple(words(alias[0])) == name}
    return verdicts.pop() if len(verdicts) == 1 else None
