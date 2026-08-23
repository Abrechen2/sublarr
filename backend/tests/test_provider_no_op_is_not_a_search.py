"""A provider that cannot search a query must not be recorded as having searched.

Measured on production 2026-08-23: of 4998 logged animetosho "searches", 64.9%
took 0 ms and returned 0 results. Those were not searches — the provider left
immediately through `if not search_term: return []`, 3593 times with
"insufficient search criteria - no search term". They were still counted, and
they dragged `avg_response_time_ms` from 15 567 down to 4157.

That average is what `_compute_dynamic_timeout` multiplies:
`max(5, min(4157*3/1000 + 2, 30))` = 14s — while the median *real* animetosho
search takes 16 563 ms. The ceiling ended up below the median, so 48.9% of real
searches were cut off and their results discarded.

The fix is not a bigger timeout. It is to stop counting a no-op as a search.
"""

from unittest.mock import MagicMock, patch

import pytest

from providers.base import ProviderNotApplicableError, SubtitleFormat, SubtitleResult, VideoQuery


def _result(name="animetosho", language="de"):
    return SubtitleResult(
        provider_name=name,
        subtitle_id="1",
        language=language,
        format=SubtitleFormat.SRT,
        filename="x.srt",
        score=0,
    )


class TestTheProviderCanSayItDidNotSearch:
    def test_a_query_with_nothing_to_search_for_reports_not_applicable(self, app_ctx):
        """The shape behind the 3593 production no-ops: neither an episode
        (season+episode) nor a movie (a title), so the search term stays empty
        and no request is ever made."""
        from providers.animetosho import AnimeToshoProvider

        p = AnimeToshoProvider()
        p.session = MagicMock()
        q = VideoQuery(file_path="/media/x.mkv", languages=["de"])
        assert not q.is_episode and not q.is_movie
        with pytest.raises(ProviderNotApplicableError) as exc:
            p.search(q)
        assert "search term" in str(exc.value).lower()
        p.session.get.assert_not_called()

    def test_a_title_still_searches_normally(self, app_ctx):
        from providers.animetosho import AnimeToshoProvider

        p = AnimeToshoProvider()
        p.session = MagicMock()
        p.session.get.return_value = MagicMock(status_code=200, json=lambda: [])
        q = VideoQuery(
            file_path="/media/x.mkv",
            series_title="Some Show",
            season=1,
            episode=3,
            languages=["de"],
        )
        assert p.search(q) == []
        p.session.get.assert_called()


class TestANoOpDoesNotReachTheStats:
    """The load-bearing assertion: a no-op must not move total_searches or
    avg_response_time_ms, because those two decide the provider's timeout."""

    @staticmethod
    def _run_collect(side_effect):
        from concurrent.futures import ThreadPoolExecutor

        from providers import ProviderManager

        manager = ProviderManager()
        manager._providers.clear()
        manager._circuit_breakers.clear()

        provider = MagicMock()
        provider.name = "animetosho"
        provider.search.side_effect = side_effect
        manager._providers["animetosho"] = provider

        stats_calls: list[dict] = []
        skips: list[tuple] = []

        with ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(lambda: (_ for _ in ()).throw(side_effect))
            futures = {fut: "animetosho"}
            with (
                patch(
                    "providers.search_coordinator.decision_log.provider_skipped",
                    side_effect=lambda n, r, detail="": skips.append((n, r)),
                ),
                patch(
                    "providers.search_coordinator.decision_log.provider_searched",
                    side_effect=lambda *a, **k: skips.append(("SEARCHED", a[0])),
                ),
            ):
                manager._collect_provider_results(
                    futures,
                    {},
                    5,
                    VideoQuery(file_path="/m/x.mkv", languages=["de"]),
                    False,
                    lambda *a, **k: stats_calls.append(k),
                )
        return stats_calls, skips

    def test_not_applicable_records_no_stats_at_all(self, app_ctx):
        stats, skips = self._run_collect(ProviderNotApplicableError("no search term"))
        assert stats == [], (
            "a no-op was written into provider_stats — this is the pollution that "
            "pushed the animetosho timeout below its own median"
        )
        assert ("animetosho", "not_applicable") in skips

    def test_a_real_failure_is_still_recorded(self, app_ctx):
        """Guard against over-correcting: a genuine error must keep counting."""
        stats, _ = self._run_collect(RuntimeError("boom"))
        assert stats, "a real failure must still reach the stats"
        assert stats[0].get("success") is False


class TestTheCeilingThisProtects:
    """Pins the arithmetic the production measurement exposed, so a future
    change to the formula has to confront these numbers."""

    def test_polluted_average_puts_the_ceiling_below_the_median(self, app_ctx):
        from providers import ProviderManager

        m = ProviderManager()
        # Measured on prod 2026-08-23.
        polluted = {"total_searches": 15229, "avg_response_time_ms": 4157}
        clean = {"total_searches": 1753, "avg_response_time_ms": 15567}
        median_real_ms = 16563

        with_pollution = m._compute_dynamic_timeout("animetosho", polluted)
        without = m._compute_dynamic_timeout("animetosho", clean)

        assert with_pollution * 1000 < median_real_ms, (
            "the measured situation: the ceiling sat below the median real search"
        )
        assert without * 1000 > median_real_ms, (
            "with an honest average the ceiling clears the median"
        )


class TestAnEpisodeWithoutASeriesNameIsNotSearchedFor:
    """Found while writing the tests above: the name was checked *after* the
    episode number was appended, so an episode with no series title produced
    the search term " 03" — a bare number, matched loosely across AnimeTosho's
    whole index. Not a no-op, and not a useful search either."""

    def test_a_bare_episode_number_is_never_sent(self, app_ctx):
        from providers.animetosho import AnimeToshoProvider

        p = AnimeToshoProvider()
        p.session = MagicMock()
        q = VideoQuery(file_path="/media/x.mkv", season=1, episode=3, languages=["de"])
        assert q.is_episode and not (q.series_title or q.title)

        with pytest.raises(ProviderNotApplicableError):
            p.search(q)
        p.session.get.assert_not_called()

    def test_a_named_episode_still_carries_its_number(self, app_ctx):
        from providers.animetosho import AnimeToshoProvider

        p = AnimeToshoProvider()
        p.session = MagicMock()
        p.session.get.return_value = MagicMock(status_code=200, json=lambda: [])
        q = VideoQuery(
            file_path="/media/x.mkv",
            series_title="Some Show",
            season=1,
            episode=3,
            languages=["de"],
        )
        p.search(q)
        sent = p.session.get.call_args.kwargs.get("params", {})
        assert "Some Show" in str(sent), sent
        assert "03" in str(sent), sent

    def test_a_movie_without_a_title_is_not_searched_for(self, app_ctx):
        from providers.animetosho import AnimeToshoProvider

        p = AnimeToshoProvider()
        p.session = MagicMock()
        q = VideoQuery(file_path="/media/x.mkv", year=2019, languages=["de"])
        with pytest.raises(ProviderNotApplicableError):
            p.search(q)
        p.session.get.assert_not_called()


class TestProvidersThatServeOtherLanguagesAreNotAsked:
    """The fleet-wide half of the same defect. Every language-specific adapter
    already refused a foreign-language query internally — but only after being
    submitted and timed, so each refusal counted as a 0 ms search. Measured on
    prod 2026-08-23: napisy24 29 345 "searches" averaging 0 ms, titrari 1 ms,
    kitsunekko 6 ms. Impossible numbers for an HTTP call."""

    @staticmethod
    def _manager(monkeypatch, providers):
        from providers import ProviderManager

        monkeypatch.setattr(
            "providers.ProviderManager._get_cache_backend", staticmethod(lambda: None)
        )
        m = ProviderManager()
        m._providers.clear()
        m._circuit_breakers.clear()
        for p in providers:
            m._providers[p.name] = p
        m.settings = m.settings.model_copy(
            update={"provider_budget_enabled": False, "provider_language_excludes_json": ""}
        )
        return m

    @staticmethod
    def _provider(name, languages):
        p = MagicMock()
        p.name = name
        p.languages = languages
        p.tier = "free"
        p.session = object()
        p.rate_limits = {}
        p.config_fields = []
        p.search = MagicMock(return_value=[])
        return p

    def test_a_polish_only_provider_is_not_submitted_for_a_german_search(
        self, app_ctx, monkeypatch
    ):
        polish = self._provider("napisy24", ["pl"])
        german = self._provider("opensubtitles", ["de", "en", "pl"])
        m = self._manager(monkeypatch, [polish, german])

        skips = []
        monkeypatch.setattr(
            "providers.search_coordinator.decision_log.provider_skipped",
            lambda n, r, detail="": skips.append((n, r)),
        )

        class _Exec:
            def submit(self, fn, *a, **kw):
                class F:
                    def result(self, timeout=None):
                        return ([], 0)

                    def cancel(self):
                        return True

                return F()

        futures, _ = m._submit_provider_searches(
            _Exec(), VideoQuery(file_path="/m/x.mkv", languages=["de"]), lambda n: False
        )
        submitted = set(futures.values())

        assert "napisy24" not in submitted, "a Polish-only provider was asked for German"
        assert ("napisy24", "language_unsupported") in skips
        assert "opensubtitles" in submitted, "the provider that does serve German must still run"

    def test_a_provider_declaring_no_languages_is_never_gated(self, app_ctx, monkeypatch):
        """An adapter that declares nothing may serve anything — it keeps its
        chance to answer rather than being silently excluded."""
        unknown = self._provider("customapi", [])
        m = self._manager(monkeypatch, [unknown])

        class _Exec:
            def submit(self, fn, *a, **kw):
                class F:
                    def result(self, timeout=None):
                        return ([], 0)

                    def cancel(self):
                        return True

                return F()

        futures, _ = m._submit_provider_searches(
            _Exec(), VideoQuery(file_path="/m/x.mkv", languages=["de"]), lambda n: False
        )
        assert "customapi" in set(futures.values())

    def test_an_overlapping_provider_is_still_submitted(self, app_ctx, monkeypatch):
        partial = self._provider("subdl", ["en", "de"])
        m = self._manager(monkeypatch, [partial])

        class _Exec:
            def submit(self, fn, *a, **kw):
                class F:
                    def result(self, timeout=None):
                        return ([], 0)

                    def cancel(self):
                        return True

                return F()

        futures, _ = m._submit_provider_searches(
            _Exec(), VideoQuery(file_path="/m/x.mkv", languages=["de", "fr"]), lambda n: False
        )
        assert "subdl" in set(futures.values())
