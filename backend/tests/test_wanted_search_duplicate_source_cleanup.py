"""Regression tests: the translate steps must never delete a pre-existing file.

When ``manager.save_subtitle`` raises ``DuplicateSubtitleError``, the step
rebinds ``actual_source_path`` to ``dup_err.existing_path`` — a file that was
already on disk (usually the user's own sidecar). The "temp file cleanup"
afterwards used to ``os.remove`` that path unconditionally: an automatic
wanted-search or webhook run hard-deleted user files with no trash and no
backup. Now only files created in the same run are cleaned up.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from error_handler import DuplicateSubtitleError


def _ctx(tmp_path, settings):
    item = {
        "id": 1,
        "title": "Ep",
        "sonarr_series_id": None,
    }
    return {
        "item": item,
        "item_id": 1,
        "item_lang": "de",
        "settings": settings,
        "manager": MagicMock(),
        "_pf": {"must_contain": "", "must_not_contain": ""},
        "file_path": str(tmp_path / "ep.mkv"),
        # Pre-built so the step never calls build_query_from_wanted (which
        # needs a full wanted-item row + *arr metadata).
        "source_query": MagicMock(),
    }


def _settings():
    s = MagicMock()
    s.source_language = "en"
    s.target_language_name = "German"
    return s


@pytest.fixture
def preexisting_sidecar(tmp_path):
    (tmp_path / "ep.mkv").write_bytes(b"fake")
    sidecar = tmp_path / "ep.en.srt"
    sidecar.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n", encoding="utf-8")
    return sidecar


class TestDuplicateSourceNeverDeleted:
    def test_srt_step_keeps_existing_sidecar_on_success(self, tmp_path, preexisting_sidecar):
        from wanted_search.process import _try_source_srt_translation

        ctx = _ctx(tmp_path, _settings())
        manager = ctx["manager"]

        result = MagicMock()
        result.content = b"srt-bytes"
        manager.search_and_download_best.return_value = result
        manager.save_subtitle.side_effect = DuplicateSubtitleError(
            "hash", str(preexisting_sidecar), str(tmp_path / "ep.en.srt")
        )

        with (
            patch("wanted_search.process.create_job", return_value={"id": 7}),
            patch("wanted_search.process.update_job"),
            patch("wanted_search.process.record_stat"),
            patch("wanted_search.process.record_subtitle_download"),
            patch("wanted_search.process._build_arr_context", return_value={}),
            patch(
                "translator.translate_srt_from_file",
                return_value={"success": True, "output_path": str(tmp_path / "ep.de.srt")},
            ),
            patch("wanted_search.process.delete_wanted_item", create=True),
            patch("wanted_search.process._finish_found", create=True) as _,
        ):
            try:
                _try_source_srt_translation(ctx)
            except Exception:
                # Post-translate bookkeeping may fail in this stripped-down
                # harness — the invariant under test is filesystem-only.
                pass

        manager.save_subtitle.assert_called_once()
        assert preexisting_sidecar.exists(), (
            "a pre-existing sidecar surfaced via DuplicateSubtitleError must never be deleted"
        )

    def test_srt_step_keeps_existing_sidecar_on_translate_failure(
        self, tmp_path, preexisting_sidecar
    ):
        from wanted_search.process import _try_source_srt_translation

        ctx = _ctx(tmp_path, _settings())
        manager = ctx["manager"]

        result = MagicMock()
        result.content = b"srt-bytes"
        manager.search_and_download_best.return_value = result
        manager.save_subtitle.side_effect = DuplicateSubtitleError(
            "hash", str(preexisting_sidecar), str(tmp_path / "ep.en.srt")
        )

        with (
            patch("wanted_search.process.create_job", return_value={"id": 7}),
            patch("wanted_search.process.update_job"),
            patch("wanted_search.process.record_stat"),
            patch("wanted_search.process.record_subtitle_download"),
            patch("wanted_search.process._build_arr_context", return_value={}),
            patch(
                "translator.translate_srt_from_file",
                side_effect=RuntimeError("translation blew up"),
            ),
        ):
            # The step swallows the translation error in its outer catch and
            # moves on — only the filesystem invariant matters here.
            _try_source_srt_translation(ctx)

        manager.save_subtitle.assert_called_once()
        assert preexisting_sidecar.exists(), (
            "the error-path cleanup must not delete a pre-existing sidecar either"
        )

    def test_srt_step_still_cleans_up_own_temp_file(self, tmp_path):
        """A source file the step downloaded itself IS removed afterwards —
        the fix must not leave temp artefacts behind."""
        from wanted_search.process import _try_source_srt_translation

        (tmp_path / "ep.mkv").write_bytes(b"fake")
        ctx = _ctx(tmp_path, _settings())
        manager = ctx["manager"]

        downloaded = tmp_path / "ep.en.srt"

        def _save(result, path, series_id=None):
            downloaded.write_text("1\n00:00:01,000 --> 00:00:02,000\nHi\n", encoding="utf-8")
            return str(downloaded)

        result = MagicMock()
        result.content = b"srt-bytes"
        result.provider_name = "prov"
        result.subtitle_id = "sid"
        result.score = 1.0
        result.format.value = "srt"
        manager.search_and_download_best.return_value = result
        manager.save_subtitle.side_effect = _save

        with (
            patch("wanted_search.process.create_job", return_value={"id": 7}),
            patch("wanted_search.process.update_job"),
            patch("wanted_search.process.record_stat"),
            patch("wanted_search.process.record_subtitle_download"),
            patch("wanted_search.process._build_arr_context", return_value={}),
            patch(
                "translator.translate_srt_from_file",
                return_value={"success": True, "output_path": str(tmp_path / "ep.de.srt")},
            ),
        ):
            try:
                _try_source_srt_translation(ctx)
            except Exception:
                pass

        manager.save_subtitle.assert_called_once()
        assert not downloaded.exists(), "self-created temp source must still be cleaned up"
