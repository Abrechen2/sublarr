"""HTTP tests for routes/subtitles.py — sidecar discovery, trash, and download."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

# ─── Episode subtitle sidecar endpoints ────────────────────────────────────────


def test_list_episode_subtitles_sonarr_not_configured(client, monkeypatch):
    """Returns 503 when no Sonarr client is configured."""
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda: None)
    resp = client.get("/api/v1/library/episodes/1/subtitles")
    assert resp.status_code == 503
    assert "error" in resp.get_json()


def test_list_episode_subtitles_no_video_file(client, monkeypatch):
    """Returns 404 when episode has no video file path."""
    mock_sonarr = MagicMock()
    mock_sonarr.get_episode_file_path.return_value = None
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda: mock_sonarr)
    resp = client.get("/api/v1/library/episodes/99/subtitles")
    assert resp.status_code == 404
    data = resp.get_json()
    assert "error" in data


def test_list_episode_subtitles_video_file_not_on_disk(client, monkeypatch):
    """Returns 404 when video file path does not exist on disk."""
    mock_sonarr = MagicMock()
    mock_sonarr.get_episode_file_path.return_value = "/nonexistent/video.mkv"
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda: mock_sonarr)
    monkeypatch.setattr("config.map_path", lambda p: p)
    resp = client.get("/api/v1/library/episodes/1/subtitles")
    assert resp.status_code == 404


def test_list_episode_subtitles_success(client, monkeypatch, temp_dir):
    """Returns 200 with subtitle list when episode video file exists."""
    # Create a fake video file + sidecar
    video = os.path.join(temp_dir, "episode.mkv")
    sidecar = os.path.join(temp_dir, "episode.de.ass")
    Path(video).write_bytes(b"fake")
    Path(sidecar).write_bytes(b"fake sub")

    mock_sonarr = MagicMock()
    mock_sonarr.get_episode_file_path.return_value = video
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda: mock_sonarr)
    monkeypatch.setattr("config.map_path", lambda p: p)

    resp = client.get("/api/v1/library/episodes/1/subtitles")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "subtitles" in data
    assert "video_path" in data
    assert any(s["language"] == "de" for s in data["subtitles"])


def test_list_series_subtitles_sonarr_not_configured(client, monkeypatch):
    """Returns 503 when Sonarr not configured and no standalone series."""
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda: None)
    monkeypatch.setattr("db.standalone.get_standalone_series", lambda sid: None)
    resp = client.get("/api/v1/library/series/1/subtitles")
    assert resp.status_code == 503


def test_list_series_subtitles_empty_episode_files(client, monkeypatch):
    """Returns 200 with empty subtitles when series has no episode files."""
    mock_sonarr = MagicMock()
    mock_sonarr.get_episode_files_by_series.return_value = {}
    mock_sonarr.get_episodes.return_value = []
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda: mock_sonarr)

    resp = client.get("/api/v1/library/series/1/subtitles")
    assert resp.status_code == 200
    assert resp.get_json()["subtitles"] == {}


# ─── Trash (soft-delete) endpoints ─────────────────────────────────────────────


def test_delete_subtitles_missing_paths(client):
    """Returns 400 when paths field is missing or empty."""
    resp = client.delete("/api/v1/library/subtitles", json={})
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_delete_subtitles_empty_paths_list(client):
    """Returns 400 when paths is an empty list."""
    resp = client.delete("/api/v1/library/subtitles", json={"paths": []})
    assert resp.status_code == 400


def test_delete_subtitles_path_outside_media(client, monkeypatch, temp_dir):
    """Files outside media_path are rejected with a 'failed' entry."""
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", temp_dir)

    from config import reload_settings

    reload_settings()

    resp = client.delete(
        "/api/v1/library/subtitles",
        json={"paths": ["/etc/passwd.de.ass"]},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["failed"]) == 1
    assert data["deleted"] == []


def test_delete_subtitles_file_not_found(client, monkeypatch, temp_dir):
    """Returns failed entry when file does not exist on disk."""
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", temp_dir)
    from config import reload_settings

    reload_settings()

    resp = client.delete(
        "/api/v1/library/subtitles",
        json={"paths": [os.path.join(temp_dir, "nonexistent.de.ass")]},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["failed"]) == 1


def test_delete_subtitles_success(client, monkeypatch, temp_dir):
    """Moves subtitle file to trash and returns deleted list."""
    sub_file = os.path.join(temp_dir, "video.de.ass")
    Path(sub_file).write_text("[Script Info]\n", encoding="utf-8")

    monkeypatch.setenv("SUBLARR_MEDIA_PATH", temp_dir)
    from config import reload_settings

    reload_settings()

    resp = client.delete(
        "/api/v1/library/subtitles",
        json={"paths": [sub_file]},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert sub_file in data["deleted"]
    assert "batch_id" in data
    assert not os.path.exists(sub_file)  # file was moved to trash


def test_list_trash_empty(client, monkeypatch, temp_dir):
    """Returns empty batches list when no trash exists."""
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", temp_dir)
    from config import reload_settings

    reload_settings()

    resp = client.get("/api/v1/library/trash")
    assert resp.status_code == 200
    assert resp.get_json()["batches"] == []


def test_list_trash_with_batch(client, monkeypatch, temp_dir):
    """Returns batch info after a file has been trashed."""
    sub_file = os.path.join(temp_dir, "ep1.de.ass")
    Path(sub_file).write_text("[Script Info]\n", encoding="utf-8")

    monkeypatch.setenv("SUBLARR_MEDIA_PATH", temp_dir)
    from config import reload_settings

    reload_settings()

    # First, delete a file to create a trash batch
    del_resp = client.delete("/api/v1/library/subtitles", json={"paths": [sub_file]})
    assert del_resp.status_code == 200

    # Now list trash
    resp = client.get("/api/v1/library/trash")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["batches"]) >= 1
    batch = data["batches"][0]
    assert "batch_id" in batch
    assert "file_count" in batch


def test_restore_trash_batch_invalid_id(client, monkeypatch, temp_dir):
    """Returns 400 for non-alphanumeric batch_id containing hyphens."""
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", temp_dir)
    from config import reload_settings

    reload_settings()

    resp = client.post("/api/v1/library/trash/bad-id-here/restore")
    assert resp.status_code == 400


def test_restore_trash_batch_not_found(client, monkeypatch, temp_dir):
    """Returns 404 for a batch_id that does not exist."""
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", temp_dir)
    from config import reload_settings

    reload_settings()

    resp = client.post("/api/v1/library/trash/nonexistentbatch123/restore")
    assert resp.status_code == 404


def test_restore_trash_batch_success(client, monkeypatch, temp_dir):
    """Successfully restores a previously trashed file."""
    sub_file = os.path.join(temp_dir, "ep_restore.de.ass")
    Path(sub_file).write_text("[Script Info]\n", encoding="utf-8")

    monkeypatch.setenv("SUBLARR_MEDIA_PATH", temp_dir)
    from config import reload_settings

    reload_settings()

    # Trash it
    del_resp = client.delete("/api/v1/library/subtitles", json={"paths": [sub_file]})
    batch_id = del_resp.get_json()["batch_id"]

    # Restore it
    resp = client.post(f"/api/v1/library/trash/{batch_id}/restore")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["restored"] == 1
    assert data["failed"] == 0
    assert os.path.exists(sub_file)  # file is back


def test_purge_trash_batch_invalid_id(client, monkeypatch, temp_dir):
    """Returns 400 for non-alphanumeric batch_id."""
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", temp_dir)
    from config import reload_settings

    reload_settings()

    resp = client.delete("/api/v1/library/trash/bad-id-here")
    assert resp.status_code == 400


def test_purge_trash_batch_not_found(client, monkeypatch, temp_dir):
    """Returns 404 for non-existent batch."""
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", temp_dir)
    from config import reload_settings

    reload_settings()

    resp = client.delete("/api/v1/library/trash/abc123notexist")
    assert resp.status_code == 404


def test_purge_trash_batch_success(client, monkeypatch, temp_dir):
    """Permanently deletes a trash batch."""
    sub_file = os.path.join(temp_dir, "ep_purge.de.ass")
    Path(sub_file).write_text("[Script Info]\n", encoding="utf-8")

    monkeypatch.setenv("SUBLARR_MEDIA_PATH", temp_dir)
    from config import reload_settings

    reload_settings()

    # Trash it
    del_resp = client.delete("/api/v1/library/subtitles", json={"paths": [sub_file]})
    batch_id = del_resp.get_json()["batch_id"]

    # Purge it
    resp = client.delete(f"/api/v1/library/trash/{batch_id}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "purged" in data


# ─── Download subtitle endpoint ─────────────────────────────────────────────────


def test_download_subtitle_missing_path(client):
    """Returns 400 when path query param is missing."""
    resp = client.get("/api/v1/subtitles/download")
    assert resp.status_code == 400


def test_download_subtitle_outside_media(client, monkeypatch, temp_dir):
    """Returns 403 when path is outside media_path."""
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", temp_dir)
    from config import reload_settings

    reload_settings()

    resp = client.get("/api/v1/subtitles/download?path=/etc/shadow")
    assert resp.status_code == 403


def test_download_subtitle_wrong_extension(client, monkeypatch, temp_dir):
    """Returns 403 when file has a non-subtitle extension."""
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", temp_dir)
    from config import reload_settings

    reload_settings()

    bad_file = os.path.join(temp_dir, "file.exe")
    Path(bad_file).write_bytes(b"binary")

    resp = client.get(f"/api/v1/subtitles/download?path={bad_file}")
    assert resp.status_code == 403


def test_download_subtitle_file_not_found(client, monkeypatch, temp_dir):
    """Returns 404 when subtitle file does not exist."""
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", temp_dir)
    from config import reload_settings

    reload_settings()

    resp = client.get(f"/api/v1/subtitles/download?path={temp_dir}/missing.de.ass")
    assert resp.status_code == 404


def test_download_subtitle_success(client, monkeypatch, temp_dir):
    """Returns 200 with file content for a valid subtitle file."""
    sub_file = os.path.join(temp_dir, "ep.de.ass")
    Path(sub_file).write_text("[Script Info]\nTitle: Test\n", encoding="utf-8")

    monkeypatch.setenv("SUBLARR_MEDIA_PATH", temp_dir)
    from config import reload_settings

    reload_settings()

    resp = client.get(f"/api/v1/subtitles/download?path={sub_file}")
    assert resp.status_code == 200
    assert resp.headers.get("Content-Disposition", "").startswith("attachment")


# ─── scan_subtitle_sidecars helper (unit level) ─────────────────────────────────


def test_scan_subtitle_sidecars_no_sidecars(temp_dir):
    """Returns empty list when no subtitle files exist next to video."""
    from routes.subtitles import scan_subtitle_sidecars

    video = os.path.join(temp_dir, "ep.mkv")
    Path(video).write_bytes(b"fake")
    result = scan_subtitle_sidecars(video)
    assert result == []


def test_scan_subtitle_sidecars_finds_ass(temp_dir):
    """Finds .de.ass sidecar next to video file."""
    from routes.subtitles import scan_subtitle_sidecars

    video = os.path.join(temp_dir, "show.S01E01.mkv")
    sidecar = os.path.join(temp_dir, "show.S01E01.de.ass")
    Path(video).write_bytes(b"fake")
    Path(sidecar).write_text("[Script Info]\n", encoding="utf-8")

    result = scan_subtitle_sidecars(video)
    assert len(result) == 1
    assert result[0]["language"] == "de"
    assert result[0]["format"] == "ass"


def test_scan_subtitle_sidecars_multiple_languages(temp_dir):
    """Finds multiple language sidecars next to the same video."""
    from routes.subtitles import scan_subtitle_sidecars

    video = os.path.join(temp_dir, "movie.mkv")
    Path(video).write_bytes(b"fake")
    for lang in ("de", "en", "fr"):
        Path(os.path.join(temp_dir, f"movie.{lang}.srt")).write_text("1\n", encoding="utf-8")

    result = scan_subtitle_sidecars(video)
    langs = {r["language"] for r in result}
    assert langs == {"de", "en", "fr"}


def test_scan_subtitle_sidecars_ignores_video_itself(temp_dir):
    """Video file is not included in sidecar results."""
    from routes.subtitles import scan_subtitle_sidecars

    video = os.path.join(temp_dir, "ep.mkv")
    Path(video).write_bytes(b"fake")
    result = scan_subtitle_sidecars(video)
    paths = [r["path"] for r in result]
    assert video not in paths


def test_scan_subtitle_sidecars_ignores_non_subtitle_ext(temp_dir):
    """Non-subtitle files with the right naming pattern are ignored."""
    from routes.subtitles import scan_subtitle_sidecars

    video = os.path.join(temp_dir, "movie.mkv")
    Path(video).write_bytes(b"fake")
    Path(os.path.join(temp_dir, "movie.de.txt")).write_text("text", encoding="utf-8")

    result = scan_subtitle_sidecars(video)
    assert result == []


# ─── Batch-delete series subtitles ──────────────────────────────────────────────


def test_batch_delete_series_subtitles_sonarr_not_configured(client, monkeypatch):
    """Returns 503 when Sonarr not configured."""
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda: None)
    resp = client.post("/api/v1/library/series/1/subtitles/batch-delete", json={})
    assert resp.status_code == 503


def test_batch_delete_series_subtitles_no_episode_files(client, monkeypatch):
    """Returns 200 with zero deleted when series has no episode files."""
    mock_sonarr = MagicMock()
    mock_sonarr.get_episode_files_by_series.return_value = {}
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda: mock_sonarr)

    resp = client.post("/api/v1/library/series/1/subtitles/batch-delete", json={})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["deleted"] == 0
