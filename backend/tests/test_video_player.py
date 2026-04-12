"""Tests for services/video_player.py — FFmpeg-based video/subtitle operations."""

import os
import subprocess
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# generate_hls_playlist
# ---------------------------------------------------------------------------


def test_hls_video_not_found():
    """Raise RuntimeError when video file does not exist."""
    from services.video_player import generate_hls_playlist

    with pytest.raises(RuntimeError, match="Video file not found"):
        generate_hls_playlist("/nonexistent/video.mkv", "/tmp/out")


def test_hls_success(tmp_path):
    """Happy path: FFmpeg succeeds, segments are counted."""
    from services.video_player import generate_hls_playlist

    video = tmp_path / "video.mkv"
    video.write_bytes(b"\x00" * 100)
    out_dir = str(tmp_path / "hls")

    mock_result = MagicMock(returncode=0, stderr="")
    with patch("services.video_player.subprocess.run", return_value=mock_result):
        # Create fake segments so listdir counts them
        os.makedirs(out_dir, exist_ok=True)
        for i in range(3):
            (tmp_path / "hls" / f"segment_{i:03d}.ts").write_bytes(b"\x00")

        result = generate_hls_playlist(str(video), out_dir)
    assert result["segment_count"] == 3
    assert "playlist.m3u8" in result["playlist_path"]


def test_hls_ffmpeg_fails(tmp_path):
    """FFmpeg nonzero return code raises RuntimeError."""
    from services.video_player import generate_hls_playlist

    video = tmp_path / "video.mkv"
    video.write_bytes(b"\x00" * 100)

    mock_result = MagicMock(returncode=1, stderr="encode error")
    with (
        patch("services.video_player.subprocess.run", return_value=mock_result),
        pytest.raises(RuntimeError, match="FFmpeg HLS generation failed"),
    ):
        generate_hls_playlist(str(video), str(tmp_path / "hls"))


def test_hls_ffmpeg_timeout(tmp_path):
    """FFmpeg timeout raises RuntimeError."""
    from services.video_player import generate_hls_playlist

    video = tmp_path / "video.mkv"
    video.write_bytes(b"\x00" * 100)

    with (
        patch(
            "services.video_player.subprocess.run",
            side_effect=subprocess.TimeoutExpired("ffmpeg", 600),
        ),
        pytest.raises(RuntimeError, match="timed out"),
    ):
        generate_hls_playlist(str(video), str(tmp_path / "hls"))


def test_hls_ffmpeg_not_found(tmp_path):
    """Missing ffmpeg raises RuntimeError."""
    from services.video_player import generate_hls_playlist

    video = tmp_path / "video.mkv"
    video.write_bytes(b"\x00" * 100)

    with (
        patch("services.video_player.subprocess.run", side_effect=FileNotFoundError),
        pytest.raises(RuntimeError, match="ffmpeg not found"),
    ):
        generate_hls_playlist(str(video), str(tmp_path / "hls"))


def test_hls_quality_presets(tmp_path):
    """Different quality presets use correct bitrate."""
    from services.video_player import generate_hls_playlist

    video = tmp_path / "video.mkv"
    video.write_bytes(b"\x00" * 100)

    for quality, expected_bitrate in [("low", "1000k"), ("high", "5000k")]:
        called_cmd = []

        def capture_run(cmd, **kwargs):
            called_cmd.clear()
            called_cmd.extend(cmd)
            os.makedirs(str(tmp_path / f"hls_{quality}"), exist_ok=True)
            return MagicMock(returncode=0)

        with patch("services.video_player.subprocess.run", side_effect=capture_run):
            generate_hls_playlist(str(video), str(tmp_path / f"hls_{quality}"), quality=quality)
        assert expected_bitrate in called_cmd


# ---------------------------------------------------------------------------
# generate_screenshot
# ---------------------------------------------------------------------------


def test_screenshot_video_not_found():
    """Raise RuntimeError when video does not exist."""
    from services.video_player import generate_screenshot

    with pytest.raises(RuntimeError, match="Video file not found"):
        generate_screenshot("/nonexistent/video.mkv", 10.0)


def test_screenshot_success(tmp_path):
    """Happy path: FFmpeg creates screenshot."""
    from services.video_player import generate_screenshot

    video = tmp_path / "video.mkv"
    video.write_bytes(b"\x00" * 100)
    out = str(tmp_path / "screenshot.jpg")

    def fake_run(cmd, **kwargs):
        # Create the output file like ffmpeg would
        with open(out, "wb") as f:
            f.write(b"\xff\xd8\xff")
        return MagicMock(returncode=0)

    with patch("services.video_player.subprocess.run", side_effect=fake_run):
        result = generate_screenshot(str(video), 10.0, output_path=out)
    assert result == out


def test_screenshot_auto_tempfile(tmp_path):
    """When output_path is None, a temp file is created."""
    from services.video_player import generate_screenshot

    video = tmp_path / "video.mkv"
    video.write_bytes(b"\x00" * 100)

    def fake_run(cmd, **kwargs):
        # The output_path is the last arg
        out_path = cmd[-1]
        with open(out_path, "wb") as f:
            f.write(b"\xff\xd8\xff")
        return MagicMock(returncode=0)

    with patch("services.video_player.subprocess.run", side_effect=fake_run):
        result = generate_screenshot(str(video), 5.0)
    assert result.endswith(".jpg")
    # Clean up temp file
    if os.path.exists(result):
        os.unlink(result)


def test_screenshot_ffmpeg_fails(tmp_path):
    """FFmpeg failure raises RuntimeError."""
    from services.video_player import generate_screenshot

    video = tmp_path / "video.mkv"
    video.write_bytes(b"\x00" * 100)

    mock_result = MagicMock(returncode=1, stderr="screenshot error")
    with (
        patch("services.video_player.subprocess.run", return_value=mock_result),
        pytest.raises(RuntimeError, match="FFmpeg screenshot failed"),
    ):
        generate_screenshot(str(video), 10.0, str(tmp_path / "out.jpg"))


def test_screenshot_timeout(tmp_path):
    """FFmpeg timeout raises RuntimeError."""
    from services.video_player import generate_screenshot

    video = tmp_path / "video.mkv"
    video.write_bytes(b"\x00" * 100)

    with (
        patch(
            "services.video_player.subprocess.run",
            side_effect=subprocess.TimeoutExpired("ffmpeg", 30),
        ),
        pytest.raises(RuntimeError, match="timed out"),
    ):
        generate_screenshot(str(video), 10.0, str(tmp_path / "out.jpg"))


def test_screenshot_no_output(tmp_path):
    """FFmpeg succeeds but produces no file."""
    from services.video_player import generate_screenshot

    video = tmp_path / "video.mkv"
    video.write_bytes(b"\x00" * 100)

    mock_result = MagicMock(returncode=0)
    with (
        patch("services.video_player.subprocess.run", return_value=mock_result),
        pytest.raises(RuntimeError, match="did not produce screenshot"),
    ):
        generate_screenshot(str(video), 10.0, str(tmp_path / "missing.jpg"))


# ---------------------------------------------------------------------------
# convert_subtitle_to_webvtt
# ---------------------------------------------------------------------------


def test_webvtt_subtitle_not_found():
    """Raise RuntimeError when subtitle file does not exist."""
    from services.video_player import convert_subtitle_to_webvtt

    with pytest.raises(RuntimeError, match="Subtitle file not found"):
        convert_subtitle_to_webvtt("/nonexistent/sub.ass")


def test_webvtt_success(tmp_path):
    """Happy path: converts subtitle to WebVTT."""
    from services.video_player import convert_subtitle_to_webvtt

    sub = tmp_path / "sub.ass"
    sub.write_text("dummy subtitle content")
    out = str(tmp_path / "sub.vtt")

    def fake_run(cmd, **kwargs):
        with open(out, "w") as f:
            f.write("WEBVTT\n\n")
        return MagicMock(returncode=0)

    with patch("services.video_player.subprocess.run", side_effect=fake_run):
        result = convert_subtitle_to_webvtt(str(sub), out)
    assert result == out


def test_webvtt_timeout(tmp_path):
    """FFmpeg timeout raises RuntimeError."""
    from services.video_player import convert_subtitle_to_webvtt

    sub = tmp_path / "sub.ass"
    sub.write_text("dummy")

    with (
        patch(
            "services.video_player.subprocess.run",
            side_effect=subprocess.TimeoutExpired("ffmpeg", 30),
        ),
        pytest.raises(RuntimeError, match="timed out"),
    ):
        convert_subtitle_to_webvtt(str(sub), str(tmp_path / "out.vtt"))


# ---------------------------------------------------------------------------
# embed_subtitle_in_video
# ---------------------------------------------------------------------------


def test_embed_video_not_found(tmp_path):
    """Raise RuntimeError when video does not exist."""
    from services.video_player import embed_subtitle_in_video

    sub = tmp_path / "sub.ass"
    sub.write_text("dummy")

    with pytest.raises(RuntimeError, match="Video file not found"):
        embed_subtitle_in_video("/nonexistent/video.mkv", str(sub), "/out.mkv")


def test_embed_subtitle_not_found(tmp_path):
    """Raise RuntimeError when subtitle does not exist."""
    from services.video_player import embed_subtitle_in_video

    video = tmp_path / "video.mkv"
    video.write_bytes(b"\x00" * 100)

    with pytest.raises(RuntimeError, match="Subtitle file not found"):
        embed_subtitle_in_video(str(video), "/nonexistent/sub.ass", "/out.mkv")


def test_embed_unsupported_format(tmp_path):
    """Raise RuntimeError for unsupported subtitle format."""
    from services.video_player import embed_subtitle_in_video

    video = tmp_path / "video.mkv"
    video.write_bytes(b"\x00" * 100)
    sub = tmp_path / "sub.vtt"
    sub.write_text("WEBVTT")

    with pytest.raises(RuntimeError, match="Unsupported subtitle format"):
        embed_subtitle_in_video(str(video), str(sub), str(tmp_path / "out.mkv"))


def test_embed_success_ass(tmp_path):
    """Happy path: embed ASS subtitle."""
    from services.video_player import embed_subtitle_in_video

    video = tmp_path / "video.mkv"
    video.write_bytes(b"\x00" * 100)
    sub = tmp_path / "sub.ass"
    sub.write_text("dummy ASS")
    out = str(tmp_path / "out.mkv")

    def fake_run(cmd, **kwargs):
        with open(out, "wb") as f:
            f.write(b"\x00" * 100)
        return MagicMock(returncode=0)

    with patch("services.video_player.subprocess.run", side_effect=fake_run):
        result = embed_subtitle_in_video(str(video), str(sub), out)
    assert result == out


def test_embed_success_srt(tmp_path):
    """Happy path: embed SRT subtitle uses subrip codec."""
    from services.video_player import embed_subtitle_in_video

    video = tmp_path / "video.mkv"
    video.write_bytes(b"\x00" * 100)
    sub = tmp_path / "sub.srt"
    sub.write_text("1\n00:00:01,000 --> 00:00:03,000\nHello\n")
    out = str(tmp_path / "out.mkv")

    called_cmd = []

    def fake_run(cmd, **kwargs):
        called_cmd.extend(cmd)
        with open(out, "wb") as f:
            f.write(b"\x00" * 100)
        return MagicMock(returncode=0)

    with patch("services.video_player.subprocess.run", side_effect=fake_run):
        embed_subtitle_in_video(str(video), str(sub), out)
    assert "subrip" in called_cmd


def test_embed_ffmpeg_not_found(tmp_path):
    """Missing ffmpeg raises RuntimeError."""
    from services.video_player import embed_subtitle_in_video

    video = tmp_path / "video.mkv"
    video.write_bytes(b"\x00" * 100)
    sub = tmp_path / "sub.ass"
    sub.write_text("dummy")

    with (
        patch("services.video_player.subprocess.run", side_effect=FileNotFoundError),
        pytest.raises(RuntimeError, match="ffmpeg not found"),
    ):
        embed_subtitle_in_video(str(video), str(sub), str(tmp_path / "out.mkv"))
