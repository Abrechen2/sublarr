"""Sidecar translation belongs to the drain worker, not to the search job.

Translating inline meant `wanted_search` held the global search lock for as
long as the translations took — 21 hours in the unbounded case, 24 hours with
the count cap. The queue already owns extraction, has backoff, retry, its own
timeout and its own cancellation. Search should classify and enqueue.

The inline phase is not dead after this: it is the fallback for installs that
have subtitle automation switched off, where nothing would ever drain the
queue. There it stays bounded by the wall-clock deadline from
`wanted_search_sidecar_budget_s` (see test_wanted_search_tick_bounds.py).
"""

from __future__ import annotations

from unittest.mock import patch

SOURCE_SIDECAR = "/media/item-1.eng.ass"


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


def _configure_settings(monkeypatch, *, automation: bool = True, max_items: int = 50):
    from config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "wanted_search_order", "fair", raising=False)
    monkeypatch.setattr(s, "wanted_search_max_items_per_run", max_items, raising=False)
    monkeypatch.setattr(s, "wanted_max_search_attempts", 3, raising=False)
    monkeypatch.setattr(s, "wanted_adaptive_backoff_enabled", True, raising=False)
    monkeypatch.setattr(s, "wanted_auto_translate", True, raising=False)
    monkeypatch.setattr(s, "subtitle_automation_enabled", automation, raising=False)
    monkeypatch.setattr(s, "wanted_auto_extract", False, raising=False)
    return s


class TestSidecarEnqueue:
    def test_scheduled_run_enqueues_instead_of_translating(self, app_ctx, monkeypatch):
        from services.wanted_search_runner import run_wanted_search

        _configure_settings(monkeypatch, automation=True)
        translated: list[int] = []
        enqueued: list[dict] = []

        def _never(ctx):
            translated.append(ctx["item_id"])
            return {"status": "found", "wanted_id": ctx["item_id"]}

        def _fake_enqueue(self, **kwargs):
            enqueued.append(kwargs)
            return len(enqueued)

        with (
            patch("db.wanted.get_items_for_scheduled_search", return_value=[_item(1)]),
            patch(
                "translator._helpers.find_any_source_sub",
                return_value=(SOURCE_SIDECAR, "en"),
            ),
            patch("wanted_search.process._fallback_translate_file", side_effect=_never),
            patch(
                "db.repositories.subtitle_automation_queue."
                "SubtitleAutomationQueueRepository.enqueue",
                _fake_enqueue,
            ),
        ):
            summary = run_wanted_search(app=app_ctx, include_upgrades=True)

        assert translated == [], "the search job must not translate"
        assert len(enqueued) == 1
        assert enqueued[0]["task_type"] == "sidecar_translate"
        assert enqueued[0]["wanted_item_id"] == 1
        assert enqueued[0]["source_language"] == "en"
        assert summary["processed"] >= 1

    def test_the_queued_path_is_the_media_file_not_the_sidecar(self, app_ctx, monkeypatch):
        """`translate_file` takes the media file and finds the sidecar itself
        (Case C2b) — that is the whole reason these items need no provider.
        Queueing the .ass path would hand the drain worker something the
        translate path does not accept, and it would also disagree with the
        embedded_extract rows, where file_path is always the media file."""
        from services.wanted_search_filters import _enqueue_sidecar_items

        s = _configure_settings(monkeypatch, automation=True)
        enqueued: list[dict] = []

        def _fake_enqueue(self, **kwargs):
            enqueued.append(kwargs)
            return len(enqueued)

        with patch(
            "db.repositories.subtitle_automation_queue.SubtitleAutomationQueueRepository.enqueue",
            _fake_enqueue,
        ):
            leftover, count = _enqueue_sidecar_items(
                [{**_item(1), "_local_source_language": "en"}], s
            )

        assert count == 1
        assert leftover == []
        assert enqueued[0]["file_path"] == "/media/item-1.mkv"

    def test_a_failing_enqueue_does_not_lose_the_item(self, app_ctx, monkeypatch):
        """A queue insert that raises must leave the item for the caller, not
        drop it and not crash the tick."""
        from services.wanted_search_filters import _enqueue_sidecar_items

        s = _configure_settings(monkeypatch, automation=True)

        def _boom(self, **kwargs):
            raise RuntimeError("queue unavailable")

        with patch(
            "db.repositories.subtitle_automation_queue.SubtitleAutomationQueueRepository.enqueue",
            _boom,
        ):
            leftover, count = _enqueue_sidecar_items([_item(1)], s)

        assert count == 0
        assert [i["id"] for i in leftover] == [1]

    def test_an_item_without_a_target_language_is_left_alone(self, app_ctx, monkeypatch):
        from services.wanted_search_filters import _enqueue_sidecar_items

        s = _configure_settings(monkeypatch, automation=True)
        monkeypatch.setattr(s, "target_language", "", raising=False)
        item = {**_item(1), "target_language": ""}

        leftover, count = _enqueue_sidecar_items([item], s)

        assert count == 0
        assert [i["id"] for i in leftover] == [1]


class TestAutomationOffKeepsTheInlineFallback:
    def test_automation_off_still_translates_inline(self, app_ctx, monkeypatch):
        """With the drain worker disabled nothing would ever pick a queued row
        up, so the search job must keep doing this work itself — bounded by
        the sidecar wall-clock budget rather than handed off."""
        from services.wanted_search_runner import run_wanted_search

        _configure_settings(monkeypatch, automation=False)
        translated: list[int] = []
        enqueued: list[dict] = []

        def _translate(ctx):
            translated.append(ctx["item_id"])
            return {"status": "found", "wanted_id": ctx["item_id"]}

        def _fake_enqueue(self, **kwargs):
            enqueued.append(kwargs)
            return len(enqueued)

        with (
            patch("db.wanted.get_items_for_scheduled_search", return_value=[_item(1)]),
            patch(
                "translator._helpers.find_any_source_sub",
                return_value=(SOURCE_SIDECAR, "en"),
            ),
            patch("wanted_search.process._fallback_translate_file", side_effect=_translate),
            patch(
                "db.repositories.subtitle_automation_queue."
                "SubtitleAutomationQueueRepository.enqueue",
                _fake_enqueue,
            ),
        ):
            run_wanted_search(app=app_ctx, include_upgrades=True)

        assert enqueued == [], "nothing drains the queue when automation is off"
        assert translated == [1]


class TestDrainWorkerRunsTheTranslation:
    def _queue_row(self, **over):
        row = {
            "id": 7,
            "wanted_item_id": 1,
            "task_type": "sidecar_translate",
            "file_path": "/media/item-1.mkv",
            "target_language": "de",
            "source_language": "en",
            "attempt_count": 0,
        }
        row.update(over)
        return row

    def test_sidecar_row_goes_to_the_translate_path(self, app_ctx, monkeypatch):
        from services.subtitle_automation_runner import SubtitleAutomationRunner

        contexts: list[dict] = []

        class _Repo:
            def claim_next(self, *, now=None):
                return TestDrainWorkerRunsTheTranslation()._queue_row()

            def mark_done(self, entry_id):
                self.done = entry_id

            def mark_failed(self, entry_id, *, error, next_retry_at):
                raise AssertionError(f"unexpected failure: {error}")

        repo = _Repo()
        runner = SubtitleAutomationRunner(repo=repo)

        def _translate(ctx):
            contexts.append(ctx)
            return {"status": "found", "wanted_id": ctx["item_id"]}

        with (
            patch("wanted_search.process._fallback_translate_file", side_effect=_translate),
            patch("db.wanted.get_wanted_item", return_value=_item(1)),
            patch(
                "services.subtitle_automation_runner._extract_embedded_sub",
                side_effect=AssertionError("must not extract a translate row"),
            ),
        ):
            assert runner.process_one() is True

        assert len(contexts) == 1
        ctx = contexts[0]
        assert ctx["item"] is not None, "the translate path dereferences ctx['item']"
        assert ctx["item_id"] == 1
        assert ctx["file_path"] == "/media/item-1.mkv"
        assert repo.done == 7

    def test_extraction_rows_are_untouched(self, app_ctx, monkeypatch):
        from services.subtitle_automation_runner import SubtitleAutomationRunner

        extracted: list[int] = []

        class _Repo:
            def claim_next(self, *, now=None):
                return TestDrainWorkerRunsTheTranslation()._queue_row(
                    task_type="embedded_extract", source_language=None
                )

            def mark_done(self, entry_id):
                self.done = entry_id

            def mark_failed(self, entry_id, *, error, next_retry_at):
                raise AssertionError(f"unexpected failure: {error}")

        repo = _Repo()
        runner = SubtitleAutomationRunner(repo=repo)

        with (
            patch(
                "services.subtitle_automation_runner._extract_embedded_sub",
                side_effect=lambda wid, fp, auto_translate=False: extracted.append(wid),
            ),
            patch(
                "wanted_search.process._fallback_translate_file",
                side_effect=AssertionError("must not translate an extract row"),
            ),
        ):
            assert runner.process_one() is True

        assert extracted == [1]
        assert repo.done == 7

    def test_a_vanished_wanted_item_is_a_terminal_failure(self, app_ctx, monkeypatch):
        """The item can be deleted between enqueue and drain. Retrying that
        forever would keep a dead row cycling through the backoff ladder."""
        from services.subtitle_automation_runner import SubtitleAutomationRunner

        failures: list[tuple[str, object]] = []

        class _Repo:
            def claim_next(self, *, now=None):
                return TestDrainWorkerRunsTheTranslation()._queue_row()

            def mark_done(self, entry_id):
                raise AssertionError("must not report success")

            def mark_failed(self, entry_id, *, error, next_retry_at):
                failures.append((error, next_retry_at))

        runner = SubtitleAutomationRunner(repo=_Repo())

        with patch("db.wanted.get_wanted_item", return_value=None):
            assert runner.process_one() is True

        assert len(failures) == 1
        assert failures[0][1] is None, "a gone item must not be retried on a timer"
