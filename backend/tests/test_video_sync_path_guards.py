"""Path guards on the video-sync routes.

Containment under media_path is checked before existence on every route, so
a 404 never confirms that a path outside the library exists, and the alass
``reference_path`` (opened by alass) is held to media_path like the others.
"""

import os
from unittest.mock import patch

import pytest


@pytest.fixture
def media_dir(temp_dir, monkeypatch):
    media = os.path.join(temp_dir, "media")
    os.makedirs(media)
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", media)
    from config import reload_settings

    reload_settings()
    return media


def _srt(path):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("1\n00:00:01,000 --> 00:00:02,000\nHi\n")
    return path


@pytest.mark.parametrize(
    "url, body",
    [
        ("/api/v1/tools/video-sync", {"engine": "ffsubsync", "video_path": ""}),
        ("/api/v1/tools/video-sync/compare", {"reference_path": ""}),
        ("/api/v1/tools/auto-sync", {"video_path": ""}),
    ],
)
def test_missing_file_outside_media_is_403_not_404(client, media_dir, url, body):
    outside_missing = "/definitely/not/here.srt"
    payload = {**body, "file_path": outside_missing}
    if "video_path" in payload:
        payload["video_path"] = os.path.join(media_dir, "ep.mkv")
    if "reference_path" in payload:
        payload["reference_path"] = os.path.join(media_dir, "ref.srt")

    resp = client.post(url, json=payload)

    assert resp.status_code == 403, resp.get_data(as_text=True)


def test_auto_sync_missing_video_outside_media_is_403(client, media_dir):
    sub = _srt(os.path.join(media_dir, "ep.en.srt"))

    resp = client.post(
        "/api/v1/tools/auto-sync",
        json={"file_path": sub, "video_path": "/definitely/not/here.mkv"},
    )

    assert resp.status_code == 403


def test_alass_reference_path_outside_media_is_refused(client, media_dir, temp_dir):
    sub = _srt(os.path.join(media_dir, "ep.en.srt"))
    outside_ref = _srt(os.path.join(temp_dir, "outside.srt"))

    with patch("routes.video_sync._submit_sync") as submit:
        resp = client.post(
            "/api/v1/tools/video-sync",
            json={"file_path": sub, "engine": "alass", "reference_path": outside_ref},
        )

    assert resp.status_code == 403
    assert "reference_path" in resp.get_json()["error"]
    submit.assert_not_called()


def test_alass_reference_path_inside_media_is_accepted(client, media_dir):
    sub = _srt(os.path.join(media_dir, "ep.en.srt"))
    ref = _srt(os.path.join(media_dir, "ep.ja.srt"))

    with patch("routes.video_sync._submit_sync") as submit:
        resp = client.post(
            "/api/v1/tools/video-sync",
            json={"file_path": sub, "engine": "alass", "reference_path": ref},
        )

    assert resp.status_code in (200, 202), resp.get_data(as_text=True)
    submit.assert_called_once()


def test_missing_file_inside_media_is_still_404(client, media_dir):
    resp = client.post(
        "/api/v1/tools/video-sync",
        json={
            "file_path": os.path.join(media_dir, "nope.srt"),
            "video_path": os.path.join(media_dir, "ep.mkv"),
        },
    )

    assert resp.status_code == 404
