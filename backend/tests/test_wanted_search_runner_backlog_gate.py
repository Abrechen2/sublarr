"""Backlog reserve gate — skip backlog items when budget is >50% spent."""

from __future__ import annotations

from services.wanted_search_runner import _apply_backlog_reserve_gate


def test_backlog_items_dropped_when_any_provider_above_threshold():
    items = [
        {"id": 1, "priority": "premium"},
        {"id": 2, "priority": "standard"},
        {"id": 3, "priority": "backlog"},
    ]
    budget_states = [
        # opensubtitles at 60% of effective limit
        {"usage": {"day": 600}, "limits": {"day": 1000}},
        # subdl at 10%
        {"usage": {"day": 10}, "limits": {"day": 100}},
    ]
    result = _apply_backlog_reserve_gate(items, budget_states, reserve_pct=50)
    assert [i["id"] for i in result] == [1, 2]


def test_backlog_kept_when_all_providers_below_threshold():
    items = [{"id": 3, "priority": "backlog"}]
    budget_states = [
        {"usage": {"day": 400}, "limits": {"day": 1000}},
        {"usage": {"day": 10}, "limits": {"day": 100}},
    ]
    result = _apply_backlog_reserve_gate(items, budget_states, reserve_pct=50)
    assert [i["id"] for i in result] == [3]


def test_missing_day_limit_treated_as_zero_usage():
    items = [{"id": 3, "priority": "backlog"}]
    budget_states = [{"usage": {}, "limits": {}}]
    result = _apply_backlog_reserve_gate(items, budget_states, reserve_pct=50)
    assert [i["id"] for i in result] == [3]


def test_min_prefix_items_survive_backlog_gate():
    items = [
        {"id": 10, "priority": "backlog"},  # normally dropped
        {"id": 20, "priority": "premium"},
    ]
    budget_states = [{"usage": {"day": 600}, "limits": {"day": 1000}}]  # above 50%
    result = _apply_backlog_reserve_gate(items, budget_states, reserve_pct=50, exempt_ids={10})
    assert [i["id"] for i in result] == [10, 20]
