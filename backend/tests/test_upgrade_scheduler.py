"""Upgrade scheduler tests.

Tests:
- TestUpgradeSchedulerDisabled: scheduler disabled when interval=0
- TestUpgradeSchedulerScanLogic: _execute_scan filters and re-queues correctly
"""

import os
import sys
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from upgrade_scheduler import UPGRADE_SCORE_THRESHOLD, UpgradeScheduler

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_download(
    file_path="/media/ep1.mkv",
    score=300,
    fmt="srt",
    downloaded_at=None,
):
    dl = MagicMock()
    dl.file_path = file_path
    dl.score = score
    dl.format = fmt
    dl.downloaded_at = downloaded_at or (datetime.now(UTC) - timedelta(days=14)).isoformat()
    return dl


def _make_settings(interval=24, window_days=7):
    s = MagicMock()
    s.upgrade_scan_interval_hours = interval
    s.upgrade_window_days = window_days
    return s


# ── TestUpgradeSchedulerDisabled ──────────────────────────────────────────────


class TestUpgradeSchedulerDisabled:
    def test_start_does_not_run_when_interval_zero(self):
        mock_app = MagicMock()
        scheduler = UpgradeScheduler(mock_app)

        with patch("upgrade_scheduler.UpgradeScheduler._get_interval_hours", return_value=0):
            scheduler.start()

        assert not scheduler._running
        assert scheduler._timer is None

    def test_start_runs_when_interval_positive(self):
        mock_app = MagicMock()
        scheduler = UpgradeScheduler(mock_app)

        with patch("upgrade_scheduler.UpgradeScheduler._get_interval_hours", return_value=12):
            scheduler.start()

        assert scheduler._running
        assert scheduler._timer is not None
        scheduler.stop()

    def test_get_interval_reads_from_settings(self):
        mock_app = MagicMock()
        scheduler = UpgradeScheduler(mock_app)
        mock_settings = MagicMock()
        mock_settings.upgrade_scan_interval_hours = 48

        with patch("config.get_settings", return_value=mock_settings):
            result = scheduler._get_interval_hours()

        assert result == 48

    def test_get_interval_returns_default_on_error(self):
        from upgrade_scheduler import DEFAULT_INTERVAL_HOURS

        mock_app = MagicMock()
        scheduler = UpgradeScheduler(mock_app)

        with patch("config.get_settings", side_effect=RuntimeError("no settings")):
            result = scheduler._get_interval_hours()

        assert result == DEFAULT_INTERVAL_HOURS


# ── TestUpgradeSchedulerScanLogic ─────────────────────────────────────────────


class TestUpgradeSchedulerScanLogic:
    def _run_scan(self, downloads, wanted_item, settings=None):
        """Helper: run _execute_scan with mocked DB and return result dict."""
        mock_app = MagicMock()
        scheduler = UpgradeScheduler(mock_app)

        if settings is None:
            settings = _make_settings()

        mock_db = MagicMock()
        mock_db.execute.return_value.scalars.return_value.all.return_value = downloads

        mock_wanted_repo = MagicMock()
        mock_wanted_repo.get_wanted_by_file_path.return_value = wanted_item

        with (
            patch("config.get_settings", return_value=settings),
            patch("db.get_db") as mock_db_ctx,
            patch("db.repositories.wanted.WantedRepository", return_value=mock_wanted_repo),
        ):
            mock_db_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)

            result = scheduler._execute_scan()

        return result, mock_db

    def test_low_score_srt_queued(self):
        dl = _make_download(score=200, fmt="srt")
        item = {"id": 1, "status": "completed", "last_search_at": None}

        result, mock_db = self._run_scan([dl], item)

        assert result["queued"] == 1
        assert result["skipped"] == 0

    def test_high_score_ass_skipped(self):
        dl = _make_download(score=700, fmt="ass")
        item = {"id": 1, "status": "completed", "last_search_at": None}

        result, _ = self._run_scan([dl], item)

        assert result["queued"] == 0
        assert result["skipped"] == 1

    def test_low_score_ass_queued(self):
        # ASS with low score should still be queued (score criteria applies)
        dl = _make_download(score=200, fmt="ass")
        item = {"id": 1, "status": "completed", "last_search_at": None}

        result, _ = self._run_scan([dl], item)

        assert result["queued"] == 1

    def test_high_score_srt_queued(self):
        # SRT with high score: format is not ASS → queue for potential format upgrade
        dl = _make_download(score=700, fmt="srt")
        item = {"id": 1, "status": "completed", "last_search_at": None}

        result, _ = self._run_scan([dl], item)

        assert result["queued"] == 1

    def test_no_wanted_item_skipped(self):
        dl = _make_download(score=200, fmt="srt")

        result, _ = self._run_scan([dl], None)

        assert result["queued"] == 0
        assert result["skipped"] == 1

    def test_already_wanted_status_skipped(self):
        dl = _make_download(score=200, fmt="srt")
        item = {"id": 1, "status": "wanted", "last_search_at": None}

        result, _ = self._run_scan([dl], item)

        assert result["skipped"] == 1

    def test_already_searching_status_skipped(self):
        dl = _make_download(score=200, fmt="srt")
        item = {"id": 1, "status": "searching", "last_search_at": None}

        result, _ = self._run_scan([dl], item)

        assert result["skipped"] == 1

    def test_searched_recently_skipped(self):
        dl = _make_download(score=200, fmt="srt")
        recent_search = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        item = {"id": 1, "status": "completed", "last_search_at": recent_search}

        result, _ = self._run_scan([dl], item)

        assert result["skipped"] == 1

    def test_searched_long_ago_queued(self):
        dl = _make_download(score=200, fmt="srt")
        old_search = (datetime.now(UTC) - timedelta(hours=48)).isoformat()
        item = {"id": 1, "status": "completed", "last_search_at": old_search}

        result, _ = self._run_scan([dl], item)

        assert result["queued"] == 1

    def test_last_run_at_updated_after_scan(self):
        mock_app = MagicMock()
        scheduler = UpgradeScheduler(mock_app)
        assert scheduler.last_run_at is None

        mock_db = MagicMock()
        mock_db.execute.return_value.scalars.return_value.all.return_value = []

        with (
            patch("config.get_settings", return_value=_make_settings()),
            patch("db.get_db") as mock_db_ctx,
            patch("db.repositories.wanted.WantedRepository"),
        ):
            mock_db_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)
            scheduler._execute_scan()

        assert scheduler.last_run_at is not None

    def test_executing_flag_cleared_after_scan(self):
        mock_app = MagicMock()
        scheduler = UpgradeScheduler(mock_app)

        mock_db = MagicMock()
        mock_db.execute.return_value.scalars.return_value.all.return_value = []

        with (
            patch("config.get_settings", return_value=_make_settings()),
            patch("db.get_db") as mock_db_ctx,
            patch("db.repositories.wanted.WantedRepository"),
        ):
            mock_db_ctx.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)
            scheduler._execute_scan()

        assert not scheduler.is_executing

    def test_upgrade_score_threshold_constant(self):
        assert UPGRADE_SCORE_THRESHOLD == 500

    def test_ssa_format_treated_as_ass(self):
        # SSA (variant of ASS) should not trigger format-based upgrade for high-score subs
        dl = _make_download(score=700, fmt="ssa")
        item = {"id": 1, "status": "completed", "last_search_at": None}

        result, _ = self._run_scan([dl], item)

        # High score + SSA/ASS → skipped (not an upgrade candidate)
        assert result["skipped"] == 1
