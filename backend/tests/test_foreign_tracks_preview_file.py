"""Read-only per-track foreign-track cleanup preview for one video file.

`POST /api/v1/foreign-tracks/preview-file` must reach the SAME keep/strip
verdict a real strip would (via `services.foreign_track_cleanup.maybe_run_
foreign_track_cleanup`) and must never touch the file. Both entry points
share `services.foreign_track_cleanup.keep_tags_for` for the keep-set, so a
test here also pins that they actually agree for the same item.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


def test_preview_lists_every_track_with_its_reason(client, tmp_path, monkeypatch):
    video = tmp_path / "e1.mkv"
    video.write_bytes(b"v")
    monkeypatch.setattr("routes.foreign_tracks_preview.is_safe_path", lambda *a, **k: True)
    probe = {
        "streams": [
            {
                "index": 2,
                "codec_type": "subtitle",
                "codec_name": "subrip",
                "tags": {"language": "fre", "title": "French"},
            },
        ]
    }
    with patch("remux.get_media_streams", return_value=probe):
        resp = client.post("/api/v1/foreign-tracks/preview-file", json={"path": str(video)})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["path"] == str(video)
    assert "policy" in body
    assert body["verdicts"][0]["reason"] == "stripped_language"


def test_preview_refuses_paths_outside_the_media_root(client):
    resp = client.post("/api/v1/foreign-tracks/preview-file", json={"path": "/etc/passwd"})
    assert resp.status_code == 403


def test_preview_requires_a_path(client):
    resp = client.post("/api/v1/foreign-tracks/preview-file", json={})
    assert resp.status_code == 400


def test_preview_404s_on_a_missing_file(client, tmp_path, monkeypatch):
    monkeypatch.setattr("routes.foreign_tracks_preview.is_safe_path", lambda *a, **k: True)
    resp = client.post(
        "/api/v1/foreign-tracks/preview-file",
        json={"path": str(tmp_path / "nope.mkv")},
    )
    assert resp.status_code == 404


def test_preview_never_remuxes(client, tmp_path, monkeypatch):
    video = tmp_path / "e1.mkv"
    video.write_bytes(b"v")
    monkeypatch.setattr("routes.foreign_tracks_preview.is_safe_path", lambda *a, **k: True)
    with (
        patch("remux.get_media_streams", return_value={"streams": []}),
        patch("remux.remove_subtitle_streams") as strip,
        patch("remux.remove_foreign_subtitle_streams") as strip_foreign,
    ):
        client.post("/api/v1/foreign-tracks/preview-file", json={"path": str(video)})
    assert not strip.called
    assert not strip_foreign.called


@pytest.mark.parametrize(
    "body",
    [
        {"series_id": "abc"},
        {"series_id": -1},
        {"series_id": 3.5},
        {"series_id": [1, 2]},
        {"series_id": True},  # JSON true -- bool is an int subclass, must not bind as id 1
        {"movie_id": "abc"},
        {"movie_id": -1},
        {"movie_id": 3.5},
        {"movie_id": [1, 2]},
        {"movie_id": False},  # JSON false -- must not silently resolve as "no id"
        {"series_id": 1, "movie_id": 1},  # mutually exclusive
        {"path": 123},  # non-string path
        {"path": ""},  # empty string path
    ],
)
def test_preview_rejects_invalid_series_or_movie_ids(client, tmp_path, monkeypatch, body):
    video = tmp_path / "e1.mkv"
    video.write_bytes(b"v")
    monkeypatch.setattr("routes.foreign_tracks_preview.is_safe_path", lambda *a, **k: True)
    payload = {"path": str(video), **body}
    with patch("remux.get_media_streams", return_value={"streams": []}):
        resp = client.post("/api/v1/foreign-tracks/preview-file", json=payload)
    assert resp.status_code == 400, f"body={body!r} got {resp.status_code}: {resp.get_json()}"


def test_preview_accepts_valid_series_id_and_resolves_the_override(client, tmp_path, monkeypatch):
    from services.foreign_tracks.select import TrackPolicy

    video = tmp_path / "e1.mkv"
    video.write_bytes(b"v")
    monkeypatch.setattr("routes.foreign_tracks_preview.is_safe_path", lambda *a, **k: True)
    override_policy = TrackPolicy(mode="one_per_language", keep_sdh=True)
    with (
        patch("remux.get_media_streams", return_value={"streams": []}),
        patch(
            "services.foreign_tracks.policy.resolve_policy", return_value=override_policy
        ) as resolve,
    ):
        resp = client.post(
            "/api/v1/foreign-tracks/preview-file",
            json={"path": str(video), "series_id": 42},
        )
    assert resp.status_code == 200
    resolve.assert_called_once_with(series_id=42, movie_id=None)
    assert resp.get_json()["policy"]["mode"] == "one_per_language"
    assert resp.get_json()["policy"]["keep_sdh"] is True


def test_preview_accepts_valid_movie_id_and_resolves_the_override(client, tmp_path, monkeypatch):
    from services.foreign_tracks.select import TrackPolicy

    video = tmp_path / "e1.mkv"
    video.write_bytes(b"v")
    monkeypatch.setattr("routes.foreign_tracks_preview.is_safe_path", lambda *a, **k: True)
    override_policy = TrackPolicy(mode="one_per_language")
    with (
        patch("remux.get_media_streams", return_value={"streams": []}),
        patch(
            "services.foreign_tracks.policy.resolve_policy", return_value=override_policy
        ) as resolve,
    ):
        resp = client.post(
            "/api/v1/foreign-tracks/preview-file",
            json={"path": str(video), "movie_id": 7},
        )
    assert resp.status_code == 200
    resolve.assert_called_once_with(series_id=None, movie_id=7)


def test_preview_and_hook_reach_the_same_keep_set(client, tmp_path, monkeypatch):
    """The preview must reach the SAME keep-set the real post-download hook
    would for the same item — both go through `keep_tags_for`, never a
    re-implementation local to the route.
    """
    from services import foreign_track_cleanup as ftc

    fake_settings = SimpleNamespace(
        media_path=str(tmp_path),
        cleanup_foreign_tracks_default=True,
        cleanup_foreign_tracks_keep_und=True,
        cleanup_foreign_tracks_keep_languages=["de", "en"],
    )

    video = tmp_path / "e1.mkv"
    video.write_bytes(b"v")
    # Same item shape the preview constructs from its request body — no
    # missing_languages/target_language, since the preview never sees those.
    item = {"sonarr_series_id": None, "radarr_movie_id": None}

    calls: list[tuple[set, set]] = []
    real_keep_tags_for = ftc.keep_tags_for

    def spy(item_arg, target_languages=None):
        result = real_keep_tags_for(item_arg, target_languages)
        calls.append(result)
        return result

    monkeypatch.setattr(ftc, "keep_tags_for", spy)
    monkeypatch.setattr("routes.foreign_tracks_preview.is_safe_path", lambda *a, **k: True)

    strip = MagicMock(return_value=None)
    with (
        patch("config.get_settings", return_value=fake_settings),
        patch("remux.get_media_streams", return_value={"streams": []}),
        patch("remux.remove_foreign_subtitle_streams", strip),
    ):
        resp = client.post("/api/v1/foreign-tracks/preview-file", json={"path": str(video)})
        assert resp.status_code == 200

        ftc.maybe_run_foreign_track_cleanup(item, str(video))

    assert len(calls) == 2, "both the preview and the hook must call keep_tags_for"
    assert calls[0] == calls[1], "preview and hook must resolve the same keep-set"
