"""HTTP tests for routes/subtitles.py — sidecar discovery, trash management, download."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helper: create a minimal subtitle file
# ---------------------------------------------------------------------------


def _make_sub(directory: str, name: str, content: str = "1\n00:00:01,000 --> 00:00:02,000\nHello\n") -> str:
    path = os.path.join(directory, name)
    Path(path).write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# scan_subtitle_sidecars unit tests (pure function)
# ---------------------------------------------------------------------------


def test_scan_subtitle_sidecars_empty_dir(temp_dir):
    from routes.subtitles import scan_subtitle_sidecars

    video = os.path.join(temp_dir, "episode.mkv")
    Path(video).touch()
    result = scan_subtitle_sidecars(video)
    assert result == []


def test_scan_subtitle_sidecars_finds_sidecar(temp_dir):
    from routes.subtitles import scan_subtitle_sidecars

    video = os.path.join(temp_dir, "episode.mkv")
    Path(video).touch()
    _make_sub(temp_dir, "episode.en.srt")

    result = scan_subtitle_sidecars(video)
    assert len(result) == 1
    assert result[0]["language"] == "en"
    assert result[0]["format"] == "srt"


def test_scan_subtitle_sidecars_multiple_langs(temp_dir):
    from routes.subtitles import scan_subtitle_sidecars

    video = os.path.join(temp_dir, "episode.mkv")
    Path(video).touch()
    _make_sub(temp_dir, "episode.de.ass")
    _make_sub(temp_dir, "episode.en.srt")

    result = scan_subtitle_sidecars(video)
    langs = {r["language"] for r in result}
    assert "de" in langs
    assert "en" in langs


def test_scan_subtitle_sidecars_excludes_video(temp_dir):
    from routes.subtitles import scan_subtitle_sidecars

    video = os.path.join(temp_dir, "episode.mkv")
    Path(video).touch()
    result = scan_subtitle_sidecars(video)
    # Video itself must not appear
    paths = [r["path"] for r in result]
    assert video not in paths


def test_scan_subtitle_sidecars_ignores_long_lang_code(temp_dir):
    from routes.subtitles import scan_subtitle_sidecars

    video = os.path.join(temp_dir, "episode.mkv")
    Path(video).touch()
    # lang code "toolongcode" has 11 chars — should be ignored
    _make_sub(temp_dir, "episode.toolongcode.srt")
    result = scan_subtitle_sidecars(video)
    assert result == []


def test_scan_subtitle_sidecars_nonexistent_video(temp_dir):
    from routes.subtitles import scan_subtitle_sidecars

    # Non-existent video path — should return empty without crashing
    result = scan_subtitle_sidecars(os.path.join(temp_dir, "missing.mkv"))
    assert result == []


# ---------------------------------------------------------------------------
# GET /api/v1/subtitles/download — path-based download
# ---------------------------------------------------------------------------


def test_download_subtitle_missing_param(client, temp_dir):
    resp = client.get("/api/v1/subtitles/download")
    assert resp.status_code == 400
    assert b"path" in resp.data


def test_download_subtitle_outside_media_path(client, temp_dir, monkeypatch):
    # media_path is temp_dir; request a path outside → 403
    import os

    outside = os.path.join(tempfile.gettempdir(), "evil.srt")
    # Point media_path to a subdirectory so the above is "outside"
    sub_dir = os.path.join(temp_dir, "media")
    os.makedirs(sub_dir, exist_ok=True)
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", sub_dir)

    from config import reload_settings
    reload_settings()

    resp = client.get(f"/api/v1/subtitles/download?path={outside}")
    assert resp.status_code == 403


def test_download_subtitle_wrong_extension(client, temp_dir, monkeypatch):
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", temp_dir)
    from config import reload_settings
    reload_settings()

    bad_file = os.path.join(temp_dir, "video.mkv")
    Path(bad_file).touch()
    resp = client.get(f"/api/v1/subtitles/download?path={bad_file}")
    assert resp.status_code == 403


def test_download_subtitle_file_not_found(client, temp_dir, monkeypatch):
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", temp_dir)
    from config import reload_settings
    reload_settings()

    missing = os.path.join(temp_dir, "missing.srt")
    resp = client.get(f"/api/v1/subtitles/download?path={missing}")
    assert resp.status_code == 404


def test_download_subtitle_success(client, temp_dir, monkeypatch):
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", temp_dir)
    from config import reload_settings
    reload_settings()

    sub_path = _make_sub(temp_dir, "show.en.srt")
    resp = client.get(f"/api/v1/subtitles/download?path={sub_path}")
    assert resp.status_code == 200
    assert b"Hello" in resp.data


# ---------------------------------------------------------------------------
# DELETE /api/v1/library/subtitles — soft-delete (trash)
# ---------------------------------------------------------------------------


def test_delete_subtitles_missing_paths(client):
    resp = client.delete("/api/v1/library/subtitles", json={})
    assert resp.status_code == 400


def test_delete_subtitles_empty_paths(client):
    resp = client.delete("/api/v1/library/subtitles", json={"paths": []})
    assert resp.status_code == 400


def test_delete_subtitles_invalid_path_type(client, temp_dir, monkeypatch):
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", temp_dir)
    from config import reload_settings
    reload_settings()

    resp = client.delete("/api/v1/library/subtitles", json={"paths": [42]})
    data = resp.get_json()
    assert resp.status_code == 200
    assert len(data["failed"]) == 1


def test_delete_subtitles_path_outside_media(client, temp_dir, monkeypatch):
    sub_dir = os.path.join(temp_dir, "media")
    os.makedirs(sub_dir, exist_ok=True)
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", sub_dir)
    from config import reload_settings
    reload_settings()

    outside = os.path.join(temp_dir, "outside.en.srt")
    Path(outside).write_text("dummy")
    resp = client.delete("/api/v1/library/subtitles", json={"paths": [outside]})
    data = resp.get_json()
    assert resp.status_code == 200
    assert len(data["failed"]) == 1
    assert "outside" in data["failed"][0]["error"].lower() or "Path" in data["failed"][0]["error"]


def test_delete_subtitles_file_not_found(client, temp_dir, monkeypatch):
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", temp_dir)
    from config import reload_settings
    reload_settings()

    missing = os.path.join(temp_dir, "nonexistent.en.srt")
    resp = client.delete("/api/v1/library/subtitles", json={"paths": [missing]})
    data = resp.get_json()
    assert resp.status_code == 200
    assert len(data["failed"]) == 1


def test_delete_subtitles_success(client, temp_dir, monkeypatch):
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", temp_dir)
    from config import reload_settings
    reload_settings()

    sub_path = _make_sub(temp_dir, "show.en.srt")
    resp = client.delete("/api/v1/library/subtitles", json={"paths": [sub_path]})
    data = resp.get_json()
    assert resp.status_code == 200
    assert sub_path in data["deleted"]
    assert len(data["failed"]) == 0
    assert "batch_id" in data
    # File should no longer exist at original location
    assert not os.path.exists(sub_path)


def test_delete_subtitles_wrong_extension(client, temp_dir, monkeypatch):
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", temp_dir)
    from config import reload_settings
    reload_settings()

    bad = os.path.join(temp_dir, "show.en.mkv")
    Path(bad).touch()
    resp = client.delete("/api/v1/library/subtitles", json={"paths": [bad]})
    data = resp.get_json()
    assert resp.status_code == 200
    assert len(data["failed"]) == 1


# ---------------------------------------------------------------------------
# GET /api/v1/library/trash
# ---------------------------------------------------------------------------


def test_list_trash_empty(client, temp_dir, monkeypatch):
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", temp_dir)
    from config import reload_settings
    reload_settings()

    resp = client.get("/api/v1/library/trash")
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["batches"] == []


def test_list_trash_after_delete(client, temp_dir, monkeypatch):
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", temp_dir)
    from config import reload_settings
    reload_settings()

    sub_path = _make_sub(temp_dir, "show.de.srt")
    client.delete("/api/v1/library/subtitles", json={"paths": [sub_path]})

    resp = client.get("/api/v1/library/trash")
    data = resp.get_json()
    assert resp.status_code == 200
    assert len(data["batches"]) == 1
    batch = data["batches"][0]
    assert "batch_id" in batch
    assert batch["file_count"] == 1


# ---------------------------------------------------------------------------
# POST /api/v1/library/trash/<batch_id>/restore
# ---------------------------------------------------------------------------


def test_restore_invalid_batch_id(client, temp_dir, monkeypatch):
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", temp_dir)
    from config import reload_settings
    reload_settings()

    # batch_id with non-alphanumeric chars → 400 (isalnum guard)
    resp = client.post("/api/v1/library/trash/abc-def-123/restore")
    assert resp.status_code == 400


def test_restore_nonexistent_batch(client, temp_dir, monkeypatch):
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", temp_dir)
    from config import reload_settings
    reload_settings()

    resp = client.post("/api/v1/library/trash/aabbccdd1234567890123456/restore")
    assert resp.status_code == 404


def test_restore_batch_success(client, temp_dir, monkeypatch):
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", temp_dir)
    from config import reload_settings
    reload_settings()

    sub_path = _make_sub(temp_dir, "show.en.ass")
    del_resp = client.delete("/api/v1/library/subtitles", json={"paths": [sub_path]})
    batch_id = del_resp.get_json()["batch_id"]

    assert not os.path.exists(sub_path)

    restore_resp = client.post(f"/api/v1/library/trash/{batch_id}/restore")
    data = restore_resp.get_json()
    assert restore_resp.status_code == 200
    assert data["restored"] == 1
    assert data["failed"] == 0
    assert os.path.exists(sub_path)


# ---------------------------------------------------------------------------
# DELETE /api/v1/library/trash/<batch_id> — permanent purge
# ---------------------------------------------------------------------------


def test_purge_invalid_batch_id(client, temp_dir, monkeypatch):
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", temp_dir)
    from config import reload_settings
    reload_settings()

    # batch_id with non-alphanumeric chars → 400 (isalnum guard)
    resp = client.delete("/api/v1/library/trash/abc-def-123")
    assert resp.status_code == 400


def test_purge_nonexistent_batch(client, temp_dir, monkeypatch):
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", temp_dir)
    from config import reload_settings
    reload_settings()

    resp = client.delete("/api/v1/library/trash/aabbccdd1234567890123456")
    assert resp.status_code == 404


def test_purge_batch_success(client, temp_dir, monkeypatch):
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", temp_dir)
    from config import reload_settings
    reload_settings()

    sub_path = _make_sub(temp_dir, "show.de.ass")
    del_resp = client.delete("/api/v1/library/subtitles", json={"paths": [sub_path]})
    batch_id = del_resp.get_json()["batch_id"]

    purge_resp = client.delete(f"/api/v1/library/trash/{batch_id}")
    data = purge_resp.get_json()
    assert purge_resp.status_code == 200
    assert data["purged"] == 1

    # Trash batch directory should be gone
    list_resp = client.get("/api/v1/library/trash")
    assert list_resp.get_json()["batches"] == []


# ---------------------------------------------------------------------------
# GET /api/v1/library/episodes/<ep_id>/subtitles — sonarr-dependent
# ---------------------------------------------------------------------------


def test_list_episode_subtitles_sonarr_not_configured(client, monkeypatch):
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: None)
    resp = client.get("/api/v1/library/episodes/1/subtitles")
    assert resp.status_code == 503


def test_list_episode_subtitles_no_file(client, monkeypatch):
    mock_sonarr = MagicMock()
    mock_sonarr.get_episode_file_path.return_value = None
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: mock_sonarr)
    resp = client.get("/api/v1/library/episodes/99/subtitles")
    assert resp.status_code == 404


def test_list_episode_subtitles_file_not_found_on_disk(client, temp_dir, monkeypatch):
    mock_sonarr = MagicMock()
    mock_sonarr.get_episode_file_path.return_value = "/nonexistent/path/episode.mkv"
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: mock_sonarr)
    monkeypatch.setattr("config.map_path", lambda p: p)
    resp = client.get("/api/v1/library/episodes/1/subtitles")
    assert resp.status_code == 404


def test_list_episode_subtitles_success_empty(client, temp_dir, monkeypatch):
    video = os.path.join(temp_dir, "episode.mkv")
    Path(video).touch()

    mock_sonarr = MagicMock()
    mock_sonarr.get_episode_file_path.return_value = video
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: mock_sonarr)
    monkeypatch.setattr("config.map_path", lambda p: p)

    resp = client.get("/api/v1/library/episodes/1/subtitles")
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["subtitles"] == []


def test_list_episode_subtitles_success_with_sidecar(client, temp_dir, monkeypatch):
    video = os.path.join(temp_dir, "episode.mkv")
    Path(video).touch()
    _make_sub(temp_dir, "episode.de.srt")

    mock_sonarr = MagicMock()
    mock_sonarr.get_episode_file_path.return_value = video
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: mock_sonarr)
    monkeypatch.setattr("config.map_path", lambda p: p)

    resp = client.get("/api/v1/library/episodes/1/subtitles")
    data = resp.get_json()
    assert resp.status_code == 200
    assert len(data["subtitles"]) == 1
    assert data["subtitles"][0]["language"] == "de"


# ---------------------------------------------------------------------------
# GET /api/v1/library/series/<id>/subtitles — sonarr-dependent
# ---------------------------------------------------------------------------


def test_list_series_subtitles_sonarr_not_configured(client, monkeypatch):
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: None)
    # Without standalone series, should return 503
    with patch("db.standalone.get_standalone_series", return_value=None):
        resp = client.get("/api/v1/library/series/1/subtitles")
    assert resp.status_code == 503


def test_list_series_subtitles_no_files(client, monkeypatch):
    mock_sonarr = MagicMock()
    mock_sonarr.get_episode_files_by_series.return_value = {}
    mock_sonarr.get_episodes.return_value = []
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: mock_sonarr)
    resp = client.get("/api/v1/library/series/1/subtitles")
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["subtitles"] == {}
