"""A pack range GuessIt parsed loosely must not take the search down with it.

`match_release` compares a requested episode against the range in a pack title
(`min(episode) <= target <= max(episode)`). The list comes from GuessIt and is
not reliably numeric — prod 2026-09-28 07:16 raised out of `min()` itself:

    providers.animetosho: AnimeTosho search error:
      '<' not supported between instances of 'int' and 'str'
      File "/app/providers/animetosho_matching.py", line 79, in match_release
        if not allow_pack or not min(episode) <= target <= max(episode):
                                 ^^^^^^^^^^^^

The exception was caught upstream, so the search carried on and that log line
was the only trace. That is what makes it worth a test: the visible cost was an
entry quietly dropping out of the match, so a pack that should have been
inspected never was, and no count anywhere moved.

Note the reachability condition — `match_release` returns early when
`query.episode is None`, so every case here sets one. That is also why `target`
cannot actually be None at the comparison; the guard for it is defence, not a
scenario.
"""

import pytest

from providers.animetosho_matching import match_release


class _Query:
    def __init__(self, episode=None, absolute_episode=None, season=None, year=None, title="Show"):
        self.episode = episode
        self.absolute_episode = absolute_episode
        self.season = season
        self.year = year
        self.title = title
        self.series_title = title


def _parsed_as(monkeypatch, episode_value):
    """Pin GuessIt's answer — its output varies by title and version."""
    import providers.animetosho_matching as m

    monkeypatch.setattr(m, "guessit", lambda *_a, **_k: {"episode": episode_value, "title": "Show"})


class TestAMixedRangeDoesNotRaise:
    @pytest.mark.parametrize(
        "episode_list",
        [[1, "5"], ["01", 2], ["a", "b"], [], ["12"], [1, None]],
        ids=["int+str", "str+int", "all-str-nonnumeric", "empty", "numeric-str", "int+None"],
    )
    def test_every_shape_of_list_is_a_verdict_not_an_exception(self, episode_list, monkeypatch):
        _parsed_as(monkeypatch, episode_list)
        result = match_release("Show", _Query(episode=12, title="Show"), allow_pack=True)
        assert result is None or isinstance(result, set)

    def test_the_prod_shape_specifically(self, monkeypatch):
        """[1, '5'] — the list that raised on 2026-09-28."""
        _parsed_as(monkeypatch, [1, "5"])
        assert match_release("Show", _Query(episode=3, title="Show"), allow_pack=True) is not None

    def test_a_numeric_string_still_counts_as_a_bound(self, monkeypatch):
        """'01' is a number a human would read as one; dropping it would shrink
        the range and silently reject packs that do contain the episode."""
        _parsed_as(monkeypatch, ["01", 366])
        assert match_release("Show", _Query(episode=12, title="Show"), allow_pack=True) is not None


class TestTheFeatureStillWorks:
    def test_a_target_inside_a_numeric_range_matches(self, monkeypatch):
        _parsed_as(monkeypatch, [1, 366])
        assert match_release("Show", _Query(episode=12, title="Show"), allow_pack=True) is not None

    def test_a_target_outside_the_range_does_not(self, monkeypatch):
        _parsed_as(monkeypatch, [1, 10])
        assert match_release("Show", _Query(episode=99, title="Show"), allow_pack=True) is None

    def test_a_pack_is_refused_when_packs_are_not_allowed(self, monkeypatch):
        _parsed_as(monkeypatch, [1, 366])
        assert match_release("Show", _Query(episode=12, title="Show"), allow_pack=False) is None

    def test_a_list_with_no_usable_number_is_not_a_match(self, monkeypatch):
        """Better a miss than a range invented from nothing."""
        _parsed_as(monkeypatch, ["a", "b"])
        assert match_release("Show", _Query(episode=12, title="Show"), allow_pack=True) is None
