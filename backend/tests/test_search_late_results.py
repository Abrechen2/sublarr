"""A provider's answer that came after the search stopped waiting is kept.

Prod 2026-11-03: AnimeTosho answered a cold season-batch search in 28 s, the
search gave up at 23 s, and the only English ASS of the episode was thrown
away — on every search, so the automatic search never saw it.
"""

from concurrent.futures import Future
from unittest.mock import MagicMock, patch

import pytest

from providers.base import SubtitleFormat, SubtitleResult, VideoQuery
from providers.search_coordinator import late_results


@pytest.fixture(autouse=True)
def _empty_store():
    late_results.clear()
    yield
    late_results.clear()


def _result(language="en", sid="1"):
    return SubtitleResult(
        provider_name="animetosho",
        subtitle_id=sid,
        language=language,
        format=SubtitleFormat.ASS,
        filename="Show.S01E04.ass",
        matches={"series", "season", "episode"},
    )


def _query():
    return VideoQuery(
        series_title="Show", season=1, episode=4, languages=["en"], file_path="/media/e.mkv"
    )


class TestStore:
    def test_an_answer_is_taken_once(self):
        late_results.put("q", "animetosho", [_result()])
        assert len(late_results.take("q", "animetosho")) == 1
        assert late_results.take("q", "animetosho") is None

    def test_answers_are_per_query_and_provider(self):
        late_results.put("q", "animetosho", [_result()])
        assert late_results.take("other", "animetosho") is None
        assert late_results.take("q", "subdl") is None

    def test_an_old_answer_expires(self):
        with patch.object(late_results.time, "monotonic", return_value=1000.0):
            late_results.put("q", "animetosho", [_result()])
        with patch.object(late_results.time, "monotonic", return_value=1000.0 + late_results.TTL_S):
            assert late_results.take("q", "animetosho") is None


class TestCapture:
    def test_a_late_answer_is_kept_and_its_video_searched_again(self, app_ctx):
        future: Future = Future()
        with patch("services.suspect_sidecars._clear_backoff") as clear_backoff:
            late_results.capture(future, "q", "animetosho", _query(), None)
            future.set_result(([_result()], 28000))

        assert len(late_results.take("q", "animetosho")) == 1
        clear_backoff.assert_called_once_with("/media/e.mkv", "en")

    def test_excluded_languages_stay_out(self):
        future: Future = Future()
        late_results.capture(future, "q", "animetosho", _query(), {"vi"})
        with patch("services.suspect_sidecars._clear_backoff"):
            future.set_result(([_result("vi", "1"), _result("en", "2")], 28000))

        assert [r.subtitle_id for r in late_results.take("q", "animetosho")] == ["2"]

    def test_an_empty_answer_is_kept_but_triggers_nothing(self, app_ctx):
        future: Future = Future()
        with patch("services.suspect_sidecars._clear_backoff") as clear_backoff:
            late_results.capture(future, "q", "animetosho", _query(), None)
            future.set_result(([], 28000))

        assert late_results.take("q", "animetosho") == []
        clear_backoff.assert_not_called()

    def test_a_failed_search_keeps_nothing(self):
        future: Future = Future()
        late_results.capture(future, "q", "animetosho", _query(), None)
        future.set_exception(RuntimeError("boom"))

        assert late_results.take("q", "animetosho") is None


@pytest.fixture
def manager(app_ctx):
    from providers import ProviderManager

    return ProviderManager()


def _search(manager, futures, collected):
    def collect(*args, outcome=None, **kwargs):
        outcome["complete"] = not any(not f.done() for f in futures)
        return list(collected)

    with (
        patch.object(manager, "_try_cached_search_results", return_value=None),
        patch.object(manager, "_submit_provider_searches", return_value=(futures, {})) as submit,
        patch.object(manager, "_collect_provider_results", side_effect=collect),
        patch.object(manager, "_write_search_cache"),
        patch.object(manager, "_finalise_search_results", side_effect=lambda r, *a: r),
    ):
        results = manager.search(_query(), early_exit=False)
    return results, submit


def test_the_next_search_takes_the_late_answer_instead_of_asking_again(manager):
    manager._providers = {"opensubtitles": MagicMock(), "animetosho": MagicMock()}
    fast: Future = Future()
    fast.set_result(([], 5))
    slow: Future = Future()

    first, _ = _search(manager, {fast: "opensubtitles", slow: "animetosho"}, [])
    assert first == []
    with patch("services.suspect_sidecars._clear_backoff"):
        slow.set_result(([_result()], 28000))

    again: Future = Future()
    again.set_result(([], 5))
    second, submit = _search(manager, {again: "opensubtitles"}, [])

    assert [r.subtitle_id for r in second] == ["1"]
    assert submit.call_args.args[3] == frozenset({"animetosho"})
