"""A search no provider answered is not a miss.

Prod 2026-09-25 (1.14.5): 3 229 of 3 601 slow-mode items had a last search in
which every provider was skipped before being asked — ``rate_limited`` by the
coordinator's own sliding window, ``budget_exhausted``, ``auto_disabled`` — yet
each exit booked ``record_search_outcome(kind="no_result")``. That burns
``search_count``: three such searches push an item into slow-mode (30 days),
three more make it ``unsourceable``, without a single provider having been
asked.

Fix shape: every provider fact the coordinator records also feeds a small
per-run reach tracker (``provider_reach``), independent of whether the
decision log is enabled. When no provider answered and at least one was only
temporarily unavailable, ``record_search_outcome`` books ``provider_error``
instead: error-side backoff, no ``search_count`` charge. Permanent skips
(language not served, excluded, not applicable) still count as a real miss —
nobody could ever answer those.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

import decision_log
import provider_reach
from db.wanted import get_wanted_item, upsert_wanted_item
from services.wanted_search_outcome import record_search_outcome


@pytest.fixture
def mock_db(monkeypatch):
    get_item = MagicMock(return_value={"id": 42, "error_count": 0, "search_count": 1})
    update = MagicMock(return_value=True)
    monkeypatch.setattr("db.wanted.get_wanted_item", get_item, raising=True)
    monkeypatch.setattr("db.wanted.update_wanted_search_outcome", update, raising=True)
    return update


@pytest.fixture
def tracking():
    token = provider_reach.start()
    yield
    provider_reach.finish(token)


class TestOutcomeBooking:
    def test_all_providers_rate_limited_is_a_provider_error(self, mock_db, tracking):
        """``rate_limited`` + ``budget_exhausted`` are both own-limit reasons
        (see ``TestOwnLimitsDoNotEscalate``), so this is a fixed 6h retry with
        no ``error_count`` charge — not the escalating curve."""
        decision_log.provider_skipped("opensubtitles", "rate_limited")
        decision_log.provider_skipped("subdl", "budget_exhausted", detail="500/500")

        record_search_outcome(7, kind="no_result")

        kwargs = mock_db.call_args.kwargs
        assert kwargs["failure_kind"] == "provider_error"
        assert "error_count_increment" not in kwargs
        assert "search_count_increment" not in kwargs
        assert "opensubtitles" in kwargs["error"] and "rate_limited" in kwargs["error"]
        delta = kwargs["retry_after"] - datetime.now(UTC)
        assert timedelta(hours=5) < delta < timedelta(hours=7)

    def test_timeouts_and_errors_are_not_answers(self, mock_db, tracking):
        decision_log.provider_failed("opensubtitles", "timeout")
        decision_log.provider_failed("subdl", "error", detail="HTTP 500")
        decision_log.providers_unfinished(["animetosho"])

        record_search_outcome(7, kind="no_result")

        assert mock_db.call_args.kwargs["failure_kind"] == "provider_error"

    def test_one_answer_makes_it_a_real_miss(self, mock_db, tracking):
        decision_log.provider_skipped("opensubtitles", "rate_limited")
        decision_log.provider_searched("subdl", 0, 120.0)

        record_search_outcome(7, kind="no_result")

        kwargs = mock_db.call_args_list[0].kwargs
        assert kwargs["search_count_increment"] == 1
        assert kwargs["failure_kind"] == "no_result"

    def test_a_cache_hit_counts_as_an_answer(self, mock_db, tracking):
        decision_log.provider_skipped("opensubtitles", "rate_limited")
        decision_log.search_cache_hit(0)

        record_search_outcome(7, kind="no_result")

        assert mock_db.call_args_list[0].kwargs["search_count_increment"] == 1

    def test_only_permanent_skips_is_a_real_miss(self, mock_db, tracking):
        """A language nobody serves will never be answered — backing off on the
        error curve forever would hide it from the unsourceable escalation."""
        decision_log.provider_skipped("napisy24", "language_unsupported", detail="en")
        decision_log.provider_skipped("kitsunekko", "languages_excluded", detail="en")
        decision_log.provider_skipped("jimaku", "not_applicable")

        record_search_outcome(7, kind="no_result")

        assert mock_db.call_args_list[0].kwargs["search_count_increment"] == 1

    def test_without_tracking_the_booking_is_unchanged(self, mock_db):
        decision_log.provider_skipped("opensubtitles", "rate_limited")

        record_search_outcome(7, kind="no_result")

        assert mock_db.call_args_list[0].kwargs["search_count_increment"] == 1

    def test_the_tracker_ends_with_its_run(self, mock_db):
        token = provider_reach.start()
        decision_log.provider_skipped("opensubtitles", "rate_limited")
        provider_reach.finish(token)

        record_search_outcome(7, kind="no_result")

        assert mock_db.call_args_list[0].kwargs["search_count_increment"] == 1


class TestProcessWantedItem:
    """End to end through ``process_wanted_item`` — with the decision log
    switched OFF, so the booking cannot depend on a diagnostics setting."""

    def test_rate_limited_search_keeps_the_search_budget(self, app_ctx, monkeypatch, tmp_path):
        from config import get_settings
        from wanted_search import process_wanted_item

        monkeypatch.setattr(get_settings(), "decision_log_enabled", False, raising=False)
        mkv = tmp_path / "ep.mkv"
        mkv.touch()
        item_id, _ = upsert_wanted_item(
            item_type="episode", file_path=str(mkv), target_language="de"
        )

        def _all_rate_limited(*_a, **_kw):
            decision_log.provider_skipped("opensubtitles", "rate_limited")
            decision_log.provider_skipped("subdl", "rate_limited")
            return None

        mgr = MagicMock()
        mgr.search.side_effect = lambda *a, **kw: (_all_rate_limited(), [])[1]
        mgr.search_and_download_best.side_effect = _all_rate_limited
        monkeypatch.setattr("wanted_search.process.get_provider_manager", lambda: mgr)

        out = process_wanted_item(item_id, allow_translate_fallback=False)

        assert out.get("status") == "not_found"
        item = get_wanted_item(item_id)
        assert item["status"] == "wanted"
        assert item["failure_kind"] == "provider_error"
        assert (item.get("search_count") or 0) == 0
        # Both providers were rate_limited: a pure own-limit miss, so
        # error_count is not charged either (fixed 6h retry instead).
        assert item["error_count"] == 0


def test_forced_items_keep_the_search_budget_too(app_ctx, monkeypatch, tmp_path):
    """Forced items branch off before the steps; the tracker must cover them."""
    from db.models.core import WantedItem
    from extensions import db
    from wanted_search import process_wanted_item

    mkv = tmp_path / "ep.mkv"
    mkv.touch()
    item_id, _ = upsert_wanted_item(item_type="episode", file_path=str(mkv), target_language="de")
    row = db.session.get(WantedItem, item_id)
    row.subtitle_type = "forced"
    db.session.commit()

    def _all_rate_limited(*_a, **_kw):
        decision_log.provider_skipped("opensubtitles", "rate_limited")
        return None

    mgr = MagicMock()
    mgr.search.side_effect = lambda *a, **kw: (_all_rate_limited(), [])[1]
    mgr.search_and_download_best.side_effect = _all_rate_limited
    monkeypatch.setattr("wanted_search.process.get_provider_manager", lambda: mgr)

    process_wanted_item(item_id)

    item = get_wanted_item(item_id)
    assert item["failure_kind"] == "provider_error"
    assert (item.get("search_count") or 0) == 0


def test_a_cooling_key_pool_is_not_an_answer(mock_db, tracking):
    decision_log.provider_skipped("opensubtitles", "pool_cooling")

    record_search_outcome(7, kind="no_result")

    assert mock_db.call_args.kwargs["failure_kind"] == "provider_error"


class TestOwnLimitsDoNotEscalate:
    def test_budget_only_gets_a_fixed_retry_without_error_count(self, mock_db, tracking):
        mock_db.return_value = True
        decision_log.provider_skipped("opensubtitles", "budget_exhausted")
        decision_log.provider_skipped("subdl", "rate_limited")

        record_search_outcome(7, kind="no_result")

        kwargs = mock_db.call_args.kwargs
        assert kwargs["failure_kind"] == "provider_error"
        assert "error_count_increment" not in kwargs
        assert "search_count_increment" not in kwargs
        assert "own limits" in kwargs["error"]
        delta = kwargs["retry_after"] - datetime.now(UTC)
        assert timedelta(hours=5, minutes=59) < delta < timedelta(hours=6, minutes=1)

    def test_a_provider_fault_keeps_the_escalating_backoff(self, mock_db, tracking):
        decision_log.provider_skipped("opensubtitles", "budget_exhausted")
        decision_log.provider_skipped("animetosho", "auto_disabled")

        record_search_outcome(7, kind="no_result")

        kwargs = mock_db.call_args.kwargs
        assert kwargs["error_count_increment"] == 1
        assert "own limits" not in kwargs["error"]

    def test_a_high_error_count_does_not_stretch_an_own_limit_retry(
        self, mock_db, tracking, monkeypatch
    ):
        monkeypatch.setattr(
            "db.wanted.get_wanted_item",
            lambda _id: {"id": 7, "error_count": 4, "search_count": 1},
            raising=True,
        )
        decision_log.provider_skipped("opensubtitles", "budget_exhausted")

        record_search_outcome(7, kind="no_result")

        delta = mock_db.call_args.kwargs["retry_after"] - datetime.now(UTC)
        assert delta < timedelta(hours=6, minutes=1)
