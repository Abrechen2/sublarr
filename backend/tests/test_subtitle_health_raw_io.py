import os
import subprocess

import pytest

from services.subtitle_health import raw_io


def test_mov_text_not_treated_as_text_codec():
    """FIX 3: mov_text removed from _COPY_EXT — -c:s copy yields binary TTXT."""
    assert raw_io.is_text_codec("mov_text") is False
    assert raw_io.is_text_codec("subrip") is True


FIX = os.path.join(os.path.dirname(__file__), "fixtures", "subtitle_health")


def test_md5_of_bytes_is_stable():
    assert raw_io.md5_bytes(b"hello") == raw_io.md5_bytes(b"hello")
    assert raw_io.md5_bytes(b"a") != raw_io.md5_bytes(b"b")


def test_read_sidecar_returns_raw_bytes():
    data = raw_io.read_sidecar(os.path.join(FIX, "escape_leak.srt"))
    assert b"\\N" in data  # literal backslash-N preserved, not interpreted


def _have_ffmpeg():
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _have_ffmpeg(), reason="ffmpeg not installed")
def test_extract_track_raw_preserves_literal_escapes(tmp_path):
    """Regression guard: the raw extractor must NOT convert \\N to newlines.

    We embed an ASS subtitle (which natively uses \\N as a hard line-break
    override) into an MKV using ``-c:s copy`` so the raw ASS payload is stored
    verbatim.  ``extract_track_raw`` must hand back that same verbatim payload —
    proving it uses ``-c:s copy`` and not the SRT encoder (which collapses
    ``\\N`` into a real newline, hiding the defect).
    """
    mkv = tmp_path / "tiny.mkv"
    # Build MKV: embed escape_leak.ass with -c:s copy so \N is stored verbatim.
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=64x64:d=1",
            "-i",
            os.path.join(FIX, "escape_leak.ass"),
            "-c:v",
            "libx264",
            "-c:s",
            "copy",
            "-map",
            "0:v",
            "-map",
            "1",
            str(mkv),
        ],
        capture_output=True,
        check=True,
    )
    data = raw_io.extract_track_raw(str(mkv), sub_index=0, codec="ass")
    assert b"\\N" in data
