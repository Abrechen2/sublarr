"""Tests for routes/subtitle_processor.py -- process, undo, bak-exists, interjections, batch."""

import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_TEMP_DIR = os.path.realpath(tempfile.gettempdir())


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client(temp_db):
    from app import create_app

    app = create_app(testing=True)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def reset_batch_state():
    """Reset the module-level _batch_running flag between tests."""
    import routes.subtitle_processor as sp_mod

    sp_mod._batch_running = False
    yield
    sp_mod._batch_running = False


def _make_subtitle(tmp_path, name="test.srt", content="1\n00:00:01,000 --> 00:00:03,000\nHello\n"):
    """Create a subtitle file inside tmp_path and return its absolute path."""
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return str(p)


# ---------------------------------------------------------------------------
# TestProcessSubtitle — POST /api/v1/tools/process
# ---------------------------------------------------------------------------


class TestProcessSubtitle:
    def test_400_when_path_missing(self, client):
        resp = client.post("/api/v1/tools/process", json={"mods": []})
        assert resp.status_code == 400
        assert "path" in resp.get_json()["error"].lower()

    def test_403_when_path_outside_media(self, client):
        resp = client.post(
            "/api/v1/tools/process",
            json={"path": "/etc/passwd", "mods": []},
        )
        assert resp.status_code == 403

    def test_404_when_file_not_found(self, client):
        nonexistent = os.path.join(_TEMP_DIR, "nonexistent_sub.srt")
        resp = client.post(
            "/api/v1/tools/process",
            json={"path": nonexistent, "mods": []},
        )
        assert resp.status_code == 404

    def test_400_for_unsupported_extension(self, client, tmp_path):
        txt_file = tmp_path / "subtitle.txt"
        txt_file.write_text("not a subtitle")
        resp = client.post(
            "/api/v1/tools/process",
            json={"path": str(txt_file), "mods": []},
        )
        assert resp.status_code == 400
        assert "supported" in resp.get_json()["error"].lower()

    def test_400_invalid_mod_config(self, client, tmp_path):
        srt = _make_subtitle(tmp_path)
        resp = client.post(
            "/api/v1/tools/process",
            json={"path": srt, "mods": [{"mod": "nonexistent_mod"}]},
        )
        assert resp.status_code == 400
        assert "mod" in resp.get_json()["error"].lower()

    def test_200_dry_run_success(self, client, tmp_path):
        srt = _make_subtitle(tmp_path)
        mock_result = MagicMock()
        mock_result.changes = []
        mock_result.backed_up = False
        mock_result.output_path = srt
        mock_result.dry_run = True

        with patch("subtitle_processor.apply_mods", return_value=mock_result):
            resp = client.post(
                "/api/v1/tools/process",
                json={"path": srt, "mods": [], "dry_run": True},
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["dry_run"] is True
        assert data["changes"] == []

    def test_200_with_changes(self, client, tmp_path):
        srt = _make_subtitle(tmp_path)

        mock_change = MagicMock()
        mock_change.event_index = 0
        mock_change.timestamp = "00:00:01,000"
        mock_change.original_text = "Hello"
        mock_change.modified_text = "Hi"
        mock_change.mod_name = "common_fixes"

        mock_result = MagicMock()
        mock_result.changes = [mock_change]
        mock_result.backed_up = True
        mock_result.output_path = srt
        mock_result.dry_run = False

        with patch("subtitle_processor.apply_mods", return_value=mock_result):
            resp = client.post(
                "/api/v1/tools/process",
                json={"path": srt, "mods": []},
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["changes"]) == 1
        assert data["backed_up"] is True

    def test_500_on_unexpected_error(self, client, tmp_path):
        srt = _make_subtitle(tmp_path)
        with patch("subtitle_processor.apply_mods", side_effect=RuntimeError("boom")):
            resp = client.post(
                "/api/v1/tools/process",
                json={"path": srt, "mods": []},
            )
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# TestUndoProcess — POST /api/v1/tools/process/undo
# ---------------------------------------------------------------------------


class TestUndoProcess:
    def test_400_when_path_missing(self, client):
        resp = client.post("/api/v1/tools/process/undo", json={})
        assert resp.status_code == 400

    def test_404_when_no_backup(self, client, tmp_path):
        srt = _make_subtitle(tmp_path)
        resp = client.post(
            "/api/v1/tools/process/undo",
            json={"path": srt},
        )
        assert resp.status_code == 404
        assert "backup" in resp.get_json()["error"].lower()

    def test_200_restores_from_backup(self, client, tmp_path):
        srt = _make_subtitle(tmp_path, "test.srt", "Modified content\n")
        # Create the .bak file
        bak_path = str(tmp_path / "test.bak.srt")
        with open(bak_path, "w") as f:
            f.write("Original content\n")

        resp = client.post(
            "/api/v1/tools/process/undo",
            json={"path": srt},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "restored"
        # The bak file should have been moved
        assert not os.path.exists(bak_path)
        # The srt file should have original content
        with open(srt) as f:
            assert f.read() == "Original content\n"


# ---------------------------------------------------------------------------
# TestBakExists — GET /api/v1/tools/process/bak-exists
# ---------------------------------------------------------------------------


class TestBakExists:
    def test_400_when_path_missing(self, client):
        resp = client.get("/api/v1/tools/process/bak-exists")
        assert resp.status_code == 400

    def test_false_when_no_backup(self, client, tmp_path):
        srt = _make_subtitle(tmp_path)
        resp = client.get(f"/api/v1/tools/process/bak-exists?path={srt}")
        assert resp.status_code == 200
        assert resp.get_json()["exists"] is False

    def test_true_when_backup_exists(self, client, tmp_path):
        srt = _make_subtitle(tmp_path, "test.srt")
        bak_path = str(tmp_path / "test.bak.srt")
        with open(bak_path, "w") as f:
            f.write("backup")
        resp = client.get(f"/api/v1/tools/process/bak-exists?path={srt}")
        assert resp.status_code == 200
        assert resp.get_json()["exists"] is True


# ---------------------------------------------------------------------------
# TestGetInterjections — GET /api/v1/tools/process/interjections
# ---------------------------------------------------------------------------


class TestGetInterjections:
    def test_returns_custom_list(self, client):
        mock_settings = MagicMock(hi_interjections_list="Ah\nOh\nHmm")
        with patch("routes.subtitle_processor.get_settings", return_value=mock_settings):
            resp = client.get("/api/v1/tools/process/interjections")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["is_custom"] is True
        assert "Ah" in data["items"]
        assert "Oh" in data["items"]

    def test_returns_default_when_no_custom(self, client):
        """When hi_interjections_list is empty, falls back to data file or empty list."""
        mock_settings = MagicMock(hi_interjections_list="")
        with patch("routes.subtitle_processor.get_settings", return_value=mock_settings):
            resp = client.get("/api/v1/tools/process/interjections")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["is_custom"] is False
        assert isinstance(data["items"], list)


# ---------------------------------------------------------------------------
# TestPutInterjections — PUT /api/v1/tools/process/interjections
# ---------------------------------------------------------------------------


class TestPutInterjections:
    def test_400_when_items_not_array(self, client):
        resp = client.put(
            "/api/v1/tools/process/interjections",
            json={"items": "not-an-array"},
        )
        assert resp.status_code == 400

    def test_200_saves_items(self, client):
        with (
            patch("db.config.save_config_entry") as mock_save,
            patch("db.config.get_all_config_entries", return_value={}),
            patch("config.reload_settings"),
        ):
            resp = client.put(
                "/api/v1/tools/process/interjections",
                json={"items": ["Ah", "Oh", "Hmm"]},
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["count"] == 3
        mock_save.assert_called_once()

    def test_200_empty_items_resets(self, client):
        with (
            patch("db.config.save_config_entry") as mock_save,
            patch("db.config.get_all_config_entries", return_value={}),
            patch("config.reload_settings"),
        ):
            resp = client.put(
                "/api/v1/tools/process/interjections",
                json={"items": []},
            )
        assert resp.status_code == 200
        assert resp.get_json()["count"] == 0


# ---------------------------------------------------------------------------
# TestProcessSeries — POST /api/v1/library/series/<id>/process
# ---------------------------------------------------------------------------


class TestProcessSeries:
    def test_202_starts_background_processing(self, client):
        with patch("routes.subtitle_processor._batch_process_series"):
            resp = client.post("/api/v1/library/series/1/process")
        assert resp.status_code == 202
        data = resp.get_json()
        assert data["status"] == "started"
        assert data["series_id"] == 1

    def test_409_when_batch_already_running(self, client):
        import routes.subtitle_processor as sp_mod

        sp_mod._batch_running = True
        resp = client.post("/api/v1/library/series/1/process")
        assert resp.status_code == 409
        assert "already running" in resp.get_json()["error"].lower()


# ---------------------------------------------------------------------------
# TestProcessAll — POST /api/v1/library/process-all
# ---------------------------------------------------------------------------


class TestProcessAll:
    def test_202_starts_with_default_filter(self, client):
        with patch("routes.subtitle_processor._batch_process_library"):
            resp = client.post("/api/v1/library/process-all", json={})
        assert resp.status_code == 202
        data = resp.get_json()
        assert data["status"] == "started"
        assert data["filter"] == "all"

    def test_202_with_unprocessed_filter(self, client):
        with patch("routes.subtitle_processor._batch_process_library"):
            resp = client.post(
                "/api/v1/library/process-all",
                json={"filter": "unprocessed"},
            )
        assert resp.status_code == 202
        assert resp.get_json()["filter"] == "unprocessed"

    def test_400_invalid_filter(self, client):
        resp = client.post(
            "/api/v1/library/process-all",
            json={"filter": "invalid_mode"},
        )
        assert resp.status_code == 400
        assert "filter" in resp.get_json()["error"]

    def test_409_when_batch_already_running(self, client):
        import routes.subtitle_processor as sp_mod

        sp_mod._batch_running = True
        resp = client.post("/api/v1/library/process-all", json={})
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# TestUpdateSeriesProcessingConfig — PATCH /api/v1/library/series/<id>/processing-config
# ---------------------------------------------------------------------------


class TestUpdateSeriesProcessingConfig:
    def test_200_creates_new_config(self, client):
        mock_session = MagicMock()
        mock_session.get.return_value = None  # no existing row

        with patch("extensions.db") as mock_db:
            mock_db.session = mock_session
            resp = client.patch(
                "/api/v1/library/series/1/processing-config",
                json={"hi_removal": True, "common_fixes": False},
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert data["series_id"] == 1
        assert data["config"]["hi_removal"] is True

    def test_200_updates_existing_config(self, client):
        existing_row = MagicMock()
        existing_row.processing_config = '{"hi_removal": false}'

        mock_session = MagicMock()
        mock_session.get.return_value = existing_row

        with patch("extensions.db") as mock_db:
            mock_db.session = mock_session
            resp = client.patch(
                "/api/v1/library/series/1/processing-config",
                json={"hi_removal": True},
            )
        assert resp.status_code == 200

    def test_filters_to_allowed_keys_only(self, client):
        mock_session = MagicMock()
        mock_session.get.return_value = None

        with patch("extensions.db") as mock_db:
            mock_db.session = mock_session
            resp = client.patch(
                "/api/v1/library/series/1/processing-config",
                json={"hi_removal": True, "injected_key": "bad"},
            )
        assert resp.status_code == 200
        config = resp.get_json()["config"]
        assert "injected_key" not in config
        assert "hi_removal" in config
