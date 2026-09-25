"""Our own rate limiter must not turn a download into a provider failure.

Prod, September 2026: 309 ``download_failed`` attempts for opensubtitles with
zero quota or API errors behind them. The shared 40-per-10s window was full of
searches, ``download_subtitle`` returned None on the limiter's refusal, and the
caller booked that as a failed download and a provider stats failure.
"""

from unittest.mock import MagicMock, patch

import pytest

import providers.download_manager as dm
from providers.download_manager import (
    DownloadRateLimitedError,
    download_subtitle,
    search_and_download_best,
)


@pytest.fixture
def short_wait(monkeypatch):
    monkeypatch.setattr(dm, "RATE_LIMIT_MAX_WAIT_S", 0.05)
    monkeypatch.setattr(dm, "_RATE_LIMIT_POLL_S", 0.005)


def _result(provider_name="opensubtitles", subtitle_id="s1", score=90):
    return MagicMock(provider_name=provider_name, subtitle_id=subtitle_id, score=score)


class TestDownloadWaitsForSlot:
    def test_waits_for_a_free_slot_then_downloads(self, monkeypatch):
        monkeypatch.setattr(dm, "RATE_LIMIT_MAX_WAIT_S", 5.0)
        monkeypatch.setattr(dm, "_RATE_LIMIT_POLL_S", 0.005)
        provider = MagicMock()
        provider.download.return_value = b"content"
        checker = MagicMock(side_effect=[False, False, True])

        ret = download_subtitle({"opensubtitles": provider}, {}, checker, _result())

        assert ret == b"content"
        assert checker.call_count == 3
        provider.download.assert_called_once()

    def test_still_refused_raises_when_asked(self, short_wait):
        provider = MagicMock()

        with pytest.raises(DownloadRateLimitedError):
            download_subtitle(
                {"opensubtitles": provider},
                {},
                MagicMock(return_value=False),
                _result(),
                raise_skips=True,
            )
        provider.download.assert_not_called()

    def test_still_refused_returns_none_by_default(self, short_wait):
        provider = MagicMock()
        breaker = MagicMock()
        breaker.allow_request.return_value = True

        ret = download_subtitle(
            {"opensubtitles": provider},
            {"opensubtitles": breaker},
            MagicMock(return_value=False),
            _result(),
        )

        assert ret is None
        provider.download.assert_not_called()
        breaker.record_failure.assert_not_called()

    def test_stop_request_ends_the_wait(self, monkeypatch):
        monkeypatch.setattr(dm, "RATE_LIMIT_MAX_WAIT_S", 30.0)
        monkeypatch.setattr(dm, "_RATE_LIMIT_POLL_S", 0.005)
        checker = MagicMock(return_value=False)

        with (
            patch("services.scheduler.cancellation.abort_requested", return_value=True),
            pytest.raises(DownloadRateLimitedError),
        ):
            download_subtitle(
                {"opensubtitles": MagicMock()},
                {},
                checker,
                _result(),
                raise_skips=True,
            )
        assert checker.call_count == 1


class TestSearchAndDownloadBestRateLimited:
    def test_rate_limited_is_not_a_provider_failure(self):
        limited = _result("opensubtitles", "os1", 95)
        other = _result("jimaku", "j1", 80)
        download_fn = MagicMock(side_effect=[DownloadRateLimitedError("full"), b"content"])
        stats_fn = MagicMock()

        with (
            patch("providers.reranker.apply_auto_reranking"),
            patch.object(dm, "decision_log") as dlog,
        ):
            ret = search_and_download_best(
                MagicMock(return_value=[limited, other]), download_fn, stats_fn, "query"
            )

        assert ret is other
        stats_fn.assert_called_once_with("jimaku", success=True, score=80)
        statuses = [c.args[2] for c in dlog.download_attempt.call_args_list]
        assert statuses == ["rate_limited", "selected"]

    def test_further_results_of_a_limited_provider_are_not_retried(self):
        first = _result("opensubtitles", "os1", 95)
        second = _result("opensubtitles", "os2", 90)
        download_fn = MagicMock(side_effect=DownloadRateLimitedError("full"))
        stats_fn = MagicMock()

        with patch.object(dm, "decision_log") as dlog:
            ret = search_and_download_best(
                MagicMock(return_value=[first, second]), download_fn, stats_fn, "query"
            )

        assert ret is None
        assert download_fn.call_count == 1
        stats_fn.assert_not_called()
        statuses = [c.args[2] for c in dlog.download_attempt.call_args_list]
        assert statuses == ["rate_limited", "rate_limited"]


class TestProviderManagerWiring:
    def test_manager_search_and_download_books_rate_limited(self, short_wait):
        from providers import ProviderManager

        manager = ProviderManager.__new__(ProviderManager)
        provider = MagicMock()
        manager._providers = {"opensubtitles": provider}
        manager._circuit_breakers = {}
        manager._check_rate_limit = MagicMock(return_value=False)
        manager.search_with_fallback = MagicMock(return_value=[_result()])

        with (
            patch("db.providers.update_provider_stats") as stats,
            patch.object(dm, "decision_log") as dlog,
        ):
            ret = manager.search_and_download_best(MagicMock())

        assert ret is None
        provider.download.assert_not_called()
        stats.assert_not_called()
        statuses = [c.args[2] for c in dlog.download_attempt.call_args_list]
        assert statuses == ["rate_limited"]
