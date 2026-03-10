"""Tests for the remux engine and backup cleanup."""

from __future__ import annotations

import os
import tempfile
import time
from unittest.mock import MagicMock, call, patch

import pytest

from remux import RemuxError, _detect_backend, _verify, remove_subtitle_stream
from remux.backup_cleanup import cleanup_old_backups, list_backups

# ---------------------------------------------------------------------------
# _detect_backend
# ---------------------------------------------------------------------------


def test_detect_backend_mkv():
    assert _detect_backend("/movies/film.mkv") == "mkvmerge"


def test_detect_backend_mk3d():
    assert _detect_backend("/movies/film.mk3d") == "mkvmerge"


def test_detect_backend_mp4():
    assert _detect_backend("/movies/film.mp4") == "ffmpeg"


def test_detect_backend_avi():
    assert _detect_backend("/movies/film.avi") == "ffmpeg"


# ---------------------------------------------------------------------------
# _verify — duration / stream count / size checks
# ---------------------------------------------------------------------------


def _make_probe(duration, video=1, audio=1, subtitle=1):
    return {
        "format": {"duration": str(duration)},
        "streams": (
            [{"codec_type": "video"}] * video
            + [{"codec_type": "audio"}] * audio
            + [{"codec_type": "subtitle"}] * subtitle
        ),
    }


def test_verify_passes_clean_remux(tmp_path):
    orig = str(tmp_path / "orig.mkv")
    new = str(tmp_path / "new.mkv")
    # Create dummy files so os.path.getsize works
    with open(orig, "wb") as f:
        f.write(b"x" * 1000)
    with open(new, "wb") as f:
        f.write(b"x" * 900)

    with patch(
        "remux._probe",
        side_effect=[
            _make_probe(3600, subtitle=2),
            _make_probe(3600, subtitle=1),
        ],
    ):
        _verify(orig, new)  # should not raise


def test_verify_fails_duration_mismatch(tmp_path):
    orig = str(tmp_path / "orig.mkv")
    new = str(tmp_path / "new.mkv")
    with open(orig, "wb") as f:
        f.write(b"x" * 1000)
    with open(new, "wb") as f:
        f.write(b"x" * 900)

    with (
        patch(
            "remux._probe",
            side_effect=[
                _make_probe(3600, subtitle=2),
                _make_probe(3605, subtitle=1),  # >2s diff
            ],
        ),
        pytest.raises(RemuxError, match="Duration mismatch"),
    ):
        _verify(orig, new)


def test_verify_fails_video_stream_lost(tmp_path):
    orig = str(tmp_path / "orig.mkv")
    new = str(tmp_path / "new.mkv")
    with open(orig, "wb") as f:
        f.write(b"x" * 1000)
    with open(new, "wb") as f:
        f.write(b"x" * 900)

    with (
        patch(
            "remux._probe",
            side_effect=[
                _make_probe(3600, video=1, subtitle=2),
                _make_probe(3600, video=0, subtitle=1),  # lost video
            ],
        ),
        pytest.raises(RemuxError, match="Video stream count"),
    ):
        _verify(orig, new)


def test_verify_fails_file_too_small(tmp_path):
    orig = str(tmp_path / "orig.mkv")
    new = str(tmp_path / "new.mkv")
    with open(orig, "wb") as f:
        f.write(b"x" * 1000)
    with open(new, "wb") as f:
        f.write(b"x" * 100)  # only 10% of original

    with (
        patch(
            "remux._probe",
            side_effect=[
                _make_probe(3600, subtitle=2),
                _make_probe(3600, subtitle=1),
            ],
        ),
        pytest.raises(RemuxError, match="suspiciously small"),
    ):
        _verify(orig, new)


def test_verify_fails_wrong_subtitle_count(tmp_path):
    orig = str(tmp_path / "orig.mkv")
    new = str(tmp_path / "new.mkv")
    with open(orig, "wb") as f:
        f.write(b"x" * 1000)
    with open(new, "wb") as f:
        f.write(b"x" * 900)

    with (
        patch(
            "remux._probe",
            side_effect=[
                _make_probe(3600, subtitle=2),
                _make_probe(3600, subtitle=2),  # subtitle count unchanged → wrong
            ],
        ),
        pytest.raises(RemuxError, match="subtitle stream count"),
    ):
        _verify(orig, new)


# ---------------------------------------------------------------------------
# remove_subtitle_stream — integration (all subprocesses mocked)
# ---------------------------------------------------------------------------


def test_remove_subtitle_stream_mkv_success(tmp_path):
    video = str(tmp_path / "show.mkv")
    with open(video, "wb") as f:
        f.write(b"x" * 2000)

    with (
        patch("remux._remux_mkvmerge") as mock_remux,
        patch("remux._verify"),
        patch("remux._make_backup", return_value=video + ".bak"),
        patch("remux._detect_backend", return_value="mkvmerge"),
        patch("remux._which", return_value=True),
        patch("os.replace"),
    ):
        bak = remove_subtitle_stream(video, stream_index=2, subtitle_track_index=0)

    assert bak == video + ".bak"
    mock_remux.assert_called_once()


def test_remove_subtitle_stream_ffmpeg_success(tmp_path):
    video = str(tmp_path / "movie.mp4")
    with open(video, "wb") as f:
        f.write(b"x" * 2000)

    with (
        patch("remux._remux_ffmpeg") as mock_remux,
        patch("remux._verify"),
        patch("remux._make_backup", return_value=video + ".bak"),
        patch("remux._detect_backend", return_value="ffmpeg"),
        patch("os.replace"),
    ):
        bak = remove_subtitle_stream(video, stream_index=3, subtitle_track_index=1)

    assert bak == video + ".bak"
    mock_remux.assert_called_once()


def test_remove_subtitle_stream_cleans_temp_on_error(tmp_path):
    video = str(tmp_path / "show.mkv")
    with open(video, "wb") as f:
        f.write(b"x" * 2000)

    with (
        patch("remux._detect_backend", return_value="mkvmerge"),
        patch("remux._remux_mkvmerge", side_effect=RemuxError("mkvmerge crashed")),
        pytest.raises(RemuxError),
    ):
        remove_subtitle_stream(video, stream_index=2, subtitle_track_index=0)

    # temp file must be cleaned up
    tmp_files = [f for f in os.listdir(tmp_path) if f != "show.mkv"]
    assert len(tmp_files) == 0


def test_remove_subtitle_stream_fallback_to_ffmpeg_when_mkvmerge_missing(tmp_path):
    """When mkvmerge is not found, the engine falls back to ffmpeg for MKV files."""
    video = str(tmp_path / "show.mkv")
    with open(video, "wb") as f:
        f.write(b"x" * 2000)

    with (
        patch("remux._detect_backend", return_value="mkvmerge"),
        patch("remux._which", return_value=False),
        patch("remux._remux_ffmpeg") as mock_ffmpeg,
        patch("remux._verify"),
        patch("remux._make_backup", return_value=video + ".bak"),
        patch("os.replace"),
    ):
        bak = remove_subtitle_stream(video, stream_index=2, subtitle_track_index=0)

    assert bak == video + ".bak"
    mock_ffmpeg.assert_called_once()


def test_remove_subtitle_stream_ffmpeg_not_found_raises(tmp_path):
    """When both mkvmerge and ffmpeg are missing, raise RemuxError."""
    video = str(tmp_path / "show.mkv")
    with open(video, "wb") as f:
        f.write(b"x" * 1000)

    with (
        patch("remux._detect_backend", return_value="mkvmerge"),
        patch("remux._which", return_value=False),
        patch("remux._remux_ffmpeg", side_effect=RemuxError("ffmpeg not found")),
        pytest.raises(RemuxError, match="ffmpeg not found"),
    ):
        remove_subtitle_stream(video, stream_index=0, subtitle_track_index=0)


# ---------------------------------------------------------------------------
# backup_cleanup
# ---------------------------------------------------------------------------


def test_list_backups_finds_bak_files(tmp_path):
    (tmp_path / "show.mkv.bak").write_bytes(b"x" * 100)
    (tmp_path / "other.txt").write_bytes(b"y")

    result = list_backups([str(tmp_path)])
    assert len(result) == 1
    assert result[0]["path"].endswith(".bak")
    assert result[0]["size_bytes"] == 100


def test_cleanup_deletes_old_backups(tmp_path):
    bak = tmp_path / "old.mkv.bak"
    bak.write_bytes(b"x" * 100)
    # Set mtime to 10 days ago
    old_time = time.time() - 10 * 86400
    os.utime(str(bak), (old_time, old_time))

    result = cleanup_old_backups([str(tmp_path)], retention_days=7)
    assert len(result["deleted"]) == 1
    assert not bak.exists()


def test_cleanup_keeps_recent_backups(tmp_path):
    bak = tmp_path / "recent.mkv.bak"
    bak.write_bytes(b"x" * 100)
    # mtime = now (very recent)

    result = cleanup_old_backups([str(tmp_path)], retention_days=7)
    assert len(result["deleted"]) == 0
    assert bak.exists()


def test_cleanup_zero_retention_skips_all(tmp_path):
    bak = tmp_path / "old.mkv.bak"
    bak.write_bytes(b"x")
    old_time = time.time() - 30 * 86400
    os.utime(str(bak), (old_time, old_time))

    result = cleanup_old_backups([str(tmp_path)], retention_days=0)
    assert result["deleted"] == []
    assert bak.exists()


def test_cleanup_handles_missing_dir():
    result = cleanup_old_backups(["/nonexistent/path/xyz"], retention_days=7)
    assert result["deleted"] == []
    assert result["errors"] == []


# ---------------------------------------------------------------------------
# _make_backup — trash directory layout
# ---------------------------------------------------------------------------


def test_make_backup_creates_trash_dir(tmp_path):
    from remux import _make_backup

    video = str(tmp_path / "show.mkv")
    trash_root = str(tmp_path / ".sublarr")
    with open(video, "wb") as f:
        f.write(b"x" * 500)

    bak_path = _make_backup(video, use_reflink=False, trash_dir=trash_root)

    assert os.path.exists(bak_path)
    assert ".sublarr" in bak_path or "trash" in bak_path
    assert bak_path.endswith(".bak")


def test_make_backup_fallback_on_permission_error(tmp_path):
    """When trash dir cannot be created, falls back to sibling .bak."""
    from remux import _make_backup

    video = str(tmp_path / "show.mkv")
    with open(video, "wb") as f:
        f.write(b"x" * 100)

    # Simulate os.makedirs failing with a permission error
    with patch("os.makedirs", side_effect=OSError("Permission denied")):
        bak_path = _make_backup(video, use_reflink=False, trash_dir=".sublarr")

    # Fallback: sibling .bak
    assert bak_path == video + ".bak"
    assert os.path.exists(bak_path)
