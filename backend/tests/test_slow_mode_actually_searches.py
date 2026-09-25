"""Slow-mode must search, and a transient fault must not freeze an item.

Prod 2026-09-25 (1.14.5): of 107 slow-mode items at ``search_count=4``, 105 had
their count bumped more than a day after their last decision log — no search
had run. ``_check_max_search_attempts`` fires before the search for every item
at or over the cap, so a slow-mode item whose 30-day window elapsed was booked
another ``no_result`` and skipped: slow-mode was a three-month countdown to
``unsourceable`` that never asked a provider.

Second half: ``is_exhausted`` only kept ``no_result_slow`` alive at the cap. An
item at the cap that then hit a transient fault (``provider_error``,
``file_missing``, ``translation_error`` — all of which keep ``search_count``)
lost the marker and read as exhausted forever.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from db.models.core import WantedItem
from db.wanted import get_wanted_item, upsert_wanted_item
from extensions import db
from services.wanted_search_filters import is_exhausted

_WINDOW = "2026-09-20T00:00:00+00:00"


class TestIsExhausted:
    @pytest.mark.parametrize("kind", ["provider_error", "file_missing", "translation_error"])
    def test_a_transient_fault_at_the_cap_keeps_the_item_alive(self, kind):
        assert (
            is_exhausted(search_count=3, failure_kind=kind, retry_after=_WINDOW, max_attempts=3)
            is False
        )

    def test_a_transient_fault_without_a_window_still_does_not_save_it(self):
        assert (
            is_exhausted(
                search_count=3, failure_kind="provider_error", retry_after=None, max_attempts=3
            )
            is True
        )


def _seed(tmp_path, *, search_count, failure_kind, retry_after):
    mkv = tmp_path / "ep.mkv"
    mkv.touch()
    item_id, _ = upsert_wanted_item(item_type="episode", file_path=str(mkv), target_language="de")
    row = db.session.get(WantedItem, item_id)
    row.search_count = search_count
    row.failure_kind = failure_kind
    row.retry_after = retry_after
    db.session.commit()
    return item_id


def _manager(monkeypatch):
    mgr = MagicMock()
    mgr.search.return_value = []
    mgr.search_and_download_best.return_value = None
    monkeypatch.setattr("wanted_search.process.get_provider_manager", lambda: mgr)
    return mgr


class TestSlowModeSearches:
    def test_a_due_slow_mode_item_is_searched(self, app_ctx, monkeypatch, tmp_path):
        from wanted_search import process_wanted_item

        item_id = _seed(
            tmp_path,
            search_count=3,
            failure_kind="no_result_slow",
            retry_after=datetime.now(UTC) - timedelta(hours=1),
        )
        mgr = _manager(monkeypatch)

        process_wanted_item(item_id, allow_translate_fallback=False)

        assert mgr.search_and_download_best.called or mgr.search.called, (
            "a slow-mode item whose window elapsed must reach the providers"
        )
        item = get_wanted_item(item_id)
        assert item["search_count"] == 4
        assert item["failure_kind"] == "no_result_slow"

    def test_an_item_retrying_a_fault_at_the_cap_is_searched(self, app_ctx, monkeypatch, tmp_path):
        from wanted_search import process_wanted_item

        item_id = _seed(
            tmp_path,
            search_count=3,
            failure_kind="provider_error",
            retry_after=datetime.now(UTC) - timedelta(hours=1),
        )
        mgr = _manager(monkeypatch)

        process_wanted_item(item_id, allow_translate_fallback=False)

        assert mgr.search_and_download_best.called or mgr.search.called

    def test_a_legacy_row_at_the_cap_is_still_parked_without_a_search(
        self, app_ctx, monkeypatch, tmp_path
    ):
        """No marker at the cap is the legacy shape: park it in slow-mode, as before."""
        from wanted_search import process_wanted_item

        item_id = _seed(tmp_path, search_count=3, failure_kind=None, retry_after=None)
        mgr = _manager(monkeypatch)

        out = process_wanted_item(item_id, allow_translate_fallback=False)

        assert out["status"] == "skipped"
        assert not mgr.search_and_download_best.called and not mgr.search.called
        item = get_wanted_item(item_id)
        assert item["failure_kind"] == "no_result_slow"
