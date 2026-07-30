"""Gating tests for the wanted-search embedded-extraction path (issue #159).

Regression coverage: the scheduled wanted search used to route every item
with ``existing_sub in ("embedded_ass", "embedded_srt")`` into
``_extract_embedded_items`` unconditionally — extraction (and the container
remux that followed) ran even with ``subtitle_automation_enabled`` and
``wanted_auto_extract`` both off. 21 user files were remuxed on a default
install before the report.

The fix mirrors the scan-time routing (``_maybe_auto_extract``):
  automation on   → enqueue to subtitle_automation_queue (drain worker owns it)
  legacy toggle   → inline extract (previous behaviour, now opt-in)
  both off        → the item stays in the normal provider search; no file I/O
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _item(item_id: int, *, existing_sub: str = "embedded_ass"):
    return {
        "id": item_id,
        "title": f"item-{item_id}",
        "file_path": f"/media/item-{item_id}.mkv",
        "target_language": "de",
        "existing_sub": existing_sub,
        "priority": "standard",
        "upgrade_candidate": False,
        "last_search_at": None,
        "retry_after": None,
        "search_count": 0,
    }


def _configure_settings(monkeypatch, *, automation: bool, auto_extract: bool):
    from config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "wanted_search_order", "fair", raising=False)
    monkeypatch.setattr(s, "wanted_search_max_items_per_run", 50, raising=False)
    monkeypatch.setattr(s, "wanted_max_search_attempts", 3, raising=False)
    monkeypatch.setattr(s, "wanted_adaptive_backoff_enabled", True, raising=False)
    monkeypatch.setattr(s, "wanted_auto_translate", False, raising=False)
    monkeypatch.setattr(s, "subtitle_automation_enabled", automation, raising=False)
    monkeypatch.setattr(s, "wanted_auto_extract", auto_extract, raising=False)
    return s


def _run(app_ctx, embedded_item, provider_calls):
    def _fake_process(item_id: int) -> dict:
        provider_calls.append(item_id)
        return {"status": "not_found", "wanted_id": item_id}

    with (
        patch("db.wanted.get_items_for_scheduled_search", return_value=[embedded_item]),
        patch("wanted_search.process_wanted_item", side_effect=_fake_process),
    ):
        from services.wanted_search_runner import run_wanted_search

        return run_wanted_search(app=app_ctx, include_upgrades=True)


class TestWantedSearchEmbeddedGating:
    def test_both_toggles_off_embedded_items_are_searched_not_extracted(
        self, app_ctx, monkeypatch
    ):
        """THE #159 regression test: with automation and the legacy toggle
        both off, an embedded-sub item must go through the normal provider
        search — extract_embedded_sub must never run."""
        _configure_settings(monkeypatch, automation=False, auto_extract=False)
        provider_calls: list[int] = []

        with patch(
            "services.wanted_search_filters.extract_embedded_sub"
        ) as mock_extract:
            summary = _run(app_ctx, _item(1), provider_calls)

        mock_extract.assert_not_called()
        assert provider_calls == [1], "embedded item must reach the provider search"
        assert summary["total"] == 1
        assert summary["processed"] == 1

    def test_automation_on_embedded_items_enqueued_not_extracted_not_searched(
        self, app_ctx, monkeypatch
    ):
        _configure_settings(monkeypatch, automation=True, auto_extract=False)
        provider_calls: list[int] = []

        enqueue_calls: list[dict] = []

        class _FakeRepo:
            def enqueue(self, **kwargs):
                enqueue_calls.append(kwargs)

        with (
            patch("services.wanted_search_filters.extract_embedded_sub") as mock_extract,
            patch(
                "db.repositories.subtitle_automation_queue.SubtitleAutomationQueueRepository",
                return_value=_FakeRepo(),
            ),
        ):
            summary = _run(app_ctx, _item(1), provider_calls)

        mock_extract.assert_not_called()
        assert provider_calls == [], "enqueued item must not be provider-searched this tick"
        assert len(enqueue_calls) == 1
        assert enqueue_calls[0]["wanted_item_id"] == 1
        assert enqueue_calls[0]["target_language"] == "de"
        assert summary["processed"] == 1
        assert summary["skipped"] == 1

    def test_legacy_auto_extract_on_extracts_inline(self, app_ctx, monkeypatch):
        _configure_settings(monkeypatch, automation=False, auto_extract=True)
        provider_calls: list[int] = []

        with patch(
            "services.wanted_search_filters.extract_embedded_sub",
            return_value={"status": "extracted"},
        ) as mock_extract:
            summary = _run(app_ctx, _item(1), provider_calls)

        mock_extract.assert_called_once()
        assert mock_extract.call_args.args[0] == 1
        assert provider_calls == []
        assert summary["found"] == 1

    def test_enqueue_failure_falls_back_to_search_when_legacy_off(
        self, app_ctx, monkeypatch
    ):
        """Automation on but the queue insert raises: the item must not be
        dropped silently — with the legacy toggle off it falls back to the
        provider search (and is still never extracted inline)."""
        _configure_settings(monkeypatch, automation=True, auto_extract=False)
        provider_calls: list[int] = []

        class _BrokenRepo:
            def enqueue(self, **kwargs):
                raise RuntimeError("db locked")

        with (
            patch("services.wanted_search_filters.extract_embedded_sub") as mock_extract,
            patch(
                "db.repositories.subtitle_automation_queue.SubtitleAutomationQueueRepository",
                return_value=_BrokenRepo(),
            ),
        ):
            summary = _run(app_ctx, _item(1), provider_calls)

        mock_extract.assert_not_called()
        assert provider_calls == [1]
        assert summary["processed"] == 1

    def test_non_embedded_items_unaffected_by_toggles(self, app_ctx, monkeypatch):
        _configure_settings(monkeypatch, automation=False, auto_extract=False)
        provider_calls: list[int] = []

        summary = _run(app_ctx, _item(1, existing_sub=""), provider_calls)

        assert provider_calls == [1]
        assert summary["processed"] == 1


class TestEnqueueEmbeddedItems:
    def test_enqueues_with_item_target_language(self):
        from services.wanted_search_filters import _enqueue_embedded_items

        calls: list[dict] = []

        class _FakeRepo:
            def enqueue(self, **kwargs):
                calls.append(kwargs)

        settings = MagicMock()
        settings.target_language = "en"

        with patch(
            "db.repositories.subtitle_automation_queue.SubtitleAutomationQueueRepository",
            return_value=_FakeRepo(),
        ):
            leftover, enqueued = _enqueue_embedded_items([_item(1)], settings)

        assert leftover == []
        assert enqueued == 1
        assert calls[0]["target_language"] == "de"

    def test_falls_back_to_settings_target_language(self):
        from services.wanted_search_filters import _enqueue_embedded_items

        calls: list[dict] = []

        class _FakeRepo:
            def enqueue(self, **kwargs):
                calls.append(kwargs)

        item = _item(1)
        item["target_language"] = None
        settings = MagicMock()
        settings.target_language = "en"

        with patch(
            "db.repositories.subtitle_automation_queue.SubtitleAutomationQueueRepository",
            return_value=_FakeRepo(),
        ):
            leftover, enqueued = _enqueue_embedded_items([item], settings)

        assert enqueued == 1
        assert calls[0]["target_language"] == "en"

    def test_no_language_and_errors_become_leftover(self):
        from services.wanted_search_filters import _enqueue_embedded_items

        class _BrokenRepo:
            def enqueue(self, **kwargs):
                raise RuntimeError("boom")

        no_lang = _item(1)
        no_lang["target_language"] = None
        erroring = _item(2)

        settings = MagicMock()
        settings.target_language = ""

        with patch(
            "db.repositories.subtitle_automation_queue.SubtitleAutomationQueueRepository",
            return_value=_BrokenRepo(),
        ):
            leftover, enqueued = _enqueue_embedded_items([no_lang, erroring], settings)

        assert enqueued == 0
        assert [i["id"] for i in leftover] == [1, 2]
