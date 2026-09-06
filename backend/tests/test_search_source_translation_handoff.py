"""Steps 2 and 4 must hand their translation to the drain, not run it inline.

`allow_translate_fallback` already keeps the scheduled search out of Step 5.
It gates exactly one call site (`process.py`, the guard before
`_fallback_translate_file`) - Steps 2 and 4 were never covered by it, and both
push a full LLM translation through the search thread once a source-language
subtitle is downloaded.

Measured on prod 2026-09-06, tick 30ef4d64: 03:13:51 to 04:04:03 against a
1800s timeout. The provider work was done after ~90s; the remaining 49 minutes
were `translator.quality`, `translator.ass_flow` and `translation.llm_base`.
An LLM translation cannot be interrupted, so the tick could not honour its
stop request either - "exceeded 1800s and did NOT stop when asked", then
`timeout_abandoned`.

The handoff mirrors the sidecar phase: the search still does the cheap half it
exists for (download the source subtitle to disk) and queues the expensive
half. The item keeps its route to a subtitle, it just travels by the job that
owns translation.

Two invariants are load-bearing:
  * an enqueue that fails must fall through to the inline translation - the
    search must never drop an item on the floor;
  * the row must not be left in `searching`. That exit stranded 7,878 rows on
    prod 2026-08-19 when Step 5's gate first skipped its bookkeeping.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

_ENQUEUE = "db.repositories.subtitle_automation_queue.SubtitleAutomationQueueRepository.enqueue"


def _settings():
    s = MagicMock()
    s.source_language = "en"
    s.target_language_name = "German"
    return s


def _ctx(tmp_path, *, defer: bool, item_id: int = 1):
    (tmp_path / "ep.mkv").write_bytes(b"fake")
    return {
        "item": {"id": item_id, "title": "Ep", "sonarr_series_id": None},
        "item_id": item_id,
        "item_lang": "de",
        "settings": _settings(),
        "manager": MagicMock(),
        "_pf": {"must_contain": "", "must_not_contain": ""},
        "file_path": str(tmp_path / "ep.mkv"),
        "source_query": MagicMock(),
        "defer_translation": defer,
        "ass_had_results": False,
    }


def _downloadable(manager, tmp_path, name):
    """Make the provider return one result that saves to `name`."""
    result = MagicMock()
    result.content = b"payload"
    result.provider_name = "fake"
    result.subtitle_id = "sid-1"
    result.score = 100
    result.score_breakdown = {}
    result.format.value = "ass"
    manager.search_and_download_best.return_value = result
    saved = tmp_path / name
    saved.write_text("source subtitle", encoding="utf-8")
    manager.save_subtitle.return_value = str(saved)
    return saved


class TestStep2Handoff:
    def test_deferred_step2_enqueues_and_skips_the_llm(self, app_ctx, tmp_path):
        from wanted_search.process import _try_source_ass_translation

        ctx = _ctx(tmp_path, defer=True)
        _downloadable(ctx["manager"], tmp_path, "ep.en.ass")

        translated = []
        enqueued = []

        with (
            patch("wanted_search.process.record_subtitle_download"),
            patch("wanted_search.process.update_wanted_status") as status,
            patch(
                "translator._translate_external_ass",
                side_effect=lambda *a, **k: translated.append(True),
            ),
            patch(_ENQUEUE, side_effect=lambda **kw: enqueued.append(kw) or 1),
        ):
            out = _try_source_ass_translation(ctx)

        assert translated == [], "the search thread must not run the LLM translation"
        assert len(enqueued) == 1, f"expected one queued row, got {enqueued}"
        assert enqueued[0]["task_type"] == "sidecar_translate"
        assert enqueued[0]["wanted_item_id"] == 1
        assert out is not None, "a handoff must end the pipeline, not fall through to Step 3"
        assert out["status"] not in (
            "found",
            "failed",
        ), f"a queued item is neither found nor failed, got {out['status']}"
        # The 7,878-stranded-rows invariant.
        assert status.called, "the row must not be left in 'searching'"
        assert status.call_args[0][1] == "wanted"

    def test_download_still_happens_so_the_drain_finds_a_sidecar(self, app_ctx, tmp_path):
        """The drain rediscovers the sidecar from the media file (Case C2b).

        If the search skipped the download too, the queued row would have
        nothing to translate.
        """
        from wanted_search.process import _try_source_ass_translation

        ctx = _ctx(tmp_path, defer=True)
        saved = _downloadable(ctx["manager"], tmp_path, "ep.en.ass")

        with (
            patch("wanted_search.process.record_subtitle_download"),
            patch("wanted_search.process.update_wanted_status"),
            patch(_ENQUEUE, return_value=1),
        ):
            _try_source_ass_translation(ctx)

        ctx["manager"].save_subtitle.assert_called_once()
        assert saved.exists(), "the source sidecar must stay on disk for the drain"

    def test_failed_enqueue_falls_back_to_inline_translation(self, app_ctx, tmp_path):
        """Never lose an item because a queue insert failed."""
        from wanted_search.process import _try_source_ass_translation

        ctx = _ctx(tmp_path, defer=True)
        _downloadable(ctx["manager"], tmp_path, "ep.en.ass")

        translated = []

        with (
            patch("wanted_search.process.record_subtitle_download"),
            patch("wanted_search.process.update_wanted_status"),
            patch("wanted_search.process.create_job", return_value={"id": 7}),
            patch("wanted_search.process.update_job"),
            patch("wanted_search.process.record_stat"),
            patch("wanted_search.process._build_arr_context", return_value={}),
            patch(_ENQUEUE, side_effect=RuntimeError("queue is down")),
            patch(
                "translator._translate_external_ass",
                side_effect=lambda *a, **k: (
                    translated.append(True) or {"success": False, "error": "stop here"}
                ),
            ),
        ):
            try:
                _try_source_ass_translation(ctx)
            except Exception:
                pass

        assert translated == [True], (
            "a failed enqueue must fall through to the inline translation, not drop the item"
        )

    def test_default_still_translates_inline(self, app_ctx, tmp_path):
        """Manual search and the API keep today's behaviour - opt-out, not opt-in."""
        from wanted_search.process import _try_source_ass_translation

        ctx = _ctx(tmp_path, defer=False)
        _downloadable(ctx["manager"], tmp_path, "ep.en.ass")

        translated = []
        enqueued = []

        with (
            patch("wanted_search.process.record_subtitle_download"),
            patch("wanted_search.process.update_wanted_status"),
            patch("wanted_search.process.create_job", return_value={"id": 7}),
            patch("wanted_search.process.update_job"),
            patch("wanted_search.process.record_stat"),
            patch("wanted_search.process._build_arr_context", return_value={}),
            patch(_ENQUEUE, side_effect=lambda **kw: enqueued.append(kw) or 1),
            patch(
                "translator._translate_external_ass",
                side_effect=lambda *a, **k: (
                    translated.append(True) or {"success": False, "error": "stop here"}
                ),
            ),
        ):
            try:
                _try_source_ass_translation(ctx)
            except Exception:
                pass

        assert translated == [True], "the default path must still translate inline"
        assert enqueued == [], "the default path must not queue anything"


class TestStep4Handoff:
    def test_deferred_step4_enqueues_and_skips_the_llm(self, app_ctx, tmp_path):
        from wanted_search.process import _try_source_srt_translation

        ctx = _ctx(tmp_path, defer=True, item_id=2)
        _downloadable(ctx["manager"], tmp_path, "ep.en.srt")

        translated = []
        enqueued = []

        with (
            patch("wanted_search.process.record_subtitle_download"),
            patch("wanted_search.process.update_wanted_status") as status,
            patch(
                "translator.translate_srt_from_file",
                side_effect=lambda *a, **k: translated.append(True),
            ),
            patch(_ENQUEUE, side_effect=lambda **kw: enqueued.append(kw) or 1),
        ):
            out = _try_source_srt_translation(ctx)

        assert translated == [], "the search thread must not run the LLM translation"
        assert len(enqueued) == 1
        assert enqueued[0]["task_type"] == "sidecar_translate"
        assert out is not None
        assert out["status"] not in ("found", "failed")
        assert status.called and status.call_args[0][1] == "wanted"


class TestScheduledSearchWiring:
    """The scheduled search must switch the handoff on exactly when a drain exists."""

    def _run(self, app_ctx, monkeypatch, *, automation: bool):
        from config import get_settings
        from services.wanted_search_runner import run_wanted_search

        s = get_settings()
        for k, v in {
            "wanted_search_order": "fair",
            "wanted_search_max_items_per_run": 10,
            "wanted_max_search_attempts": 3,
            "wanted_adaptive_backoff_enabled": True,
            "wanted_auto_translate": False,
            "subtitle_automation_enabled": automation,
            "wanted_auto_extract": False,
        }.items():
            monkeypatch.setattr(s, k, v, raising=False)

        item = {
            "id": 1,
            "title": "item-1",
            "file_path": "/media/item-1.mkv",
            "target_language": "de",
            "existing_sub": "",
            "priority": "standard",
            "upgrade_candidate": False,
            "last_search_at": None,
            "retry_after": None,
            "search_count": 0,
        }
        seen: list[dict] = []

        def _fake_process(item_id, *args, **kwargs):
            seen.append(kwargs)
            return {"status": "not_found", "wanted_id": item_id}

        with (
            patch("db.wanted.get_items_for_scheduled_search", return_value=[item]),
            patch("wanted_search.process_wanted_item", side_effect=_fake_process),
        ):
            run_wanted_search(app=app_ctx, include_upgrades=True)
        return seen

    def test_automation_on_defers_steps_2_and_4(self, app_ctx, monkeypatch):
        seen = self._run(app_ctx, monkeypatch, automation=True)
        assert seen, "the provider phase must have run an item"
        assert seen[0].get("defer_translation") is True

    def test_automation_off_keeps_them_inline(self, app_ctx, monkeypatch):
        """Nothing would drain a queued row on these installs."""
        seen = self._run(app_ctx, monkeypatch, automation=False)
        assert seen, "the provider phase must have run an item"
        assert seen[0].get("defer_translation") is not True


class TestSignature:
    def test_process_wanted_item_accepts_defer_translation(self):
        import inspect

        from wanted_search import process_wanted_item

        params = inspect.signature(process_wanted_item).parameters
        assert "defer_translation" in params
        assert params["defer_translation"].default is False, (
            "opt-out: every existing caller must keep today's behaviour"
        )


class TestTheDrainCanActuallyFindWhatTheSearchLeftBehind:
    """The load-bearing invariant of the whole handoff.

    Queuing the translation is only useful if the drain can still find the
    subtitle to translate. It does not receive the sidecar path: the queue row
    carries the *media* file, and `translate_file` rediscovers the sidecar via
    `find_any_source_sub` (Case C2b). So the name Steps 2 and 4 write must be
    a name that probe recognises.

    Both halves are pinned here rather than assumed, because they live in
    different modules and nothing else would notice them drifting apart.
    """

    def test_the_name_step2_writes_is_a_name_the_probe_recognises(self, app_ctx, tmp_path):
        import os

        from translator._helpers import find_any_source_sub

        mkv = tmp_path / "Show - S01E01.mkv"
        mkv.write_bytes(b"fake")

        # Exactly how both steps build the target path.
        source_language = "en"
        base = os.path.splitext(str(mkv))[0]
        for fmt in ("ass", "srt"):
            written = f"{base}.{source_language}.{fmt}"
            with open(written, "w", encoding="utf-8") as fh:
                fh.write("source subtitle")

            path, lang = find_any_source_sub(str(mkv), target_language="de")

            assert path == written, (
                f"the drain would not find the {fmt.upper()} sidecar the search left at "
                f"{written} — it resolved {path} instead"
            )
            assert lang == source_language
            os.remove(written)

    def test_a_target_language_sidecar_is_not_mistaken_for_a_source(self, app_ctx, tmp_path):
        """Negative control: the probe must not hand the drain the target itself."""
        import os

        from translator._helpers import find_any_source_sub

        mkv = tmp_path / "Show - S01E02.mkv"
        mkv.write_bytes(b"fake")
        with open(f"{os.path.splitext(str(mkv))[0]}.de.srt", "w", encoding="utf-8") as fh:
            fh.write("already the target")

        path, _ = find_any_source_sub(str(mkv), target_language="de")
        assert path is None, f"the target-language sidecar was offered as a source: {path}"
