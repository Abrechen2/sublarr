"""A search that did not hear from every provider is not cached.

Found on the 1.19.0-rc.2 test: AnimeTosho answered in 19-30 s, past the 17 s
search timeout. The partial list without it was cached for five minutes, so
the [Forced] item's interactive search showed nothing although AnimeTosho had
seven signs & songs tracks. An early exit left the same kind of gap: its list
answered a later interactive search, which never stops early.
"""

from concurrent.futures import Future
from unittest.mock import MagicMock, patch

import pytest

from providers.base import SubtitleFormat, SubtitleResult, VideoQuery


def _result():
    return SubtitleResult(
        provider_name="opensubtitles",
        subtitle_id="1",
        language="en",
        format=SubtitleFormat.SRT,
        filename="Show.S01E04.srt",
        matches={"series", "season", "episode"},
    )


def _query():
    return VideoQuery(series_title="Show", season=1, episode=4, languages=["en"])


@pytest.fixture
def manager(app_ctx):
    from providers import ProviderManager

    return ProviderManager()


def _done(results):
    future: Future = Future()
    future.set_result((results, 5))
    return future


def _collect(manager, futures, early_exit=False, timeout=5):
    outcome: dict = {}
    results = manager._collect_provider_results(
        futures, {}, timeout, _query(), early_exit, lambda *a, **kw: None, outcome=outcome
    )
    return results, outcome


def test_every_provider_answered_is_complete(manager):
    _, outcome = _collect(manager, {_done([_result()]): "opensubtitles", _done([]): "subdl"})

    assert outcome == {"complete": True}


def test_a_provider_past_the_timeout_makes_it_incomplete(manager):
    results, outcome = _collect(
        manager, {_done([_result()]): "opensubtitles", Future(): "animetosho"}, timeout=0.05
    )

    assert len(results) == 1
    assert outcome == {"complete": False}


def test_an_early_exit_makes_it_incomplete(manager):
    def perfect(result, query):
        result.score = 500

    with patch("providers.search_coordinator.compute_score", side_effect=perfect):
        _, outcome = _collect(
            manager, {_done([_result()]): "opensubtitles", Future(): "animetosho"}, early_exit=True
        )

    assert outcome == {"complete": False}


@pytest.mark.parametrize(("complete", "cached"), [(True, 1), (False, 0)])
def test_search_caches_only_a_complete_answer(manager, complete, cached):
    def collect(*args, outcome=None, **kwargs):
        outcome["complete"] = complete
        return [_result()]

    manager._providers = {"opensubtitles": MagicMock()}
    with (
        patch.object(manager, "_try_cached_search_results", return_value=None),
        patch.object(manager, "_submit_provider_searches", return_value=({}, {})),
        patch.object(manager, "_collect_provider_results", side_effect=collect),
        patch.object(manager, "_write_search_cache") as write,
    ):
        results = manager.search(_query(), early_exit=False)

    assert len(results) == 1
    assert write.call_count == cached
