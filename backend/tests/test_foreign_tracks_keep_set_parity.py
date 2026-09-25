"""Final-review I2: the live preview reaches the SAME keep-set as the queue
drain, through one shared helper, driven through both production call
shapes (the drain's ``_foreign_track_cleanup`` and the HTTP preview)."""

from unittest.mock import patch

_STREAMS = {
    "streams": [
        {"index": 0, "codec_type": "video", "codec_name": "h264"},
        {"index": 2, "codec_type": "subtitle", "codec_name": "subrip", "tags": {"language": "ger"}},
        {"index": 3, "codec_type": "subtitle", "codec_name": "subrip", "tags": {"language": "jpn"}},
        {"index": 4, "codec_type": "subtitle", "codec_name": "subrip", "tags": {"language": "fre"}},
        {"index": 5, "codec_type": "subtitle", "codec_name": "subrip", "tags": {"language": "eng"}},
    ]
}
_PROFILE = {"target_languages": ["de", "ja"]}


def _settings(monkeypatch):
    from config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "cleanup_foreign_tracks_default", True)
    monkeypatch.setattr(s, "cleanup_foreign_tracks_keep_languages", ["en"])
    monkeypatch.setattr(s, "cleanup_foreign_tracks_keep_und", False)
    monkeypatch.setattr(s, "wanted_auto_translate", False)


def _drain_strips(video) -> set[int]:
    from services.subtitle_automation_runner import SubtitleAutomationRunner

    captured = {}

    def fake_remove(*, video_path, streams, **kw):
        captured["streams"] = streams
        return "/bak"

    with (
        patch("services.embedded_extractor.resolve_profile_for_item", return_value=_PROFILE),
        patch("remux.get_media_streams", return_value=_STREAMS),
        patch("remux.check_hardlink_policy", return_value=True),
        patch("remux.remove_subtitle_streams", side_effect=fake_remove),
        patch("services.media_server_notify.notify_media_servers"),
    ):
        SubtitleAutomationRunner()._foreign_track_cleanup(5, str(video), "de")
    return {index for index, _sub in captured.get("streams", [])}


def _preview_strips(client, video, monkeypatch) -> set[int]:
    monkeypatch.setattr("routes.foreign_tracks_preview.is_safe_path", lambda *a, **k: True)
    with (
        patch("services.embedded_extractor.resolve_profile_for_item", return_value=_PROFILE),
        patch("remux.get_media_streams", return_value=_STREAMS),
    ):
        resp = client.post(
            "/api/v1/foreign-tracks/preview-file", json={"path": str(video), "series_id": 5}
        )
    assert resp.status_code == 200, resp.get_json()
    return {v["index"] for v in resp.get_json()["verdicts"] if not v["keep"]}


def test_preview_and_drain_strip_the_same_tracks(client, tmp_path, monkeypatch):
    video = tmp_path / "e1.mkv"
    video.write_bytes(b"v")
    with client.application.app_context():
        _settings(monkeypatch)
        drain = _drain_strips(video)
    preview = _preview_strips(client, video, monkeypatch)
    assert drain == {4}, "the drain keeps the profile's de+ja and the always-keep en"
    assert preview == drain


def test_the_drain_refuses_to_strip_when_the_profile_cannot_be_resolved(
    app_ctx, tmp_path, monkeypatch
):
    """Falling back to the hook's own keep-set (downloaded language + always-
    keep) would strip the profile's other target languages — fail instead,
    the queue retries."""
    import pytest

    from services.subtitle_automation_runner import SubtitleAutomationRunner

    _settings(monkeypatch)
    video = tmp_path / "e1.mkv"
    video.write_bytes(b"v")
    with (
        patch(
            "services.embedded_extractor.resolve_profile_for_item",
            side_effect=RuntimeError("profiles table gone"),
        ),
        patch("remux.remove_foreign_subtitle_streams") as strip,
        pytest.raises(RuntimeError),
    ):
        SubtitleAutomationRunner()._foreign_track_cleanup(5, str(video), "de")
    assert not strip.called


def test_the_preview_answers_503_when_the_profile_cannot_be_resolved(client, tmp_path, monkeypatch):
    video = tmp_path / "e1.mkv"
    video.write_bytes(b"v")
    monkeypatch.setattr("routes.foreign_tracks_preview.is_safe_path", lambda *a, **k: True)
    with (
        patch(
            "services.embedded_extractor.resolve_profile_for_item",
            side_effect=RuntimeError("profiles table gone"),
        ),
        patch("remux.get_media_streams", return_value=_STREAMS),
    ):
        resp = client.post(
            "/api/v1/foreign-tracks/preview-file", json={"path": str(video), "series_id": 5}
        )
    assert resp.status_code == 503
