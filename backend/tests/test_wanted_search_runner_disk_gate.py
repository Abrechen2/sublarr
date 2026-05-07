"""Integration tests for the disk safety-valve in wanted_search_runner.

Covers the interaction between ``services.disk_safety`` and
``run_wanted_search``:
- Critical disk → early return with ``paused_reason="disk_critical"`` and
  no provider/DB calls.
- Healthy disk → normal pipeline executes (mocked).
- Threshold ≥ 100 disables the gate.
"""

from collections import namedtuple
from unittest.mock import MagicMock, patch

import pytest

from services.wanted_search_runner import run_wanted_search

DiskUsage = namedtuple("usage", ["total", "used", "free"])


def _fake_usage(used_pct: float) -> DiskUsage:
    total = 100 * 1024 * 1024 * 1024
    used = int(total * (used_pct / 100.0))
    return DiskUsage(total=total, used=used, free=total - used)


@pytest.fixture
def settings_with_threshold(monkeypatch):
    """Patch get_settings everywhere run_wanted_search reads them."""

    def _build(threshold: float):
        s = MagicMock()
        s.config_dir = "/config"
        s.wanted_search_disk_pause_pct = threshold
        s.wanted_search_max_items_per_run = 10
        s.wanted_search_order = "fair"
        s.wanted_scheduler_backlog_reserve_pct = 50
        s.upgrade_scan_interval_hours = 0
        monkeypatch.setattr("services.wanted_search_runner.get_settings", lambda: s, raising=True)
        return s

    return _build


class TestDiskGate:
    def test_critical_disk_pauses_search(self, settings_with_threshold):
        settings_with_threshold(threshold=98.0)
        with (
            patch("shutil.disk_usage", return_value=_fake_usage(used_pct=99.0)),
            patch("db.wanted.get_items_for_scheduled_search") as mock_fetch,
        ):
            result = run_wanted_search(app=None, socketio=None, cancel_event=None)

        assert result["paused_reason"] == "disk_critical"
        assert result["total"] == 0
        assert result["processed"] == 0
        assert "%" in result["disk_pct"]
        # The DB lookup must NOT have been issued — that proves we early-returned
        # before touching providers / sessions.
        mock_fetch.assert_not_called()

    def test_healthy_disk_runs_pipeline(self, settings_with_threshold):
        settings_with_threshold(threshold=98.0)
        with (
            patch("shutil.disk_usage", return_value=_fake_usage(used_pct=70.0)),
            patch("services.provider_budget.get_budget_manager") as mock_budget,
            patch("db.wanted.get_items_for_scheduled_search", return_value=[]),
        ):
            mock_budget.return_value.tick_recovery = MagicMock()
            result = run_wanted_search(app=None, socketio=None, cancel_event=None)

        assert "paused_reason" not in result
        assert result["total"] == 0  # empty pipeline, but executed

    def test_threshold_at_100_disables_gate(self, settings_with_threshold):
        settings_with_threshold(threshold=100.0)
        with (
            patch("shutil.disk_usage", return_value=_fake_usage(used_pct=99.9)),
            patch("services.provider_budget.get_budget_manager") as mock_budget,
            patch("db.wanted.get_items_for_scheduled_search", return_value=[]),
        ):
            mock_budget.return_value.tick_recovery = MagicMock()
            result = run_wanted_search(app=None, socketio=None, cancel_event=None)

        assert "paused_reason" not in result

    def test_unreadable_path_does_not_pause(self, settings_with_threshold):
        settings_with_threshold(threshold=98.0)
        with (
            patch("shutil.disk_usage", side_effect=FileNotFoundError("nope")),
            patch("services.provider_budget.get_budget_manager") as mock_budget,
            patch("db.wanted.get_items_for_scheduled_search", return_value=[]),
        ):
            mock_budget.return_value.tick_recovery = MagicMock()
            result = run_wanted_search(app=None, socketio=None, cancel_event=None)

        # An unreadable mount-point must NOT silently halt downloads — the
        # gate is conservative on missing data.
        assert "paused_reason" not in result
