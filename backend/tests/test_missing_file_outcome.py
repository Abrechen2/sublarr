"""A missing media file is a transient environment fault, not a terminal one.

RC 2026-08-20: one scheduler tick over a DB mirror whose media files do not
exist flipped 1,246 rows to ``status='failed'`` with NO ``failure_kind`` —
the same dead-end class as the 2026-08-01 prod incident (unreadable season
dirs), because the search selector never picks ``'failed'`` again. A file
that vanishes is usually a mount or permission problem, so the item now goes
back to ``'wanted'`` under ``failure_kind='file_missing'`` with the
provider-error backoff curve (6h → 24h → 3d → 7d → 30d cap): a returning
mount self-heals, a file gone for good idles at the 30-day cap instead of
poisoning the failed bucket.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from db.wanted import get_wanted_item, upsert_wanted_item
from services.wanted_search_outcome import record_search_outcome


class TestRecordOutcomeFileMissing:
    """Unit level: the new outcome kind writes the right columns."""

    @pytest.fixture
    def mock_db(self, monkeypatch):
        get_item = MagicMock(return_value={"id": 42, "error_count": 0})
        update = MagicMock(return_value=True)
        monkeypatch.setattr("db.wanted.get_wanted_item", get_item, raising=True)
        monkeypatch.setattr("db.wanted.update_wanted_search_outcome", update, raising=True)
        return {"get_wanted_item": get_item, "update": update}

    def test_first_miss_gets_error_backoff_not_search_charge(self, mock_db):
        record_search_outcome(7, kind="file_missing", error_message="File not found: /x.mkv")

        kwargs = mock_db["update"].call_args.kwargs
        assert kwargs["failure_kind"] == "file_missing"
        assert kwargs["error_count_increment"] == 1
        assert "search_count_increment" not in kwargs
        assert "status" not in kwargs
        assert kwargs["error"].startswith("File not found")
        delta = kwargs["retry_after"] - datetime.now(UTC)
        assert timedelta(hours=5) < delta < timedelta(hours=7)

    def test_repeat_misses_walk_the_error_backoff_curve(self, mock_db):
        mock_db["get_wanted_item"].return_value = {"id": 42, "error_count": 2}

        record_search_outcome(7, kind="file_missing")

        kwargs = mock_db["update"].call_args.kwargs
        delta = kwargs["retry_after"] - datetime.now(UTC)
        assert timedelta(days=2, hours=23) < delta < timedelta(days=3, hours=1)


class TestProcessPathFileMissing:
    """Integration level: the search path books the outcome and does not
    write the terminal ``failed`` status any more."""

    def _make_item_with_vanished_file(self, tmp_path):
        mkv = tmp_path / "ep.mkv"
        mkv.touch()
        row_id, _ = upsert_wanted_item(
            item_type="episode",
            file_path=str(mkv),
            target_language="de",
        )
        mkv.unlink()
        return row_id

    def test_missing_file_returns_to_rotation_with_backoff(self, app_ctx, tmp_path):
        from wanted_search import process_wanted_item

        item_id = self._make_item_with_vanished_file(tmp_path)

        out = process_wanted_item(item_id)

        assert out.get("status") == "skipped"
        assert out.get("reason") == "file_missing"
        item = get_wanted_item(item_id)
        assert item["status"] == "wanted", "a missing file must not be terminal"
        assert item["failure_kind"] == "file_missing"
        assert (item.get("error_count") or 0) == 1
        assert (item.get("search_count") or 0) == 0, "no provider was asked — no charge"
        assert item["retry_after"] is not None, "a miss earns a backoff, not a hot loop"
