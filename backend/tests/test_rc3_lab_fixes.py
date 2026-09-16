"""Behavioural regressions reproduced on the RC.3 integration lab."""

import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.mark.parametrize("existing", ["srt", "embedded_srt"])
@pytest.mark.parametrize("upgrade", [True, False])
def test_standalone_srt_respects_upgrade_setting(app_ctx, tmp_path, monkeypatch, existing, upgrade):
    from config import get_settings
    from standalone.scanner import StandaloneScanner

    monkeypatch.setattr(get_settings(), "upgrade_enabled", upgrade)
    assert StandaloneScanner()._language_satisfied(str(tmp_path / "show.mkv"), "en", existing) == (
        not upgrade
    )


@pytest.mark.parametrize("status", ["wanted", "provisional"])
def test_embedded_srt_rescan_cleans_only_nonprovisional_rows(
    app_ctx, tmp_path, monkeypatch, status
):
    from config import get_settings
    from db.wanted import get_wanted_item, update_wanted_status, upsert_wanted_item
    from standalone.scanner import StandaloneScanner

    monkeypatch.setattr(get_settings(), "upgrade_enabled", False)
    path = str(tmp_path / "show.mkv")
    item_id, _ = upsert_wanted_item(
        item_type="episode",
        file_path=path,
        title="Show",
        target_language="en",
        missing_languages=["en"],
    )
    update_wanted_status(item_id, status)
    assert StandaloneScanner()._language_satisfied(path, "en", "embedded_srt")
    assert (get_wanted_item(item_id) is not None) == (status == "provisional")


@pytest.mark.parametrize("value", [9, 0, 201, True, 25.5, "bad", "²", None])
def test_bad_page_size_is_rejected_before_other_keys_are_saved(client, value):
    from db.config import get_config_entry

    with client.application.app_context():
        before = get_config_entry("default_library_sort")
    response = client.put(
        "/api/v1/config", json={"default_library_sort": "score", "items_per_page": value}
    )
    assert response.status_code == 400
    with client.application.app_context():
        assert get_config_entry("default_library_sort") == before


@pytest.mark.parametrize("value", [10, 200, "75"])
def test_valid_page_size_roundtrips(client, value):
    response = client.put("/api/v1/config", json={"items_per_page": value})
    assert response.status_code == 200
    assert response.get_json()["config"]["items_per_page"] == int(value)


@pytest.fixture
def radarr_video(tmp_path, monkeypatch):
    video = tmp_path / "Film.mkv"
    video.touch()
    (tmp_path / "Film.en.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n")
    movie = {
        "id": 99,
        "title": "Film",
        "path": "/remote/Film",
        "movieFile": {"path": "/remote/Film/Film.mkv"},
    }
    client = Mock()
    client.get_movie_by_id.return_value = movie
    monkeypatch.setattr("radarr_client.get_radarr_client", lambda: client)
    monkeypatch.setattr("db.standalone.get_standalone_movies", lambda mid: None)
    monkeypatch.setattr(
        "config.map_path", lambda p: str(video) if p == "/remote/Film/Film.mkv" else p
    )
    return video, movie, client


def test_radarr_sidecars_use_mapped_video_file(client, radarr_video):
    video, _, _ = radarr_video
    response = client.get("/api/v1/library/movies/99/subtitles")
    assert response.status_code == 200
    assert response.get_json()["video_path"] == str(video)
    assert len(response.get_json()["subtitles"]) == 1


def test_radarr_movie_file_id_fallback(app_ctx, radarr_video):
    from services.movie_video_path import resolve_movie_video_path

    video, movie, radarr = radarr_video
    movie.pop("movieFile")
    movie["movieFileId"] = 7
    radarr.get_movie_file.return_value = {"path": "/remote/Film/Film.mkv"}
    assert resolve_movie_video_path(99) == str(video)
    radarr.get_movie_file.assert_called_once_with(7)


def test_radarr_directory_is_not_a_video(client, radarr_video):
    _, movie, _ = radarr_video
    movie.pop("movieFile")
    assert client.get("/api/v1/library/movies/99/subtitles").status_code == 404


def test_standalone_id_keeps_priority(app_ctx, radarr_video, monkeypatch, tmp_path):
    from services.movie_video_path import resolve_movie_video_path

    _, _, radarr = radarr_video
    standalone = tmp_path / "Standalone.mkv"
    standalone.touch()
    monkeypatch.setattr(
        "db.standalone.get_standalone_movies", lambda mid: {"file_path": str(standalone)}
    )
    assert resolve_movie_video_path(99) == str(standalone)
    radarr.get_movie_by_id.assert_not_called()


def test_radarr_detail_reports_real_wanted_count(client, radarr_video):
    from db.wanted import upsert_wanted_item

    video, _, _ = radarr_video
    with client.application.app_context():
        upsert_wanted_item(
            item_type="movie",
            file_path=str(video),
            title="Film",
            radarr_movie_id=99,
            target_language="de",
            missing_languages=["de"],
        )
    response = client.get("/api/v1/standalone/movies/99")
    assert response.status_code == 200
    assert response.get_json()["wanted_count"] == 1
    assert response.get_json()["file_path"] == str(video)


@pytest.mark.parametrize(
    "age,hostname,healthy",
    [(0, "here", True), (420, "here", True), (600, "here", False), (0, "other", False)],
)
def test_worker_health_uses_own_live_heartbeat(age, hostname, healthy):
    from worker_health import worker_is_healthy

    now = datetime.now(UTC)
    worker = SimpleNamespace(
        hostname=hostname,
        pid=os.getpid(),
        last_heartbeat=now - timedelta(seconds=age),
        worker_ttl=420,
    )
    assert worker_is_healthy(worker, hostname="here", now=now) == healthy


def test_worker_health_without_cap_kill(monkeypatch):
    from worker_health import worker_is_healthy

    now = datetime.now(UTC)
    worker = SimpleNamespace(hostname="here", pid=1, last_heartbeat=now, worker_ttl=420)
    monkeypatch.setattr("worker_health.os.kill", Mock(side_effect=PermissionError()))
    assert worker_is_healthy(worker, hostname="here", now=now)


def test_radarr_path_outside_the_media_roots_is_refused(
    client, radarr_video, monkeypatch, tmp_path
):
    """The path comes from the Radarr API; upload writes next to it (is_safe_path rule)."""
    elsewhere = tmp_path / "configured-media"
    elsewhere.mkdir()
    monkeypatch.setattr("services.trash_locations.media_paths", lambda: [str(elsewhere)])

    assert client.get("/api/v1/library/movies/99/subtitles").status_code == 404
    upload = client.post("/api/v1/library/movies/99/subtitles/upload")
    assert upload.status_code == 404


def test_standalone_movies_outside_the_media_roots_still_resolve(
    app_ctx, radarr_video, monkeypatch, tmp_path
):
    """Watched folders need not lie under media_path; the root rule is for Radarr data."""
    from services.movie_video_path import resolve_movie_video_path

    standalone = tmp_path / "watched" / "Standalone.mkv"
    standalone.parent.mkdir()
    standalone.touch()
    monkeypatch.setattr("services.trash_locations.media_paths", lambda: [str(tmp_path / "other")])
    monkeypatch.setattr(
        "db.standalone.get_standalone_movies", lambda mid: {"file_path": str(standalone)}
    )

    assert resolve_movie_video_path(99) == str(standalone)
