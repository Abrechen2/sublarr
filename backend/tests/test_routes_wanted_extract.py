"""Tests for routes/wanted/{extract,batch_extract,batch_probe}.py — extract + batch endpoints."""

import threading
import time
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text

from app import create_app
from db import get_db
from routes.batch_state import (
    _batch_extract_lock,
    _batch_extract_state,
    _batch_probe_lock,
    _batch_probe_state,
)

# ---------------------------------------------------------------------------
# Patch targets
#
# Top-level imports in extract.py (emit_event, log_activity, remove_subtitle_stream,
# remove_subtitle_streams, socketio) are bound at import time, so they must be
# patched on the module object: "routes.wanted.extract.<name>".
#
# Lazy imports inside function bodies (ass_utils, config, db.wanted, translator)
# are resolved at call time, so they are patched at the source module.
# ---------------------------------------------------------------------------

# -- lazy (patched at source) --
P_GET_MEDIA = "ass_utils.get_media_streams"
P_SELECT_BEST = "ass_utils.select_best_subtitle_stream"
P_EXTRACT_STREAM = "ass_utils.extract_subtitle_stream"
P_HAS_TARGET_AUDIO = "ass_utils.has_target_language_audio"
P_GET_SUB_OUT_PATH = "ass_utils.get_subtitle_stream_output_path"
P_GET_SETTINGS = "config.get_settings"
P_GET_WANTED_ITEM = "db.wanted.get_wanted_item"
P_GET_WANTED_ITEMS = "db.wanted.get_wanted_items"
P_UPDATE_EXISTING_SUB = "db.wanted.update_existing_sub"
P_UPDATE_STATUS = "db.wanted.update_wanted_status"
P_OUTPUT_FOR_LANG = "translator.get_output_path_for_lang"

# -- top-level (patched on module object) --
# The single-extract route + _extract_embedded_sub helper live in
# routes.wanted.extract. _run_batch_extract moved to routes.wanted.batch_extract,
# _run_batch_probe to routes.wanted.batch_probe (B1E split, 2026-04-18).
# Each module imports emit_event/socketio/remux independently, so patches must
# target the module where the function under test was defined.
_M = "routes.wanted.extract"
P_EMIT_EVENT = f"{_M}.emit_event"
P_LOG_ACTIVITY = f"{_M}.log_activity"
P_REMOVE_STREAM = f"{_M}.remove_subtitle_stream"

_M_BE = "routes.wanted.batch_extract"
P_EMIT_EVENT_BE = f"{_M_BE}.emit_event"
P_SOCKETIO_BE = f"{_M_BE}.socketio"

_M_BP = "routes.wanted.batch_probe"
P_EMIT_EVENT_BP = f"{_M_BP}.emit_event"
P_SOCKETIO_BP = f"{_M_BP}.socketio"
P_REMOVE_STREAMS_BP = f"{_M_BP}.remove_subtitle_streams"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKE_MKV = "/media/show/ep01.mkv"


def _insert_wanted(app, title="Ep", file_path=_FAKE_MKV, existing_sub="", status="wanted"):
    """Insert a wanted_item row and return its id."""
    with app.app_context():
        db = get_db()
        db.execute(
            text(
                "INSERT INTO wanted_items"
                " (title, file_path, item_type, target_language, status,"
                "  priority, error_count, existing_sub, added_at, updated_at)"
                " VALUES (:t, :fp, 'episode', 'de', :s,"
                "  'standard', 0, :es, datetime('now'), datetime('now'))"
            ),
            {"t": title, "fp": file_path, "s": status, "es": existing_sub},
        )
        db.commit()
        row = db.execute(text("SELECT id FROM wanted_items ORDER BY id DESC LIMIT 1")).fetchone()
        return row[0]


@pytest.fixture
def app_client(temp_db):
    """Flask app + test client sharing the same DB."""
    app = create_app(testing=True)
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    with app.test_client() as client:
        yield app, client


@pytest.fixture(autouse=True)
def _reset_batch_state():
    """Ensure batch state is clean before and after each test."""
    for state, lock in [
        (_batch_extract_state, _batch_extract_lock),
        (_batch_probe_state, _batch_probe_lock),
    ]:
        with lock:
            state["running"] = False
            state["total"] = 0
            state["processed"] = 0
            state.pop("succeeded", None)
            state.pop("found", None)
            state.pop("extracted", None)
            state["failed"] = 0
            state.pop("skipped", None)
            state["current_item"] = None
    yield
    for state, lock in [
        (_batch_extract_state, _batch_extract_lock),
        (_batch_probe_state, _batch_probe_lock),
    ]:
        with lock:
            state["running"] = False


# ===========================================================================
# POST /api/v1/wanted/<item_id>/extract — single-item extract
# ===========================================================================


class TestExtractEmbeddedSubEndpoint:
    """Tests for the POST /api/v1/wanted/<item_id>/extract route."""

    def test_item_not_found(self, app_client):
        _, client = app_client
        resp = client.post("/api/v1/wanted/99999/extract")
        assert resp.status_code == 404
        assert "Item not found" in resp.get_json()["error"]

    def test_file_not_found(self, app_client):
        app, client = app_client
        item_id = _insert_wanted(app, file_path="/nonexistent/video.mkv")
        resp = client.post(f"/api/v1/wanted/{item_id}/extract")
        assert resp.status_code == 404
        assert "File not found" in resp.get_json()["error"]

    def test_file_not_video_container(self, app_client, tmp_path):
        txt_file = tmp_path / "notes.txt"
        txt_file.write_text("not a video")
        app, client = app_client
        item_id = _insert_wanted(app, file_path=str(txt_file))
        resp = client.post(f"/api/v1/wanted/{item_id}/extract")
        assert resp.status_code == 400
        assert "not a video container" in resp.get_json()["error"]

    def test_no_subtitle_stream_found(self, app_client, tmp_path):
        mkv = tmp_path / "video.mkv"
        mkv.write_bytes(b"\x1a\x45\xdf\xa3")
        app, client = app_client
        item_id = _insert_wanted(app, file_path=str(mkv))

        with (
            patch(P_GET_MEDIA, return_value={"streams": []}),
            patch(P_SELECT_BEST, return_value=None),
        ):
            resp = client.post(f"/api/v1/wanted/{item_id}/extract")
        assert resp.status_code == 404
        assert "No suitable subtitle stream" in resp.get_json()["error"]

    def test_successful_extraction_auto_select(self, app_client, tmp_path):
        mkv = tmp_path / "video.mkv"
        mkv.write_bytes(b"\x1a\x45\xdf\xa3")
        app, client = app_client
        item_id = _insert_wanted(app, file_path=str(mkv))

        stream_info = {
            "sub_index": 0,
            "stream_index": 2,
            "format": "ass",
            "language": "eng",
        }
        probe_data = {"streams": [{"codec_type": "subtitle", "codec_name": "ass", "index": 2}]}

        with (
            patch(P_GET_MEDIA, return_value=probe_data),
            patch(P_SELECT_BEST, return_value=stream_info),
            patch(P_EXTRACT_STREAM) as mock_extract,
            patch(P_OUTPUT_FOR_LANG, return_value="/out/video.de.ass"),
            patch(P_REMOVE_STREAM, return_value="/bak"),
            patch(P_UPDATE_EXISTING_SUB) as mock_update_sub,
            patch(P_UPDATE_STATUS) as mock_update_status,
            patch(P_EMIT_EVENT) as mock_emit,
            patch(P_LOG_ACTIVITY) as mock_log,
        ):
            resp = client.post(f"/api/v1/wanted/{item_id}/extract")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "extracted"
        assert data["format"] == "ass"
        assert data["output_path"] == "/out/video.de.ass"
        assert data["language"] == "eng"

        mock_extract.assert_called_once()
        mock_update_sub.assert_called_once_with(item_id, "ass")
        mock_update_status.assert_called_once_with(item_id, "extracted")
        mock_emit.assert_called_once()
        mock_log.assert_called_once()

    def test_extraction_with_specific_stream_index(self, app_client, tmp_path):
        mkv = tmp_path / "video.mkv"
        mkv.write_bytes(b"\x1a\x45\xdf\xa3")
        app, client = app_client
        item_id = _insert_wanted(app, file_path=str(mkv))

        probe_data = {
            "streams": [
                {"codec_type": "video", "index": 0},
                {"codec_type": "audio", "index": 1},
                {
                    "codec_type": "subtitle",
                    "codec_name": "subrip",
                    "index": 2,
                    "tags": {"language": "jpn"},
                },
                {
                    "codec_type": "subtitle",
                    "codec_name": "ass",
                    "index": 3,
                    "tags": {"language": "eng"},
                },
            ]
        }

        with (
            patch(P_GET_MEDIA, return_value=probe_data),
            patch(P_EXTRACT_STREAM),
            patch(P_OUTPUT_FOR_LANG, return_value="/out/video.de.ass"),
            patch(P_REMOVE_STREAM, return_value="/bak"),
            patch(P_UPDATE_EXISTING_SUB),
            patch(P_UPDATE_STATUS),
            patch(P_EMIT_EVENT),
            patch(P_LOG_ACTIVITY),
        ):
            resp = client.post(
                f"/api/v1/wanted/{item_id}/extract",
                json={"stream_index": 1},  # second subtitle stream (index 1)
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["format"] == "ass"  # second subtitle is ASS
        assert data["language"] == "eng"

    def test_extraction_with_stream_index_srt_codec(self, app_client, tmp_path):
        """Verify SRT-family codecs resolve to format='srt'."""
        mkv = tmp_path / "video.mkv"
        mkv.write_bytes(b"\x1a\x45\xdf\xa3")
        app, client = app_client
        item_id = _insert_wanted(app, file_path=str(mkv))

        probe_data = {
            "streams": [
                {
                    "codec_type": "subtitle",
                    "codec_name": "subrip",
                    "index": 2,
                    "tags": {"language": "eng"},
                },
            ]
        }

        with (
            patch(P_GET_MEDIA, return_value=probe_data),
            patch(P_EXTRACT_STREAM),
            patch(P_OUTPUT_FOR_LANG, return_value="/out/video.de.srt"),
            patch(P_REMOVE_STREAM, return_value="/bak"),
            patch(P_UPDATE_EXISTING_SUB),
            patch(P_UPDATE_STATUS),
            patch(P_EMIT_EVENT),
            patch(P_LOG_ACTIVITY),
        ):
            resp = client.post(
                f"/api/v1/wanted/{item_id}/extract",
                json={"stream_index": 0},
            )

        assert resp.status_code == 200
        assert resp.get_json()["format"] == "srt"

    def test_extraction_with_target_language_override(self, app_client, tmp_path):
        mkv = tmp_path / "video.mkv"
        mkv.write_bytes(b"\x1a\x45\xdf\xa3")
        app, client = app_client
        item_id = _insert_wanted(app, file_path=str(mkv))

        stream_info = {"sub_index": 0, "stream_index": 2, "format": "srt", "language": "jpn"}

        with (
            patch(P_GET_MEDIA, return_value={"streams": []}),
            patch(P_SELECT_BEST, return_value=stream_info),
            patch(P_EXTRACT_STREAM),
            patch(P_OUTPUT_FOR_LANG, return_value="/out/vid.en.srt") as mock_out,
            patch(P_REMOVE_STREAM, return_value="/bak"),
            patch(P_UPDATE_EXISTING_SUB),
            patch(P_UPDATE_STATUS),
            patch(P_EMIT_EVENT),
            patch(P_LOG_ACTIVITY),
        ):
            resp = client.post(
                f"/api/v1/wanted/{item_id}/extract",
                json={"target_language": "en"},
            )

        assert resp.status_code == 200
        # get_output_path_for_lang should have been called with the overridden language
        call_args = mock_out.call_args
        assert call_args[0][2] == "en"

    def test_empty_file_path(self, app_client):
        """Item with empty file_path returns 404."""
        app, client = app_client
        item_id = _insert_wanted(app, file_path="")
        resp = client.post(f"/api/v1/wanted/{item_id}/extract")
        assert resp.status_code == 404


# ===========================================================================
# POST /api/v1/wanted/batch-extract
# ===========================================================================


class TestBatchExtract:
    """Tests for the POST /api/v1/wanted/batch-extract route."""

    def test_batch_extract_with_item_ids(self, app_client):
        app, client = app_client
        item_id = _insert_wanted(app, existing_sub="embedded_ass")

        with patch("threading.Thread") as mock_thread:
            mock_thread.return_value = MagicMock()
            resp = client.post(
                "/api/v1/wanted/batch-extract",
                json={"item_ids": [item_id]},
            )

        assert resp.status_code == 202
        data = resp.get_json()
        assert data["status"] == "started"
        assert data["total_items"] == 1
        mock_thread.assert_called_once()

    def test_batch_extract_with_series_id(self, app_client):
        app, client = app_client
        _insert_wanted(app, title="Ep1")

        with patch("threading.Thread") as mock_thread:
            mock_thread.return_value = MagicMock()
            resp = client.post(
                "/api/v1/wanted/batch-extract",
                json={"series_id": 1},
            )

        # May return 202 (started) or 200 (nothing_to_do) depending on DB
        assert resp.status_code in (200, 202)

    def test_batch_extract_auto_discover_embedded(self, app_client):
        """Empty body discovers items with embedded_ass / embedded_srt / empty existing_sub."""
        app, client = app_client
        _insert_wanted(app, title="Embedded", existing_sub="embedded_srt")
        _insert_wanted(app, title="Empty", existing_sub="")

        with patch("threading.Thread") as mock_thread:
            mock_thread.return_value = MagicMock()
            resp = client.post("/api/v1/wanted/batch-extract", json={})

        assert resp.status_code == 202
        data = resp.get_json()
        assert data["total_items"] >= 2

    def test_batch_extract_excludes_sidecar(self, app_client):
        """Items with existing_sub='ass' or 'srt' are excluded from auto-discovery."""
        app, client = app_client
        _insert_wanted(app, title="Has Sidecar", existing_sub="ass")

        with patch("threading.Thread") as mock_thread:
            mock_thread.return_value = MagicMock()
            resp = client.post("/api/v1/wanted/batch-extract", json={})

        data = resp.get_json()
        assert data.get("status") == "nothing_to_do" or data.get("total_items", 0) == 0

    def test_batch_extract_nothing_eligible(self, app_client):
        _, client = app_client
        resp = client.post("/api/v1/wanted/batch-extract", json={})
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["status"] == "nothing_to_do"

    def test_batch_extract_conflict_already_running(self, app_client):
        app, client = app_client
        item_id = _insert_wanted(app)
        with _batch_extract_lock:
            _batch_extract_state["running"] = True
        try:
            resp = client.post(
                "/api/v1/wanted/batch-extract",
                json={"item_ids": [item_id]},
            )
            assert resp.status_code == 409
            assert "already running" in resp.get_json()["error"]
        finally:
            with _batch_extract_lock:
                _batch_extract_state["running"] = False

    def test_batch_extract_auto_translate_flag(self, app_client):
        app, client = app_client
        item_id = _insert_wanted(app)

        with patch("threading.Thread") as mock_thread:
            mock_thread.return_value = MagicMock()
            resp = client.post(
                "/api/v1/wanted/batch-extract",
                json={"item_ids": [item_id], "auto_translate": True},
            )

        assert resp.status_code == 202
        # Verify auto_translate=True was passed to the thread args
        thread_args = mock_thread.call_args[1]["args"]
        assert thread_args[1] is True  # second positional arg is auto_translate


# ===========================================================================
# GET /api/v1/wanted/batch-extract/status
# ===========================================================================


class TestBatchExtractStatus:
    def test_returns_state(self, app_client):
        _, client = app_client
        resp = client.get("/api/v1/wanted/batch-extract/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "running" in data
        assert data["running"] is False

    def test_returns_in_progress_state(self, app_client):
        _, client = app_client
        with _batch_extract_lock:
            _batch_extract_state.update(
                {"running": True, "total": 10, "processed": 3, "succeeded": 2, "failed": 1}
            )
        try:
            resp = client.get("/api/v1/wanted/batch-extract/status")
            data = resp.get_json()
            assert data["running"] is True
            assert data["total"] == 10
            assert data["processed"] == 3
        finally:
            with _batch_extract_lock:
                _batch_extract_state["running"] = False


# ===========================================================================
# POST /api/v1/wanted/batch-probe
# ===========================================================================


class TestBatchProbe:
    def test_batch_probe_starts(self, app_client):
        app, client = app_client
        _insert_wanted(app, title="Probe Me", existing_sub="")

        with patch("threading.Thread") as mock_thread:
            mock_thread.return_value = MagicMock()
            resp = client.post("/api/v1/wanted/batch-probe", json={})

        assert resp.status_code == 202
        data = resp.get_json()
        assert data["status"] == "started"
        assert data["total_items"] >= 1

    def test_batch_probe_nothing_to_probe(self, app_client):
        app, client = app_client
        _insert_wanted(app, title="Already Probed", existing_sub="ass")

        resp = client.post("/api/v1/wanted/batch-probe", json={})
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["status"] == "nothing_to_probe"

    def test_batch_probe_empty_db(self, app_client):
        _, client = app_client
        resp = client.post("/api/v1/wanted/batch-probe", json={})
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["status"] == "nothing_to_probe"

    def test_batch_probe_conflict_already_running(self, app_client):
        _, client = app_client
        with _batch_probe_lock:
            _batch_probe_state["running"] = True
        try:
            resp = client.post("/api/v1/wanted/batch-probe", json={})
            assert resp.status_code == 409
            assert "already running" in resp.get_json()["error"]
        finally:
            with _batch_probe_lock:
                _batch_probe_state["running"] = False

    def test_batch_probe_with_series_id(self, app_client):
        app, client = app_client
        _insert_wanted(app, title="Series Ep", existing_sub="")

        with patch("threading.Thread") as mock_thread:
            mock_thread.return_value = MagicMock()
            resp = client.post("/api/v1/wanted/batch-probe", json={"series_id": 1})

        assert resp.status_code in (200, 202)


# ===========================================================================
# GET /api/v1/wanted/batch-probe/status
# ===========================================================================


class TestBatchProbeStatus:
    def test_returns_state(self, app_client):
        _, client = app_client
        resp = client.get("/api/v1/wanted/batch-probe/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "running" in data

    def test_returns_in_progress_state(self, app_client):
        _, client = app_client
        with _batch_probe_lock:
            _batch_probe_state.update(
                {"running": True, "total": 5, "processed": 2, "found": 1, "extracted": 1}
            )
        try:
            resp = client.get("/api/v1/wanted/batch-probe/status")
            data = resp.get_json()
            assert data["running"] is True
            assert data["total"] == 5
        finally:
            with _batch_probe_lock:
                _batch_probe_state["running"] = False


# ===========================================================================
# _remove_stream_from_container helper
# ===========================================================================


class TestRemoveStreamFromContainer:
    """Unit tests for the _remove_stream_from_container helper."""

    def test_missing_stream_index(self):
        """Logs a warning and returns when stream_index is None."""
        from routes.wanted.extract import _remove_stream_from_container

        # Should not raise
        _remove_stream_from_container("/fake/video.mkv", {})

    def test_successful_removal(self):
        from routes.wanted.extract import _remove_stream_from_container

        stream_info = {"stream_index": 3, "sub_index": 1}
        with (
            patch(P_GET_SETTINGS) as mock_settings,
            patch(P_REMOVE_STREAM, return_value="/backup/path") as mock_remove,
        ):
            mock_settings.return_value = MagicMock(
                remux_use_reflink=True, remux_trash_dir=".sublarr"
            )
            _remove_stream_from_container("/fake/video.mkv", stream_info)

        mock_remove.assert_called_once_with(
            video_path="/fake/video.mkv",
            stream_index=3,
            subtitle_track_index=1,
            use_reflink=True,
            trash_dir=".sublarr",
        )

    def test_remux_error_handled(self):
        from remux import RemuxError
        from routes.wanted.extract import _remove_stream_from_container

        stream_info = {"stream_index": 3, "sub_index": 0}
        with (
            patch(P_GET_SETTINGS) as mock_settings,
            patch(P_REMOVE_STREAM, side_effect=RemuxError("ffmpeg fail")),
        ):
            mock_settings.return_value = MagicMock(
                remux_use_reflink=True, remux_trash_dir=".sublarr"
            )
            # Should not raise
            _remove_stream_from_container("/fake/video.mkv", stream_info)

    def test_unexpected_error_handled(self):
        from routes.wanted.extract import _remove_stream_from_container

        stream_info = {"stream_index": 3, "sub_index": 0}
        with (
            patch(P_GET_SETTINGS) as mock_settings,
            patch(P_REMOVE_STREAM, side_effect=OSError("disk fail")),
        ):
            mock_settings.return_value = MagicMock(
                remux_use_reflink=True, remux_trash_dir=".sublarr"
            )
            # Should not raise
            _remove_stream_from_container("/fake/video.mkv", stream_info)

    def test_default_sub_index(self):
        """sub_index defaults to 0 when missing from stream_info."""
        from routes.wanted.extract import _remove_stream_from_container

        stream_info = {"stream_index": 5}  # no sub_index key
        with (
            patch(P_GET_SETTINGS) as mock_settings,
            patch(P_REMOVE_STREAM, return_value="/bak") as mock_remove,
        ):
            mock_settings.return_value = MagicMock(
                remux_use_reflink=True, remux_trash_dir=".sublarr"
            )
            _remove_stream_from_container("/fake/video.mkv", stream_info)

        assert mock_remove.call_args[1]["subtitle_track_index"] == 0


# ===========================================================================
# _extract_embedded_sub helper (standalone, outside request context)
# ===========================================================================


class TestExtractEmbeddedSubHelper:
    """Unit tests for the _extract_embedded_sub standalone helper."""

    def test_item_not_found_raises(self, app_client):
        app, _ = app_client
        from routes.wanted.extract import _extract_embedded_sub

        with (
            app.app_context(),
            patch(P_GET_WANTED_ITEM, return_value=None),
            pytest.raises(ValueError, match="not found"),
        ):
            _extract_embedded_sub(999, "/fake/file.mkv")

    def test_file_not_found_raises(self, app_client):
        app, _ = app_client
        from routes.wanted.extract import _extract_embedded_sub

        with (
            app.app_context(),
            patch(P_GET_WANTED_ITEM, return_value={"id": 1, "target_language": "de"}),
            pytest.raises(FileNotFoundError),
        ):
            _extract_embedded_sub(1, "/nonexistent/file.mkv")

    def test_non_video_raises(self, app_client, tmp_path):
        app, _ = app_client
        from routes.wanted.extract import _extract_embedded_sub

        txt = tmp_path / "notes.txt"
        txt.write_text("hi")

        with (
            app.app_context(),
            patch(P_GET_WANTED_ITEM, return_value={"id": 1, "target_language": "de"}),
            pytest.raises(ValueError, match="not a video container"),
        ):
            _extract_embedded_sub(1, str(txt))

    def test_no_subtitle_stream_raises(self, app_client, tmp_path):
        app, _ = app_client
        from routes.wanted.extract import _extract_embedded_sub

        mkv = tmp_path / "video.mkv"
        mkv.write_bytes(b"\x1a\x45\xdf\xa3")

        with (
            app.app_context(),
            patch(P_GET_WANTED_ITEM, return_value={"id": 1, "target_language": "de"}),
            patch(P_GET_MEDIA, return_value={"streams": []}),
            patch(P_SELECT_BEST, return_value=None),
            pytest.raises(LookupError, match="No suitable subtitle"),
        ):
            _extract_embedded_sub(1, str(mkv))

    def test_successful_extraction(self, app_client, tmp_path):
        app, _ = app_client
        from routes.wanted.extract import _extract_embedded_sub

        mkv = tmp_path / "video.mkv"
        mkv.write_bytes(b"\x1a\x45\xdf\xa3")

        stream_info = {"sub_index": 0, "stream_index": 2, "format": "ass", "language": "eng"}

        with (
            app.app_context(),
            patch(P_GET_WANTED_ITEM, return_value={"id": 1, "target_language": "de"}),
            patch(P_GET_MEDIA, return_value={"streams": []}),
            patch(P_SELECT_BEST, return_value=stream_info),
            patch(P_OUTPUT_FOR_LANG, return_value="/out/video.de.ass"),
            patch(P_EXTRACT_STREAM),
            patch(P_REMOVE_STREAM, return_value="/bak"),
            patch(P_UPDATE_EXISTING_SUB),
            patch(P_UPDATE_STATUS),
            patch(P_EMIT_EVENT),
            patch(P_LOG_ACTIVITY),
        ):
            result = _extract_embedded_sub(1, str(mkv))

        assert result["status"] == "extracted"
        assert result["format"] == "ass"
        assert result["output_path"] == "/out/video.de.ass"

    def test_auto_translate_srt(self, app_client, tmp_path):
        """auto_translate=True starts a background translation thread for SRT."""
        app, _ = app_client
        from routes.wanted.extract import _extract_embedded_sub

        mkv = tmp_path / "video.mkv"
        mkv.write_bytes(b"\x1a\x45\xdf\xa3")

        stream_info = {"sub_index": 0, "stream_index": 2, "format": "srt", "language": "eng"}

        with (
            app.app_context(),
            patch(P_GET_WANTED_ITEM, return_value={"id": 1, "target_language": "de"}),
            patch(P_GET_MEDIA, return_value={"streams": []}),
            patch(P_SELECT_BEST, return_value=stream_info),
            patch(P_OUTPUT_FOR_LANG, return_value="/out/video.de.srt"),
            patch(P_EXTRACT_STREAM),
            patch(P_REMOVE_STREAM, return_value="/bak"),
            patch(P_UPDATE_EXISTING_SUB),
            patch(P_UPDATE_STATUS),
            patch(P_EMIT_EVENT),
            patch(P_LOG_ACTIVITY),
            patch("threading.Thread") as mock_thread,
        ):
            mock_thread.return_value = MagicMock()
            result = _extract_embedded_sub(1, str(mkv), auto_translate=True)

        assert result["format"] == "srt"
        mock_thread.assert_called_once()
        mock_thread.return_value.start.assert_called_once()

    def test_auto_translate_not_triggered_for_ass(self, app_client, tmp_path):
        """auto_translate=True does NOT start translation for ASS format."""
        app, _ = app_client
        from routes.wanted.extract import _extract_embedded_sub

        mkv = tmp_path / "video.mkv"
        mkv.write_bytes(b"\x1a\x45\xdf\xa3")

        stream_info = {"sub_index": 0, "stream_index": 2, "format": "ass", "language": "eng"}

        with (
            app.app_context(),
            patch(P_GET_WANTED_ITEM, return_value={"id": 1, "target_language": "de"}),
            patch(P_GET_MEDIA, return_value={"streams": []}),
            patch(P_SELECT_BEST, return_value=stream_info),
            patch(P_OUTPUT_FOR_LANG, return_value="/out/video.de.ass"),
            patch(P_EXTRACT_STREAM),
            patch(P_REMOVE_STREAM, return_value="/bak"),
            patch(P_UPDATE_EXISTING_SUB),
            patch(P_UPDATE_STATUS),
            patch(P_EMIT_EVENT),
            patch(P_LOG_ACTIVITY),
            patch("threading.Thread") as mock_thread,
        ):
            _extract_embedded_sub(1, str(mkv), auto_translate=True)

        mock_thread.assert_not_called()

    def test_empty_file_path_raises(self, app_client):
        app, _ = app_client
        from routes.wanted.extract import _extract_embedded_sub

        with (
            app.app_context(),
            patch(P_GET_WANTED_ITEM, return_value={"id": 1, "target_language": "de"}),
            pytest.raises(FileNotFoundError),
        ):
            _extract_embedded_sub(1, "")


# ===========================================================================
# _run_batch_extract background thread
# ===========================================================================


class TestRunBatchExtract:
    """Unit tests for the _run_batch_extract background function."""

    def test_successful_run(self, app_client):
        app, _ = app_client
        from routes.wanted.batch_extract import _run_batch_extract

        with (
            patch(P_GET_WANTED_ITEM, return_value={"id": 1, "title": "Ep", "file_path": "/f.mkv"}),
            patch("routes.wanted.extract._extract_embedded_sub") as mock_extract,
            patch(P_SOCKETIO_BE),
            patch(P_EMIT_EVENT_BE),
        ):
            _run_batch_extract([1], False, app)

        mock_extract.assert_called_once_with(1, "/f.mkv", False)
        with _batch_extract_lock:
            assert _batch_extract_state["running"] is False
            assert _batch_extract_state["succeeded"] == 1
            assert _batch_extract_state["failed"] == 0

    def test_lookup_error_clears_embedded_flag(self, app_client):
        app, _ = app_client
        from routes.wanted.batch_extract import _run_batch_extract

        with (
            patch(P_GET_WANTED_ITEM, return_value={"id": 1, "title": "Ep", "file_path": "/f.mkv"}),
            patch(
                "routes.wanted.extract._extract_embedded_sub", side_effect=LookupError("no stream")
            ),
            patch(P_UPDATE_EXISTING_SUB) as mock_clear,
            patch(P_UPDATE_STATUS) as mock_status,
            patch(P_SOCKETIO_BE),
            patch(P_EMIT_EVENT_BE),
        ):
            _run_batch_extract([1], False, app)

        mock_clear.assert_called_once_with(1, "")
        mock_status.assert_called_once_with(1, "wanted")
        with _batch_extract_lock:
            assert _batch_extract_state["failed"] == 1

    def test_file_not_found_clears_embedded_flag(self, app_client):
        app, _ = app_client
        from routes.wanted.batch_extract import _run_batch_extract

        with (
            patch(P_GET_WANTED_ITEM, return_value={"id": 1, "title": "Ep", "file_path": ""}),
            patch(
                "routes.wanted.extract._extract_embedded_sub", side_effect=FileNotFoundError("gone")
            ),
            patch(P_UPDATE_EXISTING_SUB) as mock_clear,
            patch(P_UPDATE_STATUS) as mock_status,
            patch(P_SOCKETIO_BE),
            patch(P_EMIT_EVENT_BE),
        ):
            _run_batch_extract([1], False, app)

        mock_clear.assert_called_once_with(1, "")
        mock_status.assert_called_once_with(1, "wanted")

    def test_unexpected_error_increments_failed(self, app_client):
        app, _ = app_client
        from routes.wanted.batch_extract import _run_batch_extract

        with (
            patch(P_GET_WANTED_ITEM, return_value={"id": 1, "title": "Ep", "file_path": "/f.mkv"}),
            patch("routes.wanted.extract._extract_embedded_sub", side_effect=RuntimeError("boom")),
            patch(P_SOCKETIO_BE),
            patch(P_EMIT_EVENT_BE),
        ):
            _run_batch_extract([1], False, app)

        with _batch_extract_lock:
            assert _batch_extract_state["failed"] == 1
            assert _batch_extract_state["succeeded"] == 0

    def test_multiple_items_mixed_results(self, app_client):
        app, _ = app_client
        from routes.wanted.batch_extract import _run_batch_extract

        items = {
            1: {"id": 1, "title": "OK", "file_path": "/ok.mkv"},
            2: {"id": 2, "title": "Fail", "file_path": "/fail.mkv"},
            3: {"id": 3, "title": "Also OK", "file_path": "/also.mkv"},
        }

        def fake_extract(item_id, fp, auto):
            if item_id == 2:
                raise LookupError("no stream")

        with (
            patch(P_GET_WANTED_ITEM, side_effect=lambda iid: items.get(iid)),
            patch("routes.wanted.extract._extract_embedded_sub", side_effect=fake_extract),
            patch(P_UPDATE_EXISTING_SUB),
            patch(P_UPDATE_STATUS),
            patch(P_SOCKETIO_BE),
            patch(P_EMIT_EVENT_BE),
        ):
            _run_batch_extract([1, 2, 3], False, app)

        with _batch_extract_lock:
            assert _batch_extract_state["total"] == 3
            assert _batch_extract_state["processed"] == 3
            assert _batch_extract_state["succeeded"] == 2
            assert _batch_extract_state["failed"] == 1

    def test_emits_progress_and_completion(self, app_client):
        app, _ = app_client
        from routes.wanted.batch_extract import _run_batch_extract

        with (
            patch(P_GET_WANTED_ITEM, return_value={"id": 1, "title": "Ep", "file_path": "/f.mkv"}),
            patch("routes.wanted.extract._extract_embedded_sub"),
            patch(P_SOCKETIO_BE) as mock_sio,
            patch(P_EMIT_EVENT_BE) as mock_emit,
        ):
            _run_batch_extract([1], False, app)

        # Progress event via socketio
        mock_sio.emit.assert_called()
        assert mock_sio.emit.call_args_list[0][0][0] == "batch_extract_progress"
        # Completion event via emit_event
        mock_emit.assert_called_once()
        assert mock_emit.call_args[0][0] == "batch_extract_completed"

    def test_db_update_failure_on_clear(self, app_client):
        """DB failure when clearing embedded flag is silently logged."""
        app, _ = app_client
        from routes.wanted.batch_extract import _run_batch_extract

        with (
            patch(P_GET_WANTED_ITEM, return_value={"id": 1, "title": "Ep", "file_path": "/f.mkv"}),
            patch(
                "routes.wanted.extract._extract_embedded_sub", side_effect=LookupError("no stream")
            ),
            patch(P_UPDATE_EXISTING_SUB, side_effect=Exception("db down")),
            patch(P_UPDATE_STATUS),
            patch(P_SOCKETIO_BE),
            patch(P_EMIT_EVENT_BE),
        ):
            # Should not raise despite DB failure
            _run_batch_extract([1], False, app)

        with _batch_extract_lock:
            assert _batch_extract_state["failed"] == 1


# ===========================================================================
# _run_batch_probe background thread
# ===========================================================================


class TestRunBatchProbe:
    """Unit tests for the _run_batch_probe background function."""

    def test_target_language_audio_skipped(self, app_client):
        app, _ = app_client
        from routes.wanted.batch_probe import _run_batch_probe

        items = [{"id": 1, "file_path": "/f.mkv", "title": "Ep", "target_language": "de"}]
        probe_data = {"streams": []}

        with (
            patch(P_GET_MEDIA, return_value=probe_data),
            patch(P_HAS_TARGET_AUDIO, return_value=True),
            patch(P_GET_SETTINGS) as mock_s,
            patch(P_SOCKETIO_BP),
            patch(P_EMIT_EVENT_BP),
        ):
            mock_s.return_value = MagicMock(scan_metadata_max_workers=1)
            _run_batch_probe(items, app)

        with _batch_probe_lock:
            assert _batch_probe_state["skipped"] == 1
            assert _batch_probe_state["processed"] == 1

    def test_no_text_subs_skipped(self, app_client):
        app, _ = app_client
        from routes.wanted.batch_probe import _run_batch_probe

        items = [{"id": 1, "file_path": "/f.mkv", "title": "Ep", "target_language": "de"}]
        # Only PGS subtitle (not text-based)
        probe_data = {
            "streams": [{"codec_type": "subtitle", "codec_name": "hdmv_pgs_subtitle", "index": 2}]
        }

        with (
            patch(P_GET_MEDIA, return_value=probe_data),
            patch(P_HAS_TARGET_AUDIO, return_value=False),
            patch(P_GET_SETTINGS) as mock_s,
            patch(P_SOCKETIO_BP),
            patch(P_EMIT_EVENT_BP),
        ):
            mock_s.return_value = MagicMock(scan_metadata_max_workers=1)
            _run_batch_probe(items, app)

        with _batch_probe_lock:
            assert _batch_probe_state["skipped"] == 1

    def test_successful_extraction_with_target_lang_ass(self, app_client, tmp_path):
        app, _ = app_client
        from routes.wanted.batch_probe import _run_batch_probe

        target_ass = tmp_path / "video.de.ass"

        items = [{"id": 1, "file_path": "/f.mkv", "title": "Ep", "target_language": "de"}]
        probe_data = {
            "streams": [
                {
                    "codec_type": "subtitle",
                    "codec_name": "ass",
                    "index": 2,
                    "tags": {"language": "eng"},
                }
            ]
        }

        def fake_output_path(fp, fmt, lang):
            if fmt == "ass":
                return str(target_ass)
            return str(tmp_path / "video.de.srt")

        with (
            patch(P_GET_MEDIA, return_value=probe_data),
            patch(P_HAS_TARGET_AUDIO, return_value=False),
            patch(P_GET_SETTINGS) as mock_s,
            patch(P_EXTRACT_STREAM) as mock_ext,
            patch(P_GET_SUB_OUT_PATH, return_value=str(tmp_path / "out.ass")),
            patch(P_OUTPUT_FOR_LANG, side_effect=fake_output_path),
            patch(P_UPDATE_EXISTING_SUB) as mock_update,
            patch(P_REMOVE_STREAMS_BP),
            patch(P_SOCKETIO_BP),
            patch(P_EMIT_EVENT_BP),
        ):
            mock_s.return_value = MagicMock(
                scan_metadata_max_workers=1, remux_use_reflink=True, remux_trash_dir=".sublarr"
            )
            # Simulate extraction creating the target-lang file
            mock_ext.side_effect = lambda fp, si, out: target_ass.write_text("[Script Info]")
            _run_batch_probe(items, app)

        mock_update.assert_called_once_with(1, "ass")
        with _batch_probe_lock:
            assert _batch_probe_state["found"] == 1

    def test_successful_extraction_with_target_lang_srt(self, app_client, tmp_path):
        app, _ = app_client
        from routes.wanted.batch_probe import _run_batch_probe

        target_srt = tmp_path / "video.de.srt"

        items = [{"id": 1, "file_path": "/f.mkv", "title": "Ep", "target_language": "de"}]
        probe_data = {
            "streams": [
                {
                    "codec_type": "subtitle",
                    "codec_name": "subrip",
                    "index": 2,
                    "tags": {"language": "eng"},
                }
            ]
        }

        def fake_output_path(fp, fmt, lang):
            if fmt == "srt":
                return str(target_srt)
            return str(tmp_path / "video.de.ass")

        with (
            patch(P_GET_MEDIA, return_value=probe_data),
            patch(P_HAS_TARGET_AUDIO, return_value=False),
            patch(P_GET_SETTINGS) as mock_s,
            patch(P_EXTRACT_STREAM) as mock_ext,
            patch(P_GET_SUB_OUT_PATH, return_value=str(tmp_path / "out.srt")),
            patch(P_OUTPUT_FOR_LANG, side_effect=fake_output_path),
            patch(P_UPDATE_EXISTING_SUB) as mock_update,
            patch(P_REMOVE_STREAMS_BP),
            patch(P_SOCKETIO_BP),
            patch(P_EMIT_EVENT_BP),
        ):
            mock_s.return_value = MagicMock(
                scan_metadata_max_workers=1, remux_use_reflink=True, remux_trash_dir=".sublarr"
            )
            mock_ext.side_effect = lambda fp, si, out: target_srt.write_text("1\n00:00:01\nHi\n")
            _run_batch_probe(items, app)

        mock_update.assert_called_once_with(1, "srt")
        with _batch_probe_lock:
            assert _batch_probe_state["found"] == 1

    def test_extraction_failure_skips(self, app_client, tmp_path):
        """When extraction of all streams fails, item is counted as skipped."""
        app, _ = app_client
        from routes.wanted.batch_probe import _run_batch_probe

        items = [{"id": 1, "file_path": "/f.mkv", "title": "Ep", "target_language": "de"}]
        probe_data = {
            "streams": [
                {
                    "codec_type": "subtitle",
                    "codec_name": "ass",
                    "index": 2,
                    "tags": {"language": "eng"},
                }
            ]
        }

        with (
            patch(P_GET_MEDIA, return_value=probe_data),
            patch(P_HAS_TARGET_AUDIO, return_value=False),
            patch(P_GET_SETTINGS) as mock_s,
            patch(P_EXTRACT_STREAM, side_effect=RuntimeError("ffmpeg fail")),
            patch(P_GET_SUB_OUT_PATH, return_value=str(tmp_path / "out.ass")),
            patch(P_OUTPUT_FOR_LANG, return_value=str(tmp_path / "fake.ass")),
            patch(P_SOCKETIO_BP),
            patch(P_EMIT_EVENT_BP),
        ):
            mock_s.return_value = MagicMock(scan_metadata_max_workers=1)
            _run_batch_probe(items, app)

        with _batch_probe_lock:
            assert _batch_probe_state["skipped"] == 1

    def test_probe_failure_increments_failed(self, app_client):
        app, _ = app_client
        from routes.wanted.batch_probe import _run_batch_probe

        items = [{"id": 1, "file_path": "/f.mkv", "title": "Ep", "target_language": "de"}]

        with (
            patch(P_GET_MEDIA, side_effect=RuntimeError("ffprobe died")),
            patch(P_GET_SETTINGS) as mock_s,
            patch(P_SOCKETIO_BP),
            patch(P_EMIT_EVENT_BP),
        ):
            mock_s.return_value = MagicMock(scan_metadata_max_workers=1)
            _run_batch_probe(items, app)

        with _batch_probe_lock:
            assert _batch_probe_state["failed"] == 1

    def test_ffprobe_returns_none(self, app_client):
        """When ffprobe returns None, should count as failed."""
        app, _ = app_client
        from routes.wanted.batch_probe import _run_batch_probe

        items = [{"id": 1, "file_path": "/f.mkv", "title": "Ep", "target_language": "de"}]

        with (
            patch(P_GET_MEDIA, return_value=None),
            patch(P_GET_SETTINGS) as mock_s,
            patch(P_SOCKETIO_BP),
            patch(P_EMIT_EVENT_BP),
        ):
            mock_s.return_value = MagicMock(scan_metadata_max_workers=1)
            _run_batch_probe(items, app)

        with _batch_probe_lock:
            assert _batch_probe_state["failed"] == 1

    def test_existing_output_file_skips_extraction(self, app_client, tmp_path):
        """When output file already exists, extraction is skipped but stream is scheduled for removal."""
        app, _ = app_client
        from routes.wanted.batch_probe import _run_batch_probe

        existing_file = tmp_path / "out.ass"
        existing_file.write_text("[Script Info]")

        items = [{"id": 1, "file_path": "/f.mkv", "title": "Ep", "target_language": "de"}]
        probe_data = {
            "streams": [
                {
                    "codec_type": "subtitle",
                    "codec_name": "ass",
                    "index": 2,
                    "tags": {"language": "eng"},
                }
            ]
        }

        def fake_output_path(fp, fmt, lang):
            return str(tmp_path / "video.de.ass")

        with (
            patch(P_GET_MEDIA, return_value=probe_data),
            patch(P_HAS_TARGET_AUDIO, return_value=False),
            patch(P_GET_SETTINGS) as mock_s,
            patch(P_EXTRACT_STREAM) as mock_ext,
            patch(P_GET_SUB_OUT_PATH, return_value=str(existing_file)),
            patch(P_OUTPUT_FOR_LANG, side_effect=fake_output_path),
            patch(P_UPDATE_EXISTING_SUB),
            patch(P_REMOVE_STREAMS_BP) as mock_remux,
            patch(P_SOCKETIO_BP),
            patch(P_EMIT_EVENT_BP),
        ):
            mock_s.return_value = MagicMock(
                scan_metadata_max_workers=1, remux_use_reflink=True, remux_trash_dir=".sublarr"
            )
            _run_batch_probe(items, app)

        # Extraction should NOT have been called (file already exists)
        mock_ext.assert_not_called()
        # But remux should still be called to remove the stream from the container
        mock_remux.assert_called_once()

    def test_emits_completion_event_with_duration(self, app_client):
        app, _ = app_client
        from routes.wanted.batch_probe import _run_batch_probe

        items = [{"id": 1, "file_path": "/f.mkv", "title": "Ep", "target_language": "de"}]

        with (
            patch(P_GET_MEDIA, return_value=None),
            patch(P_GET_SETTINGS) as mock_s,
            patch(P_SOCKETIO_BP),
            patch(P_EMIT_EVENT_BP) as mock_emit,
        ):
            mock_s.return_value = MagicMock(scan_metadata_max_workers=1)
            _run_batch_probe(items, app)

        mock_emit.assert_called_once()
        event_name, event_data = mock_emit.call_args[0]
        assert event_name == "batch_probe_completed"
        assert "duration_ms" in event_data

    def test_remux_failure_continues(self, app_client, tmp_path):
        """Container removal failure does not abort the batch."""
        app, _ = app_client
        from remux import RemuxError
        from routes.wanted.batch_probe import _run_batch_probe

        target_ass = tmp_path / "video.de.ass"

        items = [{"id": 1, "file_path": "/f.mkv", "title": "Ep", "target_language": "de"}]
        probe_data = {
            "streams": [
                {
                    "codec_type": "subtitle",
                    "codec_name": "ass",
                    "index": 2,
                    "tags": {"language": "eng"},
                }
            ]
        }

        def fake_output_path(fp, fmt, lang):
            if fmt == "ass":
                return str(target_ass)
            return str(tmp_path / "video.de.srt")

        with (
            patch(P_GET_MEDIA, return_value=probe_data),
            patch(P_HAS_TARGET_AUDIO, return_value=False),
            patch(P_GET_SETTINGS) as mock_s,
            patch(P_EXTRACT_STREAM) as mock_ext,
            patch(P_GET_SUB_OUT_PATH, return_value=str(tmp_path / "out.ass")),
            patch(P_OUTPUT_FOR_LANG, side_effect=fake_output_path),
            patch(P_UPDATE_EXISTING_SUB),
            patch(P_REMOVE_STREAMS_BP, side_effect=RemuxError("mux fail")),
            patch(P_SOCKETIO_BP),
            patch(P_EMIT_EVENT_BP),
        ):
            mock_s.return_value = MagicMock(
                scan_metadata_max_workers=1, remux_use_reflink=True, remux_trash_dir=".sublarr"
            )
            mock_ext.side_effect = lambda fp, si, out: target_ass.write_text("[Script Info]")
            # Should not raise
            _run_batch_probe(items, app)

        with _batch_probe_lock:
            assert _batch_probe_state["found"] == 1

    def test_source_lang_extracted_counts_as_extracted(self, app_client, tmp_path):
        """When subs are extracted but NOT target-lang, counts as 'extracted' (needs translation)."""
        app, _ = app_client
        from routes.wanted.batch_probe import _run_batch_probe

        items = [{"id": 1, "file_path": "/f.mkv", "title": "Ep", "target_language": "de"}]
        probe_data = {
            "streams": [
                {
                    "codec_type": "subtitle",
                    "codec_name": "ass",
                    "index": 2,
                    "tags": {"language": "eng"},
                }
            ]
        }

        with (
            patch(P_GET_MEDIA, return_value=probe_data),
            patch(P_HAS_TARGET_AUDIO, return_value=False),
            patch(P_GET_SETTINGS) as mock_s,
            patch(P_EXTRACT_STREAM),
            patch(P_GET_SUB_OUT_PATH, return_value=str(tmp_path / "out.ass")),
            patch(P_OUTPUT_FOR_LANG, return_value=str(tmp_path / "nonexistent.ass")),
            patch(P_REMOVE_STREAMS_BP),
            patch(P_SOCKETIO_BP),
            patch(P_EMIT_EVENT_BP),
        ):
            mock_s.return_value = MagicMock(
                scan_metadata_max_workers=1, remux_use_reflink=True, remux_trash_dir=".sublarr"
            )
            _run_batch_probe(items, app)

        with _batch_probe_lock:
            assert _batch_probe_state["extracted"] == 1
            assert _batch_probe_state["found"] == 0
