"""Tests for the embedded-stream strip path in services.cleanup_signs (Task 6)."""

from unittest.mock import MagicMock, patch


def _settings(media, level="signs_forced"):
    s = MagicMock()
    s.cleanup_signs_removal_level = level
    s.media_path = str(media)
    return s


def test_strips_signs_embedded_stream(tmp_path):
    from services.cleanup_signs import execute_signs_cleanup

    video = tmp_path / "Ep.mkv"
    video.write_bytes(b"fake")

    probe = {
        "streams": [
            {
                "codec_type": "subtitle",
                "codec_name": "ass",
                "disposition": {},
                "tags": {"language": "eng", "title": "Dialogue"},
            },
            {
                "codec_type": "subtitle",
                "codec_name": "ass",
                "disposition": {"forced": 1},
                "tags": {"language": "eng", "title": "Signs"},
            },
        ]
    }
    with (
        patch("config.get_settings", return_value=_settings(tmp_path)),
        patch("remux.get_media_streams", return_value=probe),
        patch(
            "remux.remove_subtitle_streams_by_index", return_value=str(tmp_path / "Ep.mkv.bak")
        ) as strip,
    ):
        result = execute_signs_cleanup(
            str(tmp_path), {"strip_embedded": True, "keep_languages": ["en"]}, dry_run=False
        )

    # subtitle order-index 1 (the forced "Signs" track) must be dropped
    strip.assert_called_once()
    assert strip.call_args[0][1] == [1]
    assert result["stripped_files"] == 1
    assert result["stripped_tracks"] == 1


def test_embedded_dry_run_does_not_strip(tmp_path):
    from services.cleanup_signs import execute_signs_cleanup

    video = tmp_path / "Ep.mkv"
    video.write_bytes(b"fake")
    probe = {
        "streams": [
            {
                "codec_type": "subtitle",
                "codec_name": "ass",
                "disposition": {"forced": 1},
                "tags": {"language": "eng", "title": "Signs"},
            },
            {
                "codec_type": "subtitle",
                "codec_name": "ass",
                "disposition": {},
                "tags": {"language": "eng", "title": "Dialogue"},
            },
        ]
    }
    with (
        patch("config.get_settings", return_value=_settings(tmp_path)),
        patch("remux.get_media_streams", return_value=probe),
        patch("remux.remove_subtitle_streams_by_index") as strip,
    ):
        result = execute_signs_cleanup(str(tmp_path), {"strip_embedded": True}, dry_run=True)
    strip.assert_not_called()
    assert result["would_strip_tracks"] == 1


def test_embedded_last_track_guard_keeps_only_lang_track(tmp_path):
    """When the signs track is the ONLY keep-language subtitle, it must not be dropped."""
    from services.cleanup_signs import execute_signs_cleanup

    video = tmp_path / "Ep.mkv"
    video.write_bytes(b"fake")
    probe = {
        "streams": [
            {
                "codec_type": "subtitle",
                "codec_name": "ass",
                "disposition": {"forced": 1},
                "tags": {"language": "eng", "title": "Signs"},
            },
        ]
    }
    with (
        patch("config.get_settings", return_value=_settings(tmp_path)),
        patch("remux.get_media_streams", return_value=probe),
        patch("remux.remove_subtitle_streams_by_index") as strip,
    ):
        result = execute_signs_cleanup(
            str(tmp_path),
            {"strip_embedded": True, "keep_languages": ["en"]},
            dry_run=False,
        )
    strip.assert_not_called()
    assert result["stripped_files"] == 0


def test_embedded_not_triggered_when_flag_false(tmp_path):
    """strip_embedded=False must not probe any video files."""
    from services.cleanup_signs import execute_signs_cleanup

    video = tmp_path / "Ep.mkv"
    video.write_bytes(b"fake")
    with (
        patch("config.get_settings", return_value=_settings(tmp_path)),
        patch("remux.get_media_streams") as probe_mock,
        patch("remux.remove_subtitle_streams_by_index") as strip,
    ):
        result = execute_signs_cleanup(str(tmp_path), {"strip_embedded": False}, dry_run=False)
    probe_mock.assert_not_called()
    strip.assert_not_called()
    assert result["stripped_files"] == 0
