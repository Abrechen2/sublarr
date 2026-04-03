"""Unit tests for archive_utils — ZIP extraction with security checks."""

import io
import zipfile

import pytest

from archive_utils import _MAX_ARCHIVE_BYTES, extract_subtitles_from_zip


def _make_zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


class TestValidExtraction:
    def test_valid_zip_extracts_subtitle(self):
        content = b"Hello, this is a subtitle."
        data = _make_zip({"subtitle.srt": content})
        results = extract_subtitles_from_zip(data)
        assert len(results) == 1
        name, body = results[0]
        assert name == "subtitle.srt"
        assert b"Hello" in body

    def test_valid_zip_filters_non_subtitle(self):
        data = _make_zip(
            {
                "subtitle.srt": b"1\n00:00:01,000 --> 00:00:03,000\nHello\n",
                "readme.txt": b"this is not a subtitle",
                "video.mkv": b"\x1a\x45\xdf\xa3",
            }
        )
        results = extract_subtitles_from_zip(data)
        names = [name for name, _ in results]
        assert names == ["subtitle.srt"]


class TestSizeProtection:
    def test_archive_too_large_raises(self):
        oversized = b"x" * (_MAX_ARCHIVE_BYTES + 1)
        with pytest.raises(ValueError, match="Archive too large"):
            extract_subtitles_from_zip(oversized)

    def test_zip_bomb_ratio_raises(self):
        # 500 KB of zeros compresses far beyond 100:1 ratio
        zeros = b"\x00" * (500 * 1024)
        data = _make_zip({"bomb.srt": zeros})
        with pytest.raises(ValueError, match="ZIP bomb"):
            extract_subtitles_from_zip(data)


class TestZipSlip:
    def test_zip_slip_path_stripped(self):
        data = _make_zip({"../../../etc/passwd.srt": b"fake sub content"})
        results = extract_subtitles_from_zip(data)
        if results:
            name, _ = results[0]
            assert "/" not in name
            assert "\\" not in name
            assert name == "passwd.srt"


class TestMalformedInput:
    def test_bad_zip_returns_empty(self):
        results = extract_subtitles_from_zip(b"not a zip")
        assert results == []

    def test_empty_zip_returns_empty(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w"):
            pass  # empty archive
        data = buf.getvalue()
        results = extract_subtitles_from_zip(data)
        assert results == []
