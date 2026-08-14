"""The wanted-search tick must be bounded and must stop when asked.

Prod incident 2026-08-12: one ``wanted_search`` tick pulled 3124 items with a
local source sidecar out of the candidate pool and started translating them
one after another. Two defects made that a dead end rather than a long run:

1. ``local_translate_items`` was split off the raw fetch pool *before*
   ``eligible = eligible[:max_items]``, so it was never bounded by
   ``wanted_search_max_items_per_run`` — the cap that exists to keep one tick
   from swallowing the whole queue applied to the provider list only.
2. Neither the local-sidecar loop nor the embedded-extract loop looked at the
   cancellation signal. The provider loop does. So when the scheduler's
   1800s timeout fired and set the event, the tick kept translating.

Consequence: the tick never returned, ``search_all`` kept its ``_search_lock``,
and every scheduled ``wanted_search`` for the next 21 hours logged
"Wanted search already running, skipping". Provider downloads went from 88 a
day to zero while the machine-translation path kept running — the queue looked
busy and was in fact starved.

These tests pin both bounds: a tick takes at most ``max_items`` per phase, and
every phase stops at its next item when the run is cancelled.
"""

from __future__ import annotations

import threading
from unittest.mock import patch

import pytest


def _item(item_id: int, *, existing_sub: str = ""):
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


def _configure_settings(
    monkeypatch,
    *,
    max_items: int = 50,
    auto_translate: bool = True,
    auto_extract: bool = False,
):
    from config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "wanted_search_order", "fair", raising=False)
    monkeypatch.setattr(s, "wanted_search_max_items_per_run", max_items, raising=False)
    monkeypatch.setattr(s, "wanted_max_search_attempts", 3, raising=False)
    monkeypatch.setattr(s, "wanted_adaptive_backoff_enabled", True, raising=False)
    monkeypatch.setattr(s, "wanted_auto_translate", auto_translate, raising=False)
    monkeypatch.setattr(s, "subtitle_automation_enabled", False, raising=False)
    monkeypatch.setattr(s, "wanted_auto_extract", auto_extract, raising=False)
    return s


def _run_with_sidecars(app_ctx, items, fallback, *, cancel_event=None):
    """Run a tick where every item has a local sidecar (no provider calls)."""
    provider_calls: list[int] = []

    def _fake_process(item_id: int) -> dict:
        provider_calls.append(item_id)
        return {"status": "not_found", "wanted_id": item_id}

    with (
        patch("db.wanted.get_items_for_scheduled_search", return_value=items),
        patch(
            "translator._helpers.find_any_source_sub",
            return_value=("/media/source.eng.ass", "en"),
        ),
        patch("wanted_search.process._fallback_translate_file", side_effect=fallback),
        patch("wanted_search.process_wanted_item", side_effect=_fake_process),
    ):
        from services.wanted_search_runner import run_wanted_search

        summary = run_wanted_search(app=app_ctx, include_upgrades=True, cancel_event=cancel_event)
    return summary, provider_calls


class TestLocalSidecarPhaseIsBounded:
    def test_local_sidecar_items_respect_max_items_per_run(self, app_ctx, monkeypatch):
        """The per-run cap must bound the sidecar phase, not just the provider
        phase. Without this the tick's workload is the whole fetch pool."""
        _configure_settings(monkeypatch, max_items=3)
        calls: list[int] = []

        def _fallback(ctx):
            calls.append(ctx["item_id"])
            return {"wanted_id": ctx["item_id"], "status": "found"}

        summary, _ = _run_with_sidecars(app_ctx, [_item(i) for i in range(1, 11)], _fallback)

        assert len(calls) == 3, f"tick must translate at most max_items, got {len(calls)}"
        assert summary["total"] == 3, "total must report the bounded workload"

    def test_prod_sized_max_items_does_not_bound_the_sidecar_phase(self, app_ctx, monkeypatch):
        """``max_items`` is tuned for the parallel provider phase — prod runs it
        at 2000. For a serial phase with a multi-minute LLM translation per item
        that is not a bound at all, so the sidecar phase carries its own, much
        smaller ceiling. Without this the 2026-08-12 runaway would have been
        capped at 2000 items, which is the same failure with a longer fuse."""
        from services.wanted_search_runner import _MAX_LOCAL_TRANSLATES_PER_TICK

        _configure_settings(monkeypatch, max_items=2000)
        calls: list[int] = []

        def _fallback(ctx):
            calls.append(ctx["item_id"])
            return {"wanted_id": ctx["item_id"], "status": "found"}

        items = [_item(i) for i in range(1, _MAX_LOCAL_TRANSLATES_PER_TICK + 50)]
        _run_with_sidecars(app_ctx, items, _fallback)

        assert len(calls) == _MAX_LOCAL_TRANSLATES_PER_TICK

    def test_lower_max_items_still_wins(self, app_ctx, monkeypatch):
        """A user who deliberately set a small per-run cap must keep it — the
        ceiling is an upper bound, not a floor."""
        _configure_settings(monkeypatch, max_items=2)
        calls: list[int] = []

        def _fallback(ctx):
            calls.append(ctx["item_id"])
            return {"wanted_id": ctx["item_id"], "status": "found"}

        _run_with_sidecars(app_ctx, [_item(i) for i in range(1, 21)], _fallback)

        assert len(calls) == 2

    def test_cap_leaves_provider_search_reachable(self, app_ctx, monkeypatch):
        """A backlog of sidecar items must not starve the provider phase: the
        two phases consume different resources and each gets the per-run cap.
        This is the shape of the prod starvation — 3124 sidecar items ahead of
        every provider search in the queue."""
        _configure_settings(monkeypatch, max_items=2)
        calls: list[int] = []

        def _fallback(ctx):
            calls.append(ctx["item_id"])
            return {"wanted_id": ctx["item_id"], "status": "found"}

        sidecar_items = [_item(i) for i in range(1, 6)]
        provider_item = _item(99)

        def _selective_find(file_path, target_language=None):
            if "item-99" in file_path:
                return None, None
            return "/media/source.eng.ass", "en"

        provider_calls: list[int] = []

        def _fake_process(item_id: int) -> dict:
            provider_calls.append(item_id)
            return {"status": "not_found", "wanted_id": item_id}

        with (
            patch(
                "db.wanted.get_items_for_scheduled_search",
                return_value=[*sidecar_items, provider_item],
            ),
            patch("translator._helpers.find_any_source_sub", side_effect=_selective_find),
            patch("wanted_search.process._fallback_translate_file", side_effect=_fallback),
            patch("wanted_search.process_wanted_item", side_effect=_fake_process),
        ):
            from services.wanted_search_runner import run_wanted_search

            run_wanted_search(app=app_ctx, include_upgrades=True)

        assert len(calls) == 2, "sidecar phase stays capped"
        assert provider_calls == [99], "provider search must still run in the same tick"


class TestLocalSidecarPhaseStopsWhenAsked:
    def test_cancel_event_stops_the_sidecar_loop(self, app_ctx, monkeypatch):
        """The user's Cancel button sets this event. The loop must notice."""
        _configure_settings(monkeypatch, max_items=50)
        cancel_event = threading.Event()
        calls: list[int] = []

        def _fallback(ctx):
            calls.append(ctx["item_id"])
            cancel_event.set()
            return {"wanted_id": ctx["item_id"], "status": "found"}

        _run_with_sidecars(
            app_ctx, [_item(i) for i in range(1, 6)], _fallback, cancel_event=cancel_event
        )

        assert len(calls) == 1, f"must stop at the next item after cancel, ran {len(calls)}"

    def test_scheduler_abort_stops_the_sidecar_loop(self, app_ctx, monkeypatch):
        """The scheduler signals a timeout through the cancellation contextvar,
        not through the caller's argument — ``abort_requested()`` is the only
        way a scheduled tick learns it overran. This is the exact path that
        failed on prod."""
        from services.scheduler import cancellation

        _configure_settings(monkeypatch, max_items=50)
        calls: list[int] = []

        def _fallback(ctx):
            calls.append(ctx["item_id"])
            return {"wanted_id": ctx["item_id"], "status": "found"}

        event = threading.Event()
        event.set()
        token = cancellation.activate(event)
        try:
            _run_with_sidecars(app_ctx, [_item(i) for i in range(1, 6)], _fallback)
        finally:
            cancellation.deactivate(token)

        assert calls == [], "an already-aborted tick must not translate anything"


class TestEmbeddedExtractPhaseStopsWhenAsked:
    def test_cancel_event_stops_the_extract_loop(self, app_ctx, monkeypatch):
        """Same defect, same file: the inline extract loop ignored the signal."""
        _configure_settings(monkeypatch, max_items=50, auto_translate=False, auto_extract=True)
        cancel_event = threading.Event()
        extracted: list[int] = []

        def _fake_extract(item_id, file_path, auto_translate=False):
            extracted.append(item_id)
            cancel_event.set()

        items = [_item(i, existing_sub="embedded_ass") for i in range(1, 6)]

        with (
            patch("db.wanted.get_items_for_scheduled_search", return_value=items),
            patch("services.wanted_search_filters.extract_embedded_sub", side_effect=_fake_extract),
            patch("wanted_search.process_wanted_item", return_value={"status": "not_found"}),
        ):
            from services.wanted_search_runner import run_wanted_search

            run_wanted_search(app=app_ctx, include_upgrades=True, cancel_event=cancel_event)

        assert len(extracted) == 1, f"must stop at the next item after cancel, ran {len(extracted)}"


class TestSidecarPhaseHasATimeBudget:
    """A count cannot bound this phase.

    ``_MAX_LOCAL_TRANSLATES_PER_TICK`` was justified as "small enough that a
    tick finishes inside its budget". One item measured ~14.5 minutes on
    production 2026-08-13, and the cost scales with subtitle length, so 100
    items is roughly a day. The bound that matches the resource being spent
    is wall clock.
    """

    def test_phase_stops_at_its_deadline(self, app_ctx, monkeypatch):
        import time as _time

        from services.wanted_search_filters import _translate_local_sidecar_items

        s = _configure_settings(monkeypatch, max_items=50)
        calls: list[int] = []

        def _fallback(ctx):
            calls.append(ctx["item_id"])
            return {"wanted_id": ctx["item_id"], "status": "found"}

        # Deadline already in the past: not one item may start.
        with patch("wanted_search.process._fallback_translate_file", side_effect=_fallback):
            _translate_local_sidecar_items(
                [_item(i) for i in range(1, 6)],
                0,
                0,
                0,
                5,
                None,
                s,
                deadline=_time.monotonic() - 1,
            )

        assert calls == []

    def test_deadline_is_checked_between_items_not_only_before(self, app_ctx, monkeypatch):
        import time as _time

        from services.wanted_search_filters import _translate_local_sidecar_items

        s = _configure_settings(monkeypatch, max_items=50)
        calls: list[int] = []
        deadline = _time.monotonic() + 3600

        def _fallback(ctx):
            nonlocal deadline
            calls.append(ctx["item_id"])
            deadline = _time.monotonic() - 1  # budget spent during this item
            return {"wanted_id": ctx["item_id"], "status": "found"}

        with patch("wanted_search.process._fallback_translate_file", side_effect=_fallback):
            _translate_local_sidecar_items(
                [_item(i) for i in range(1, 6)],
                0,
                0,
                0,
                5,
                None,
                s,
                deadline=lambda: deadline,
            )

        assert len(calls) == 1

    def test_no_deadline_means_no_budget(self, app_ctx, monkeypatch):
        """``deadline=None`` must keep the phase's old behaviour intact —
        the count cap stays the only bound for callers that pass nothing."""
        from services.wanted_search_filters import _translate_local_sidecar_items

        s = _configure_settings(monkeypatch, max_items=50)
        calls: list[int] = []

        def _fallback(ctx):
            calls.append(ctx["item_id"])
            return {"wanted_id": ctx["item_id"], "status": "found"}

        with patch("wanted_search.process._fallback_translate_file", side_effect=_fallback):
            _translate_local_sidecar_items(
                [_item(i) for i in range(1, 6)], 0, 0, 0, 5, None, s, deadline=None
            )

        assert len(calls) == 5

    def test_zero_budget_disables_the_phase_in_a_real_tick(self, app_ctx, monkeypatch):
        """The setting is also the off switch: 0 means "never translate inline"."""
        s = _configure_settings(monkeypatch, max_items=50)
        monkeypatch.setattr(s, "wanted_search_sidecar_budget_s", 0, raising=False)
        calls: list[int] = []

        def _fallback(ctx):
            calls.append(ctx["item_id"])
            return {"wanted_id": ctx["item_id"], "status": "found"}

        _run_with_sidecars(app_ctx, [_item(i) for i in range(1, 6)], _fallback)

        assert calls == []
