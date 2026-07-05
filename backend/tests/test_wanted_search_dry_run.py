"""Tests for ``process_wanted_item``'s ``dry_run`` / ``bypass_existing_target_check``
parameters (feature #8b Phase 2 Task 2 — provisional-MT re-seek).

``dry_run=True`` previews whether a genuine provider original exists for a
wanted item WITHOUT writing anything to disk or the DB: no ``save_subtitle``,
no ``record_subtitle_download``, no ``delete_wanted_item``. This lets
``services.mt_reseek`` detect a qualifying original before deciding whether to
replace (auto_replace) or merely flag it (notify) — the normal "found" path
is atomic (search -> download -> save -> record -> delete, all before
returning), so there is no other point at which to intervene.

``bypass_existing_target_check=True`` skips the early "target sidecar already
exists" short-circuit. Provisional-MT items already HAVE a target-language
sidecar (the machine translation itself) — the ordinary gate would otherwise
make the re-seek job a permanent no-op for MT rows saved as ``.ass``.

Mirrors the mocking style of ``tests/test_wanted_search.py``
(``TestSaveSubtitleReturnPathPropagated``): a real wanted item + real DB via
``app_ctx``, with ``get_provider_manager`` mocked so no real network/disk I/O
for subtitle content occurs.
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


def _make_subtitle_result(language="de", score=80, fmt_value="ass", content=b"dummy"):
    r = MagicMock()
    r.provider_name = "test_provider"
    r.subtitle_id = "sub123"
    r.language = language
    r.format.value = fmt_value
    r.score = score
    r.content = content
    return r


class TestDryRunTargetAssDirect:
    """Step 1 (target-language ASS direct) dry_run short-circuit."""

    def test_dry_run_skips_all_writes_and_reports_found(self, app_ctx, monkeypatch, tmp_path):
        from wanted_search import process_wanted_item

        item_id, _ = _make_wanted_item(tmp_path)
        result = _make_subtitle_result(score=95, fmt_value="ass")

        mock_mgr = MagicMock()
        mock_mgr.search.return_value = []
        mock_mgr.search_and_download_best.return_value = result

        monkeypatch.setattr("wanted_search.process.get_provider_manager", lambda: mock_mgr)

        recorded = []
        deleted = []
        monkeypatch.setattr(
            "wanted_search.process.record_subtitle_download",
            lambda *a, **kw: recorded.append((a, kw)),
        )
        monkeypatch.setattr("wanted_search.process.delete_wanted_item", lambda i: deleted.append(i))

        out = process_wanted_item(item_id, auto_translate=False, dry_run=True)

        assert not mock_mgr.save_subtitle.called, "dry_run must not write the subtitle to disk"
        assert recorded == [], "dry_run must not record a subtitle_downloads row"
        assert deleted == [], "dry_run must not delete the wanted item"
        assert out.get("status") == "found"
        assert out.get("dry_run") is True
        assert out.get("provider") == "test_provider"
        assert out.get("score") == 95
        assert out.get("output_path", "").endswith(".de.ass")


class TestDryRunTargetSrtDirect:
    """Step 3 (target-language SRT direct) dry_run short-circuit — reached when
    Step 1 (ASS) finds nothing and ``wanted_skip_srt_on_no_ass`` is off."""

    def test_dry_run_skips_all_writes_when_only_srt_found(self, app_ctx, monkeypatch, tmp_path):
        from config import get_settings
        from wanted_search import process_wanted_item

        item_id, _ = _make_wanted_item(tmp_path)

        srt_result = _make_subtitle_result(score=70, fmt_value="srt")

        mock_mgr = MagicMock()

        def _search_and_download(query, format_filter=None, **kw):
            from providers.base import SubtitleFormat

            if format_filter == SubtitleFormat.SRT:
                return srt_result
            return None

        mock_mgr.search.return_value = []
        mock_mgr.search_and_download_best.side_effect = _search_and_download
        monkeypatch.setattr("wanted_search.process.get_provider_manager", lambda: mock_mgr)

        recorded = []
        deleted = []
        monkeypatch.setattr(
            "wanted_search.process.record_subtitle_download",
            lambda *a, **kw: recorded.append((a, kw)),
        )
        monkeypatch.setattr("wanted_search.process.delete_wanted_item", lambda i: deleted.append(i))

        # wanted_skip_srt_on_no_ass is a UI-first (DB-only) setting, not
        # env-loadable — flip it directly on the live settings singleton.
        monkeypatch.setattr(get_settings(), "wanted_skip_srt_on_no_ass", False)

        out = process_wanted_item(item_id, auto_translate=False, dry_run=True)

        assert not mock_mgr.save_subtitle.called
        assert recorded == []
        assert deleted == []
        assert out.get("status") == "found"
        assert out.get("dry_run") is True
        assert out.get("score") == 70
        assert out.get("output_path", "").endswith(".de.srt")


class TestDryRunNoResultStopsBeforeFallback:
    """When providers return nothing, dry_run must return not_found WITHOUT
    invoking the embedded/translate fallback (Step 5) — that pipeline has its
    own disk-writing side effects (extraction, jobs) that dry_run does not
    attempt to make safe."""

    def test_dry_run_no_provider_hits_returns_not_found_without_fallback(
        self, app_ctx, monkeypatch, tmp_path
    ):
        from wanted_search import process_wanted_item

        item_id, _ = _make_wanted_item(tmp_path)

        mock_mgr = MagicMock()
        mock_mgr.search.return_value = []
        mock_mgr.search_and_download_best.return_value = None
        monkeypatch.setattr("wanted_search.process.get_provider_manager", lambda: mock_mgr)

        fallback_called = []
        monkeypatch.setattr(
            "wanted_search.process._fallback_translate_file",
            lambda ctx: fallback_called.append(True) or {"status": "should-not-happen"},
        )

        out = process_wanted_item(item_id, auto_translate=False, dry_run=True)

        assert fallback_called == [], "dry_run must never reach the translate/embedded fallback"
        assert out.get("status") == "not_found"
        assert out.get("dry_run") is True


class TestDryRunFalsePreservesExistingBehaviour:
    """Regression: omitting dry_run (default False) must behave exactly like
    before this feature — the real write path still runs to completion."""

    def test_dry_run_omitted_still_writes_and_deletes(self, app_ctx, monkeypatch, tmp_path):
        from wanted_search import process_wanted_item

        item_id, _ = _make_wanted_item(tmp_path)
        result = _make_subtitle_result(score=95, fmt_value="ass")

        mock_mgr = MagicMock()
        mock_mgr.search.return_value = []
        mock_mgr.search_and_download_best.return_value = result
        mock_mgr.save_subtitle.return_value = str(tmp_path / "ep.de.ass")
        monkeypatch.setattr("wanted_search.process.get_provider_manager", lambda: mock_mgr)
        monkeypatch.setattr("nfo_export.maybe_write_nfo", lambda *a, **kw: None)
        monkeypatch.setattr("wanted_search.process._try_auto_sync", lambda *a, **kw: None)

        recorded = []
        deleted = []
        monkeypatch.setattr(
            "wanted_search.process.record_subtitle_download",
            lambda *a, **kw: recorded.append((a, kw)),
        )
        monkeypatch.setattr("wanted_search.process.delete_wanted_item", lambda i: deleted.append(i))

        out = process_wanted_item(item_id, auto_translate=False)

        assert mock_mgr.save_subtitle.called
        assert len(recorded) == 1
        assert deleted == [item_id]
        assert out.get("status") == "found"
        assert "dry_run" not in out


class TestBypassExistingTargetCheck:
    """``bypass_existing_target_check=True`` — needed so mt_reseek can
    re-search provisional items whose existing sidecar IS the machine
    translation being re-sought against (the ordinary gate treats presence of
    a target .ass as "already satisfied" regardless of its source)."""

    def _seed_existing_ass(self, mkv_path, lang="de"):
        base = str(mkv_path)[: -len(".mkv")]
        ass_path = f"{base}.{lang}.ass"
        with open(ass_path, "wb") as fh:
            fh.write(b"[Script Info]\n")
        return ass_path

    def test_default_skips_when_target_ass_already_present(self, app_ctx, monkeypatch, tmp_path):
        from wanted_search import process_wanted_item

        item_id, mkv_path = _make_wanted_item(tmp_path)
        self._seed_existing_ass(mkv_path)

        mock_mgr = MagicMock()
        monkeypatch.setattr("wanted_search.process.get_provider_manager", lambda: mock_mgr)

        out = process_wanted_item(item_id, auto_translate=False)

        assert out.get("status") == "skipped"
        assert not mock_mgr.search_and_download_best.called

    def test_bypass_proceeds_to_search_despite_existing_ass(self, app_ctx, monkeypatch, tmp_path):
        from wanted_search import process_wanted_item

        item_id, mkv_path = _make_wanted_item(tmp_path)
        self._seed_existing_ass(mkv_path)

        result = _make_subtitle_result(score=95, fmt_value="ass")
        mock_mgr = MagicMock()
        mock_mgr.search.return_value = []
        mock_mgr.search_and_download_best.return_value = result
        monkeypatch.setattr("wanted_search.process.get_provider_manager", lambda: mock_mgr)

        out = process_wanted_item(
            item_id, auto_translate=False, dry_run=True, bypass_existing_target_check=True
        )

        assert mock_mgr.search_and_download_best.called
        assert out.get("status") == "found"
        assert out.get("dry_run") is True
