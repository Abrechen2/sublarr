"""Tests for the auto-mark-as-unsourceable escalation in record_search_outcome.

V1 introduced a bounded slow-mode escalation: an item that has cycled through
N slow-mode no_result attempts is moved out of the wanted queue entirely by
setting ``status='unsourceable'``. This avoids the indefinite "always 2084
items in wanted, never shrinks" UX wart that existed when slow-mode was the
terminal state.

These tests pin down the boundary conditions so a future tweak to backoff
math doesn't accidentally re-introduce the indefinite-slow-mode regression.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from services.wanted_search_outcome import record_search_outcome


@pytest.fixture
def mock_db(monkeypatch):
    """Patch the two DB helpers record_search_outcome reaches into."""
    get_item = MagicMock()
    update = MagicMock(return_value=True)

    def _patch():
        monkeypatch.setattr("db.wanted.get_wanted_item", get_item, raising=True)
        monkeypatch.setattr("db.wanted.update_wanted_search_outcome", update, raising=True)

    _patch()
    return {"get_wanted_item": get_item, "update": update}


@pytest.fixture
def settings_factory(monkeypatch):
    """Build a settings stub with the two thresholds we care about."""

    def _build(*, max_attempts: int = 3, max_slow_cycles: int = 3):
        s = MagicMock()
        s.wanted_max_search_attempts = max_attempts
        s.wanted_search_max_slow_cycles = max_slow_cycles
        s.wanted_backoff_base_hours = 1.0
        s.wanted_backoff_cap_hours = 168
        monkeypatch.setattr("services.wanted_search_outcome.get_settings", lambda: s, raising=True)
        return s

    return _build


class TestSlowModeEscalation:
    def test_first_slow_cycle_stays_in_slow_mode(self, mock_db, settings_factory):
        """sc=3 (just hit max_attempts) → enters slow-mode, NOT unsourceable."""
        settings_factory(max_attempts=3, max_slow_cycles=3)
        # After increment, item is at sc=3 (the threshold for slow-mode entry).
        mock_db["get_wanted_item"].return_value = {
            "id": 42,
            "search_count": 3,
            "failure_kind": "no_result",
        }

        record_search_outcome(42, kind="no_result")

        # Two updates: first the increment+failure_kind, then the slow-mode
        # patch (failure_kind='no_result_slow', retry_after=+30d).
        last_call_kwargs = mock_db["update"].call_args_list[-1].kwargs
        assert last_call_kwargs["failure_kind"] == "no_result_slow"
        assert "status" not in last_call_kwargs
        # 30-day retry, give a generous window for clock drift.
        delta = last_call_kwargs["retry_after"] - datetime.now(UTC)
        assert timedelta(days=29) < delta < timedelta(days=31)

    def test_late_slow_cycle_stays_in_slow_mode(self, mock_db, settings_factory):
        """sc=5 (2 slow cycles done) still slow-mode — escalation only at sc>=6."""
        settings_factory(max_attempts=3, max_slow_cycles=3)
        mock_db["get_wanted_item"].return_value = {
            "id": 42,
            "search_count": 5,
            "failure_kind": "no_result_slow",
        }

        record_search_outcome(42, kind="no_result")

        last_call_kwargs = mock_db["update"].call_args_list[-1].kwargs
        assert last_call_kwargs["failure_kind"] == "no_result_slow"
        assert "status" not in last_call_kwargs

    def test_threshold_slow_cycle_escalates_to_unsourceable(self, mock_db, settings_factory):
        """sc=6 (max_attempts=3 + max_slow_cycles=3) → status='unsourceable'."""
        settings_factory(max_attempts=3, max_slow_cycles=3)
        mock_db["get_wanted_item"].return_value = {
            "id": 42,
            "search_count": 6,
            "failure_kind": "no_result_slow",
        }

        record_search_outcome(42, kind="no_result")

        last_call_kwargs = mock_db["update"].call_args_list[-1].kwargs
        assert last_call_kwargs["status"] == "unsourceable"
        assert last_call_kwargs["failure_kind"] == "unsourceable"
        # No future retry — the scheduler shouldn't pick it up again.
        assert last_call_kwargs["retry_after"] is None

    def test_far_above_threshold_still_unsourceable(self, mock_db, settings_factory):
        """sc=99 should still terminate as unsourceable, not crash."""
        settings_factory(max_attempts=3, max_slow_cycles=3)
        mock_db["get_wanted_item"].return_value = {
            "id": 42,
            "search_count": 99,
            "failure_kind": "no_result_slow",
        }

        record_search_outcome(42, kind="no_result")

        last_call_kwargs = mock_db["update"].call_args_list[-1].kwargs
        assert last_call_kwargs["status"] == "unsourceable"

    def test_max_slow_cycles_zero_escalates_immediately_after_attempts(
        self, mock_db, settings_factory
    ):
        """max_slow_cycles=0 → no slow-mode at all, jump straight to unsourceable."""
        settings_factory(max_attempts=3, max_slow_cycles=0)
        mock_db["get_wanted_item"].return_value = {
            "id": 42,
            "search_count": 3,
            "failure_kind": "no_result",
        }

        record_search_outcome(42, kind="no_result")

        last_call_kwargs = mock_db["update"].call_args_list[-1].kwargs
        assert last_call_kwargs["status"] == "unsourceable"

    def test_normal_retry_path_unaffected(self, mock_db, settings_factory):
        """sc=1 (well below max_attempts) → normal exponential backoff."""
        settings_factory(max_attempts=3, max_slow_cycles=3)
        mock_db["get_wanted_item"].return_value = {
            "id": 42,
            "search_count": 1,
            "failure_kind": "no_result",
        }

        record_search_outcome(42, kind="no_result")

        last_call_kwargs = mock_db["update"].call_args_list[-1].kwargs
        assert last_call_kwargs["failure_kind"] == "no_result"
        assert "status" not in last_call_kwargs
        # 1h backoff at sc=1
        delta = last_call_kwargs["retry_after"] - datetime.now(UTC)
        assert timedelta(minutes=55) < delta < timedelta(minutes=65)

    def test_provider_error_does_not_escalate(self, mock_db, settings_factory):
        """provider_error path is independent — never marks unsourceable."""
        settings_factory(max_attempts=3, max_slow_cycles=3)
        mock_db["get_wanted_item"].return_value = {
            "id": 42,
            "search_count": 99,  # very high but irrelevant for provider_error
            "error_count": 0,
        }

        record_search_outcome(42, kind="provider_error", error_message="boom")

        # Should call update once with provider_error backoff, never with status=
        for call in mock_db["update"].call_args_list:
            assert call.kwargs.get("status") != "unsourceable"
