"""Tests for the local-sidecar fast path in run_wanted_search.

Regression coverage for a prod finding: items with a source-language
sidecar already on disk (e.g. ``.eng.ass`` sitting next to the video) waited
behind the exact same provider-rate-limit ``retry_after`` backoff as items
with no local material at all, because ``_filter_eligible`` only inspects DB
fields and has no idea the filesystem already has what's needed. Confirmed
on prod: 1012 of 2133 wanted items had a ready sidecar; 0 were ever picked
up while wanted_auto_translate was enabled.

The fix (``_split_local_translate_items`` / ``_translate_local_sidecar_items``
in services/wanted_search_filters.py) pulls these items out BEFORE the
eligibility gate and translates them directly via the same Step-5 fallback
the normal per-item pipeline would eventually reach — no provider call, no
retry_after check.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _item(
    item_id: int, *, existing_sub: str = "", retry_after: str | None = None, search_count: int = 0
):
    return {
        "id": item_id,
        "title": f"item-{item_id}",
        "file_path": f"/media/item-{item_id}.mkv",
        "target_language": "de",
        "existing_sub": existing_sub,
        "priority": "standard",
        "upgrade_candidate": False,
        "last_search_at": None,
        "retry_after": retry_after,
        "search_count": search_count,
    }


def _configure_settings(monkeypatch, *, auto_translate: bool, max_items: int = 50):
    from config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "wanted_search_order", "fair", raising=False)
    monkeypatch.setattr(s, "wanted_search_max_items_per_run", max_items, raising=False)
    monkeypatch.setattr(s, "wanted_max_search_attempts", 3, raising=False)
    monkeypatch.setattr(s, "wanted_adaptive_backoff_enabled", True, raising=False)
    monkeypatch.setattr(s, "wanted_auto_translate", auto_translate, raising=False)
    return s


class TestSplitLocalTranslateItems:
    def test_disabled_auto_translate_returns_everything_unsplit(self, monkeypatch):
        from services.wanted_search_filters import _split_local_translate_items

        s = _configure_settings(monkeypatch, auto_translate=False)
        items = [_item(1), _item(2)]

        local_items, remaining = _split_local_translate_items(items, s)

        assert local_items == []
        assert remaining == items

    def test_items_with_local_sidecar_are_split_out(self, monkeypatch):
        from services.wanted_search_filters import _split_local_translate_items

        s = _configure_settings(monkeypatch, auto_translate=True)
        has_sidecar = _item(1)
        no_sidecar = _item(2)

        def _fake_find(file_path, target_language=None):
            if "item-1" in file_path:
                return "/media/item-1.eng.ass", "en"
            return None, None

        with patch("translator._helpers.find_any_source_sub", side_effect=_fake_find):
            local_items, remaining = _split_local_translate_items([has_sidecar, no_sidecar], s)

        assert [i["id"] for i in local_items] == [1]
        assert [i["id"] for i in remaining] == [2]

    def test_embedded_items_are_never_split_into_local_translate(self, monkeypatch):
        """Embedded-track items already have their own zero-provider path
        (_extract_embedded_items) — the sidecar split must leave them alone
        even if find_any_source_sub would also match."""
        from services.wanted_search_filters import _split_local_translate_items

        s = _configure_settings(monkeypatch, auto_translate=True)
        embedded_item = _item(1, existing_sub="embedded_ass")

        with patch(
            "translator._helpers.find_any_source_sub", return_value=("/media/item-1.eng.ass", "en")
        ) as mock_find:
            local_items, remaining = _split_local_translate_items([embedded_item], s)

        assert local_items == []
        assert [i["id"] for i in remaining] == [1]
        mock_find.assert_not_called()


class TestRunWantedSearchLocalSidecarBypass:
    def test_local_sidecar_item_bypasses_retry_after_cooldown(self, app_ctx, monkeypatch):
        """The whole point: an item deep in retry_after cooldown must still
        get translated when a local sidecar exists, and process_wanted_item
        (the provider-hitting path) must never be called for it."""
        _configure_settings(monkeypatch, auto_translate=True)
        now = datetime.now(UTC)

        cooling_down_with_sidecar = _item(
            1, retry_after=_iso(now + timedelta(days=30)), search_count=6
        )

        provider_calls: list[int] = []

        def _fake_process(item_id: int) -> dict:
            provider_calls.append(item_id)
            return {"status": "found", "wanted_id": item_id}

        fallback_calls: list[int] = []

        def _fake_fallback(ctx):
            fallback_calls.append(ctx["item_id"])
            return {"wanted_id": ctx["item_id"], "status": "found"}

        with (
            patch(
                "db.wanted.get_items_for_scheduled_search",
                return_value=[cooling_down_with_sidecar],
            ),
            patch(
                "translator._helpers.find_any_source_sub",
                return_value=("/media/item-1.eng.ass", "en"),
            ),
            patch("wanted_search.process._fallback_translate_file", side_effect=_fake_fallback),
            patch("wanted_search.process_wanted_item", side_effect=_fake_process),
        ):
            from services.wanted_search_runner import run_wanted_search

            summary = run_wanted_search(app=app_ctx, include_upgrades=True)

        assert fallback_calls == [1], "local-sidecar item must be translated directly"
        assert provider_calls == [], "must never hit the provider-search path"
        assert summary["found"] == 1
        assert summary["total"] == 1

    def test_auto_translate_off_keeps_normal_provider_flow(self, app_ctx, monkeypatch):
        """Without auto-translate there is nothing to bypass to — items with
        a local sidecar must go through the ordinary eligibility+provider
        path exactly as before (Steps 1/3 still get a shot at a real match)."""
        _configure_settings(monkeypatch, auto_translate=False)

        due_item = _item(1, retry_after=None, search_count=0)

        provider_calls: list[int] = []

        def _fake_process(item_id: int) -> dict:
            provider_calls.append(item_id)
            return {"status": "found", "wanted_id": item_id}

        with (
            patch("db.wanted.get_items_for_scheduled_search", return_value=[due_item]),
            patch(
                "translator._helpers.find_any_source_sub",
                return_value=("/media/item-1.eng.ass", "en"),
            ) as mock_find,
            patch("wanted_search.process_wanted_item", side_effect=_fake_process),
        ):
            from services.wanted_search_runner import run_wanted_search

            summary = run_wanted_search(app=app_ctx, include_upgrades=True)

        mock_find.assert_not_called()
        assert provider_calls == [1]
        assert summary["processed"] == 1
