"""Verify run_wanted_search honours the configured order preset."""

from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture
def captured():
    return {}


def _fake_selector(captured):
    def _select(limit, order):
        captured["limit"] = limit
        captured["order"] = order
        return []

    return _select


def test_run_wanted_search_uses_configured_order(app_ctx, captured, monkeypatch):
    from config import get_settings
    from services.wanted_search_runner import _ELIGIBILITY_FETCH_CAP

    s = get_settings()
    monkeypatch.setattr(s, "wanted_search_order", "fair", raising=False)
    monkeypatch.setattr(s, "wanted_search_max_items_per_run", 100, raising=False)

    with patch("db.wanted.get_items_for_scheduled_search", side_effect=_fake_selector(captured)):
        from services.wanted_search_runner import run_wanted_search

        run_wanted_search()

    # The fetch limit is decoupled from max_items_per_run (see
    # _ELIGIBILITY_FETCH_CAP) so the eligibility filter always sees the full
    # candidate pool; max_items only bounds the per-tick workload afterwards.
    assert captured == {"limit": _ELIGIBILITY_FETCH_CAP, "order": "fair"}


def test_run_wanted_search_falls_back_to_fair_when_order_missing(app_ctx, captured, monkeypatch):
    """If wanted_search_order setting is not set, default to 'fair'.

    Since v0.88.0-beta wanted_search_order lives on ``Settings.ui``; mutate
    that sub-object directly so the runner's ``getattr(s, ...)`` fallback
    is exercised.
    """
    from config import get_settings

    s = get_settings()
    # Do NOT set wanted_search_order — rely on the runner's default
    monkeypatch.setattr(s.ui, "wanted_search_max_items_per_run", 50, raising=False)
    if hasattr(s.ui, "wanted_search_order"):
        monkeypatch.delattr(s.ui, "wanted_search_order", raising=False)

    with patch("db.wanted.get_items_for_scheduled_search", side_effect=_fake_selector(captured)):
        from services.wanted_search_runner import run_wanted_search

        run_wanted_search()

    assert captured.get("order") == "fair"
