"""The scheduled search must not run the translate fallback inline.

Prod 2026-08-14: a wanted_search tick overran its 1800s timeout, was asked to
stop, and 60s later was still running — recorded as `timeout_abandoned`. The
cancellation itself worked; the phase could not reach an exit.

Why: the provider phase submits every eligible item to a ThreadPoolExecutor
and, on cancel, cancels the *pending* futures and breaks. Leaving the `with`
block then calls shutdown(wait=True), which blocks on the futures already
running. And a running future is `process_wanted_item`, whose Step 5
(`_fallback_translate_file`) performs an ffmpeg extraction plus a full LLM
translation — the same log window shows

    subprocess.TimeoutExpired: Command '['ffmpeg', ... '-map', '0:s:0', ...]'
        timed out after 300 seconds

300s for the extraction alone, against a 60s grace. This is the original
2026-08-12 defect — translation inside the search — reached through the
per-item door rather than the bulk sidecar phase.

The fix mirrors the sidecar handoff: where a drain worker exists, the search
hands the work over; where it does not, the search keeps doing it itself, so
installs with automation off lose nothing. `dry_run` already stops before
Step 5 for the same reason, which is the seam this reuses.
"""

from unittest.mock import MagicMock

from db.wanted import upsert_wanted_item


def _make_wanted_item(tmp_path, target_language="de"):
    mkv = tmp_path / "ep.mkv"
    mkv.touch()
    row_id, _ = upsert_wanted_item(
        item_type="episode",
        file_path=str(mkv),
        target_language=target_language,
    )
    return row_id, mkv


def _no_provider_hits(monkeypatch):
    mock_mgr = MagicMock()
    mock_mgr.search.return_value = []
    mock_mgr.search_and_download_best.return_value = None
    monkeypatch.setattr("wanted_search.process.get_provider_manager", lambda: mock_mgr)
    return mock_mgr


class TestStep5Gate:
    def test_disallowed_fallback_is_not_reached(self, app_ctx, monkeypatch, tmp_path):
        """One in-flight item must cost a provider search, not a translation."""
        from wanted_search import process_wanted_item

        item_id, _ = _make_wanted_item(tmp_path)
        _no_provider_hits(monkeypatch)

        called = []
        monkeypatch.setattr(
            "wanted_search.process._fallback_translate_file",
            lambda ctx: called.append(True) or {"status": "should-not-happen"},
        )

        out = process_wanted_item(item_id, allow_translate_fallback=False)

        assert called == [], "the scheduled path must not translate inline"
        assert out.get("status") == "not_found"

    def test_default_still_translates(self, app_ctx, monkeypatch, tmp_path):
        """Regression guard: manual search and the API keep today's behaviour.

        The gate is opt-out, not opt-in — anything that does not ask for the
        handoff must be unaffected."""
        from wanted_search import process_wanted_item

        item_id, _ = _make_wanted_item(tmp_path)
        _no_provider_hits(monkeypatch)

        called = []
        monkeypatch.setattr(
            "wanted_search.process._fallback_translate_file",
            lambda ctx: called.append(True) or {"status": "not_found", "wanted_id": ctx["item_id"]},
        )

        process_wanted_item(item_id)

        assert called == [True], "the default path must still reach Step 5"


class TestScheduledSearchWiring:
    def _settings(self, monkeypatch, *, automation: bool):
        from config import get_settings

        s = get_settings()
        monkeypatch.setattr(s, "wanted_search_order", "fair", raising=False)
        monkeypatch.setattr(s, "wanted_search_max_items_per_run", 10, raising=False)
        monkeypatch.setattr(s, "wanted_max_search_attempts", 3, raising=False)
        monkeypatch.setattr(s, "wanted_adaptive_backoff_enabled", True, raising=False)
        monkeypatch.setattr(s, "wanted_auto_translate", False, raising=False)
        monkeypatch.setattr(s, "subtitle_automation_enabled", automation, raising=False)
        monkeypatch.setattr(s, "wanted_auto_extract", False, raising=False)
        return s

    def _item(self, item_id=1):
        return {
            "id": item_id,
            "title": f"item-{item_id}",
            "file_path": f"/media/item-{item_id}.mkv",
            "target_language": "de",
            "existing_sub": "",
            "priority": "standard",
            "upgrade_candidate": False,
            "last_search_at": None,
            "retry_after": None,
            "search_count": 0,
        }

    def _run(self, app_ctx, monkeypatch, *, automation: bool):
        from unittest.mock import patch

        from services.wanted_search_runner import run_wanted_search

        self._settings(monkeypatch, automation=automation)
        seen: list[dict] = []

        def _fake_process(item_id, *args, **kwargs):
            seen.append(kwargs)
            return {"status": "not_found", "wanted_id": item_id}

        with (
            patch("db.wanted.get_items_for_scheduled_search", return_value=[self._item()]),
            patch("wanted_search.process_wanted_item", side_effect=_fake_process),
        ):
            run_wanted_search(app=app_ctx, include_upgrades=True)
        return seen

    def test_automation_on_hands_the_fallback_over(self, app_ctx, monkeypatch):
        seen = self._run(app_ctx, monkeypatch, automation=True)

        assert seen, "the provider phase must have run an item"
        assert seen[0].get("allow_translate_fallback") is False

    def test_automation_off_keeps_the_inline_fallback(self, app_ctx, monkeypatch):
        """Nothing would drain a queued item on these installs, so the search
        must keep doing this work itself."""
        seen = self._run(app_ctx, monkeypatch, automation=False)

        assert seen, "the provider phase must have run an item"
        assert seen[0].get("allow_translate_fallback") is not False


class TestEmbeddedSourceHandoff:
    """Step 5's exit must hand an embedded source track to the drain.

    Prod 2026-11-11: 134 German-wanted episodes with a full English track in
    the container had never been translated. The scheduled search stops before
    Step 5 when the automation queue is on, and the queue only receives items
    the scanner discovers new or whose embedded track is the target language.
    A requeued item with only a source-language track reached neither, and
    went into a month of no-result backoff instead.
    """

    def _item(self, tmp_path, embedded):
        mkv = tmp_path / "ep.mkv"
        mkv.touch()
        row_id, _ = upsert_wanted_item(
            item_type="episode",
            file_path=str(mkv),
            target_language="de",
            embedded_languages=embedded,
        )
        return row_id, str(mkv)

    def _run(self, monkeypatch, item_id, *, auto_translate=True, any_source=True):
        from config import get_settings
        from wanted_search import process_wanted_item

        settings = get_settings()
        monkeypatch.setattr(settings, "wanted_auto_translate", auto_translate, raising=False)
        monkeypatch.setattr(settings, "auto_translate_any_source", any_source, raising=False)
        monkeypatch.setattr(settings, "source_language", "en", raising=False)
        _no_provider_hits(monkeypatch)
        monkeypatch.setattr(
            "wanted_search.process._fallback_translate_file",
            lambda ctx: {"status": "should-not-happen"},
        )
        return process_wanted_item(item_id, allow_translate_fallback=False)

    def _queued(self, item_id):
        from db.models.core import SubtitleAutomationQueueEntry

        return [
            (row.task_type, row.state, row.source_language)
            for row in SubtitleAutomationQueueEntry.query.filter_by(wanted_item_id=item_id)
        ]

    def test_embedded_source_track_is_queued_for_translation(self, app_ctx, monkeypatch, tmp_path):
        item_id, _ = self._item(tmp_path, [{"lang": "eng", "format": "ass"}])

        out = self._run(monkeypatch, item_id)

        assert out.get("status") == "not_found"
        assert self._queued(item_id) == [("sidecar_translate", "pending", "en")]

    def test_no_embedded_track_queues_nothing(self, app_ctx, monkeypatch, tmp_path):
        item_id, _ = self._item(tmp_path, [])

        self._run(monkeypatch, item_id)

        assert self._queued(item_id) == []

    def test_auto_translate_off_queues_nothing(self, app_ctx, monkeypatch, tmp_path):
        """Original-only searches (auto-translate off, provisional re-seek)
        must never turn into a translation."""
        item_id, _ = self._item(tmp_path, [{"lang": "eng", "format": "ass"}])

        self._run(monkeypatch, item_id, auto_translate=False)

        assert self._queued(item_id) == []

    def test_strict_source_mode_skips_other_languages(self, app_ctx, monkeypatch, tmp_path):
        """translate_file would refuse a French track in strict English mode
        and go on to providers and Whisper from the drain instead."""
        item_id, _ = self._item(tmp_path, [{"lang": "fre", "format": "ass"}])

        self._run(monkeypatch, item_id, any_source=False)

        assert self._queued(item_id) == []

    def test_strict_source_mode_takes_the_preferred_track(self, app_ctx, monkeypatch, tmp_path):
        item_id, _ = self._item(
            tmp_path, [{"lang": "fre", "format": "ass"}, {"lang": "eng", "format": "srt"}]
        )

        self._run(monkeypatch, item_id, any_source=False)

        assert self._queued(item_id) == [("sidecar_translate", "pending", "en")]

    def test_strict_source_mode_follows_the_profile_source(self, app_ctx, monkeypatch, tmp_path):
        """Step 5 translates from the profile's source language when it has one."""
        item_id, _ = self._item(
            tmp_path, [{"lang": "eng", "format": "ass"}, {"lang": "jpn", "format": "srt"}]
        )
        monkeypatch.setattr(
            "services.mt_provisional._resolve_profile_for_item",
            lambda item: {"source_language": "ja"},
        )

        self._run(monkeypatch, item_id, any_source=False)

        assert self._queued(item_id) == [("sidecar_translate", "pending", "ja")]
