"""Tests for min_attempts_per_day prefix (Phase 4a)."""

from __future__ import annotations

from unittest.mock import patch

from services.wanted_search_runner import _collect_min_attempts_items


def test_prefix_returns_oldest_searched_per_series():
    candidates = {
        100: [
            {"id": 1, "sonarr_series_id": 100, "last_search_at": None},
            {"id": 2, "sonarr_series_id": 100, "last_search_at": "2026-04-17T10:00:00+00:00"},
            {"id": 3, "sonarr_series_id": 100, "last_search_at": "2026-04-17T11:00:00+00:00"},
        ]
    }
    with (
        patch(
            "services.wanted_search_runner._series_min_attempts_config",
            return_value={100: 2},
        ),
        patch(
            "services.wanted_search_runner._series_searches_today",
            return_value={100: 0},
        ),
        patch(
            "services.wanted_search_runner._wanted_items_by_series",
            return_value=candidates,
        ),
    ):
        out = _collect_min_attempts_items()
    assert [i["id"] for i in out] == [1, 2]


def test_prefix_clamped_when_fewer_items_than_min():
    candidates = {100: [{"id": 1, "sonarr_series_id": 100, "last_search_at": None}]}
    with (
        patch(
            "services.wanted_search_runner._series_min_attempts_config",
            return_value={100: 5},
        ),
        patch(
            "services.wanted_search_runner._series_searches_today",
            return_value={100: 0},
        ),
        patch(
            "services.wanted_search_runner._wanted_items_by_series",
            return_value=candidates,
        ),
    ):
        out = _collect_min_attempts_items()
    assert len(out) == 1


def test_prefix_subtracts_already_searched_today():
    candidates = {
        100: [
            {"id": 1, "sonarr_series_id": 100, "last_search_at": None},
            {"id": 2, "sonarr_series_id": 100, "last_search_at": None},
        ]
    }
    with (
        patch(
            "services.wanted_search_runner._series_min_attempts_config",
            return_value={100: 3},
        ),
        patch(
            "services.wanted_search_runner._series_searches_today",
            return_value={100: 2},
        ),
        patch(
            "services.wanted_search_runner._wanted_items_by_series",
            return_value=candidates,
        ),
    ):
        out = _collect_min_attempts_items()
    assert len(out) == 1


def test_empty_when_no_series_have_min_configured():
    with patch(
        "services.wanted_search_runner._series_min_attempts_config",
        return_value={},
    ):
        assert _collect_min_attempts_items() == []
