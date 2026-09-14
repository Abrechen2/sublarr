"""The search cache must not answer one show's query with another show's results.

Found on production 2026-09-14: a search for "Frieren" came back with Doctor
Who subtitles. The key was built from file_path, languages, format, anidb_id,
the profile's provider list, its scoring preset and the language exclusions —
but not from what was actually being looked for. Two searches for different
series therefore collided whenever file_path was empty and no AniDB id was
known, and the documented API endpoint makes file_path optional.

Callers that pass a file_path were never affected: the path identifies the
episode on its own. That is why the wanted queue never showed it and only a
bare API search did.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from providers.base import VideoQuery
from providers.search_coordinator.cache import SearchCacheMixin


class _Keyer(SearchCacheMixin):
    """The key helper depends on nothing but the exclusions lookup."""

    def _get_language_excludes(self):
        return {}


def _key(**kw):
    return _Keyer()._make_cache_key(VideoQuery(languages=["en"], **kw))


def test_two_different_series_do_not_share_an_entry():
    frieren = _key(series_title="Frieren", title="Frieren", season=1, episode=1)
    who = _key(series_title="Doctor Who", title="Doctor Who", season=1, episode=1)

    assert frieren != who, "a search for one series answered with another series' results"


def test_two_episodes_of_one_series_do_not_share_an_entry():
    first = _key(series_title="Frieren", season=1, episode=1)
    second = _key(series_title="Frieren", season=1, episode=2)

    assert first != second


def test_two_seasons_do_not_share_an_entry():
    s1 = _key(series_title="Frieren", season=1, episode=1)
    s2 = _key(series_title="Frieren", season=2, episode=1)

    assert s1 != s2


def test_a_movie_year_separates_two_films_of_the_same_name():
    old = _key(title="Dune", year=1984)
    new = _key(title="Dune", year=2021)

    assert old != new


def test_external_ids_separate_entries():
    a = _key(title="Dune", imdb_id="tt0087182")
    b = _key(title="Dune", imdb_id="tt1160419")

    assert a != b


def test_the_same_search_still_hits_its_own_entry():
    """Guard: the key must stay stable, or the cache never serves anything."""
    first = _key(series_title="Frieren", season=1, episode=1)
    second = _key(series_title="Frieren", season=1, episode=1)

    assert first == second


def test_a_file_path_still_separates_entries():
    """Guard for the callers that were never affected."""
    a = _key(file_path="/media/a.mkv")
    b = _key(file_path="/media/b.mkv")

    assert a != b
