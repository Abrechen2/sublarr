"""Parsing for titrari.ro search pages and season-pack archives (Forgejo #21).

Built against a real search page (tests/fixtures/titrari/search_inception.html):

- The search form sends ``page=cautare`` with ``z2`` (title), ``z3`` (language,
  1 = Romanian), ``z4`` (sort) and ``z1``. Any other field is ignored and the
  site answers with its default list, which is what the provider used to show
  for every query.
- The site matches the bare title only: "Inception 2010" or "Breaking Bad
  S01E04" find nothing. Series are season packs titled "<Series> - Sezonul N"
  or "<Series> - Sezoanele A-B".
- Each result holds one download link ``get.php?id=<n>``, its title in the
  preceding ``<h1>`` and the uploader's release note in the next
  ``td.comment``. Like, follow and comment links sit in the same block.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urljoin, urlparse

BASE_URL = "https://www.titrari.ro"
SEARCH_URL = f"{BASE_URL}/index.php"
LANGUAGE_ROMANIAN = 1
SORT_BY_DATE = 1

_SITE_HOST = urlparse(BASE_URL).netloc
_COMMENT_LABEL_RE = re.compile(r"^\s*Comentariu:\s*", re.I)
_SEASON_RE = re.compile(r"\bSezonul\s+(\d{1,2})\b", re.I)
_SEASON_RANGE_RE = re.compile(r"\bSezoanele\s+(\d{1,2})\s*-\s*(\d{1,2})\b", re.I)
_EPISODE_MARKER_RE = re.compile(r"(?i)(?:\bS(\d{1,2})[ ._-]?E(\d{1,3})\b|\b(\d{1,2})x(\d{2,3})\b)")
_MAX_COMMENT_CHARS = 300


@dataclass(frozen=True)
class TitrariEntry:
    """One search result: download id, title and the uploader's note."""

    subtitle_id: str
    title: str
    comment: str

    @property
    def download_url(self) -> str:
        return f"{BASE_URL}/get.php?id={self.subtitle_id}"

    @property
    def release_info(self) -> str:
        return f"{self.title} {self.comment}".strip()


def search_params(search_term: str) -> dict:
    """Query string of the site's own search form."""
    return {
        "page": "cautare",
        "z1": 0,
        "z2": search_term,
        "z3": LANGUAGE_ROMANIAN,
        "z4": SORT_BY_DATE,
    }


def _download_id(href: str) -> str | None:
    parsed = urlparse(urljoin(BASE_URL + "/", href))
    if parsed.netloc != _SITE_HOST or not parsed.path.endswith("/get.php"):
        return None
    value = parse_qs(parsed.query).get("id", [""])[0]
    return value if value.isdigit() else None


def _comment_after(link) -> str:
    cell = link.find_next("td", class_="comment")
    while cell is not None and _COMMENT_LABEL_RE.fullmatch(cell.get_text(" ", strip=True) or ""):
        cell = cell.find_next("td", class_="comment")
    if cell is None:
        return ""
    # Stop at the next result: a note further down belongs to another entry.
    next_download = link.find_next("a", href=re.compile(r"get\.php\?id=\d+"))
    if next_download is not None and _precedes(next_download, cell):
        return ""
    text = " ".join(cell.get_text(" ", strip=True).split())
    return _COMMENT_LABEL_RE.sub("", text)[:_MAX_COMMENT_CHARS]


def _precedes(first, second) -> bool:
    """True when ``first`` comes before ``second`` in document order."""
    return any(element is second for element in first.next_elements)


def parse_entries(soup) -> list[TitrariEntry]:
    """One entry per download link, in page order, without duplicates."""
    entries: list[TitrariEntry] = []
    seen: set[str] = set()
    for link in soup.find_all("a", href=True):
        subtitle_id = _download_id(link["href"])
        if subtitle_id is None or subtitle_id in seen:
            continue
        heading = link.find_previous("h1")
        title = " ".join(heading.get_text(" ", strip=True).split()) if heading else ""
        if not title:
            continue
        seen.add(subtitle_id)
        entries.append(TitrariEntry(subtitle_id, title, _comment_after(link)))
    return entries


def season_covered(title: str, season: int | None) -> bool:
    """Whether a pack title ("Sezonul 2", "Sezoanele 1-5") includes ``season``."""
    if season is None:
        return False
    for match in _SEASON_RE.finditer(title):
        if int(match.group(1)) == season:
            return True
    for match in _SEASON_RANGE_RE.finditer(title):
        if int(match.group(1)) <= season <= int(match.group(2)):
            return True
    return False


def _episode_of(name: str) -> tuple[int, int] | None:
    match = _EPISODE_MARKER_RE.search(name.rsplit("/", 1)[-1])
    if not match:
        return None
    season, episode = (match.group(1), match.group(2)) if match.group(1) else match.group(3, 4)
    return int(season), int(episode)


def pick_episode_member(
    members: list[tuple[str, bytes]], season: int | None, episode: int | None
) -> tuple[str, bytes] | None:
    """The archive member for the requested episode.

    A pack whose files carry episode markers must contain the episode, or it
    yields nothing (the first file would be the wrong episode). Without markers
    or without an episode request, a single file is used as is.
    """
    if not members:
        return None
    if season is None or episode is None:
        return members[0]
    marked = [(m, _episode_of(m[0])) for m in members]
    if not any(ep for _, ep in marked):
        return members[0] if len(members) == 1 else None
    for member, found in marked:
        if found == (season, episode):
            return member
    return None
