"""A failed translation is a transient environment fault, not a terminal one.

Prod 2026-08-04: an Ollama outage made every Step-5 translation fail, and
each failure wrote ``status='failed'`` with NO ``failure_kind`` — the same
dead-end class as ``file_missing`` (the search selector only ever fetches
``status='wanted'``, so those 21 rows were never retried after the backend
recovered). Worse, ``_fallback_translate_file`` is also reached from the
sidecar-translate phase and the automation drain worker, where no finally-net
exists to restore the status.

The fix routes both failure exits of ``_fallback_translate_file`` through
``record_search_outcome(kind='translation_error')``: error-side backoff
(6h → 24h → 3d → 7d → 30d cap), no ``search_count`` charge, status untouched
so the row stays (or returns to) ``'wanted'`` and self-heals when the
translation backend comes back.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from db.wanted import get_wanted_item, upsert_wanted_item
from services.wanted_search_outcome import record_search_outcome


class TestRecordOutcomeTranslationError:
    """Unit level: the new outcome kind writes the right columns."""

    @pytest.fixture
    def mock_db(self, monkeypatch):
        get_item = MagicMock(return_value={"id": 42, "error_count": 0})
        update = MagicMock(return_value=True)
        monkeypatch.setattr("db.wanted.get_wanted_item", get_item, raising=True)
        monkeypatch.setattr("db.wanted.update_wanted_search_outcome", update, raising=True)
        return {"get_wanted_item": get_item, "update": update}

    def test_first_failure_gets_error_backoff_not_search_charge(self, mock_db):
        record_search_outcome(
            7, kind="translation_error", error_message="Ollama: connection refused"
        )

        kwargs = mock_db["update"].call_args.kwargs
        assert kwargs["failure_kind"] == "translation_error"
        assert kwargs["error_count_increment"] == 1
        assert "search_count_increment" not in kwargs
        assert "status" not in kwargs
        assert kwargs["error"].startswith("Ollama")
        delta = kwargs["retry_after"] - datetime.now(UTC)
        assert timedelta(hours=5) < delta < timedelta(hours=7)

    def test_repeat_failures_walk_the_error_backoff_curve(self, mock_db):
        mock_db["get_wanted_item"].return_value = {"id": 42, "error_count": 2}

        record_search_outcome(7, kind="translation_error")

        kwargs = mock_db["update"].call_args.kwargs
        delta = kwargs["retry_after"] - datetime.now(UTC)
        assert timedelta(days=2, hours=23) < delta < timedelta(days=3, hours=1)


class TestFallbackTranslateFailurePath:
    """Integration level: both failure exits of ``_fallback_translate_file``
    book the outcome instead of writing the terminal ``failed`` status.

    The ctx is fed directly — exactly how the sidecar phase and the
    automation drain call it, i.e. WITHOUT the searching-flip finally-net.
    The row must therefore still read ``'wanted'`` afterwards.
    """

    def _make_item(self, tmp_path):
        mkv = tmp_path / "ep.mkv"
        mkv.touch()
        row_id, _ = upsert_wanted_item(
            item_type="episode",
            file_path=str(mkv),
            target_language="de",
        )
        return row_id, str(mkv)

    def _ctx(self, item_id, file_path):
        item = get_wanted_item(item_id)
        return {
            "item": item,
            "item_id": item_id,
            "item_lang": "de",
            "settings": MagicMock(),
            "auto_translate": True,
            "file_path": file_path,
        }

    def _run(self, ctx, translate_result=None, translate_raises=None):
        from wanted_search import process as proc

        translate = MagicMock()
        if translate_raises is not None:
            translate.side_effect = translate_raises
        else:
            translate.return_value = translate_result
        with (
            patch("translator.translate_file", translate),
            patch.object(proc, "create_job", return_value={"id": 1}),
            patch.object(proc, "update_job"),
            patch.object(proc, "record_stat"),
            patch.object(proc, "_build_arr_context", return_value={}),
        ):
            return proc._fallback_translate_file(ctx)

    def test_translate_failure_keeps_the_row_wanted_with_backoff(self, app_ctx, tmp_path):
        item_id, file_path = self._make_item(tmp_path)

        out = self._run(
            self._ctx(item_id, file_path),
            translate_result={"success": False, "error": "LLM backend unreachable"},
        )

        assert out["status"] == "failed", "callers still see the failure in the result dict"
        item = get_wanted_item(item_id)
        assert item["status"] == "wanted", "a failed translation must not be terminal"
        assert item["failure_kind"] == "translation_error"
        assert (item.get("error_count") or 0) == 1
        assert (item.get("search_count") or 0) == 0, "no provider was asked — no charge"
        assert item["retry_after"] is not None
        assert "LLM backend unreachable" in (item.get("error") or "")

    def test_unexpected_exception_keeps_the_row_wanted_with_backoff(self, app_ctx, tmp_path):
        item_id, file_path = self._make_item(tmp_path)

        out = self._run(
            self._ctx(item_id, file_path),
            translate_raises=RuntimeError("ffmpeg exploded"),
        )

        assert out["status"] == "failed"
        item = get_wanted_item(item_id)
        assert item["status"] == "wanted", "an unexpected crash must not be terminal"
        assert item["failure_kind"] == "translation_error"
        assert (item.get("error_count") or 0) == 1
        assert item["retry_after"] is not None


class TestRestoreNetKeepsErrorText:
    """The finally-net used to clobber the error column with '' when it
    restored a row out of 'searching' — the Health page then showed a
    file_missing/translation_error row with no error text at all."""

    def test_restore_preserves_the_recorded_error(self, app_ctx, tmp_path):
        from db.wanted import update_wanted_status
        from wanted_search.process import _restore_if_left_searching

        mkv = tmp_path / "ep.mkv"
        mkv.touch()
        item_id, _ = upsert_wanted_item(
            item_type="episode",
            file_path=str(mkv),
            target_language="de",
        )
        update_wanted_status(item_id, "searching")
        record_search_outcome(item_id, kind="translation_error", error_message="boom")

        _restore_if_left_searching(item_id, "wanted")

        item = get_wanted_item(item_id)
        assert item["status"] == "wanted"
        assert "boom" in (item.get("error") or ""), "the net must not clobber the error text"
