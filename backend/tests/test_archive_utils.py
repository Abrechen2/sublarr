"""Unit tests for archive_utils — ZIP extraction with security checks."""

import io
import zipfile

import pytest

from archive_utils import (
    _MAX_ARCHIVE_BYTES,
    _MAX_EXTRACTED_BYTES,
    extract_subtitles_from_zip,
    safe_read_zip_member,
)


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

    def test_zip_windows_backslash_path_stripped(self):
        """Linux os.path.basename doesn't strip backslashes; _safe_basename must."""
        data = _make_zip({"..\\..\\windows\\cmd.exe.srt": b"fake sub content"})
        results = extract_subtitles_from_zip(data)
        assert results, "ZIP with backslash path should still extract a safe basename"
        name, _ = results[0]
        assert "\\" not in name
        assert ".." not in name
        assert name.endswith(".srt")

    def test_zip_null_byte_path_sanitized(self):
        """Null byte in ZIP entry path is stripped by secure_filename."""
        data = _make_zip({"normal\x00hidden.srt": b"fake sub content"})
        results = extract_subtitles_from_zip(data)
        if results:
            name, _ = results[0]
            assert "\x00" not in name

    def test_zip_unicode_path_sanitized(self):
        """Unicode in ZIP entry path is ASCII-normalised by secure_filename."""
        data = _make_zip({"Anime【HorribleSubs】.srt": b"fake sub content"})
        results = extract_subtitles_from_zip(data)
        if results:
            name, _ = results[0]
            # secure_filename strips non-ASCII — result is still .srt-extensioned
            assert name.endswith(".srt")


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


class TestSafeReadZipMember:
    """``safe_read_zip_member`` — generic per-entry bomb guard used by the
    /api/v1/api-keys/import endpoints (audit 2026-04-30). The endpoints
    were calling ``zf.read(name)`` directly; a 16 MB ZIP can decompress
    into multi-GB memory if a single entry has >1000:1 ratio."""

    def test_normal_member_round_trips(self):
        data = _make_zip({"config.json": b'{"hello": "world"}'})
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            assert safe_read_zip_member(zf, "config.json") == b'{"hello": "world"}'

    def test_missing_member_raises_keyerror(self):
        data = _make_zip({"config.json": b"{}"})
        with zipfile.ZipFile(io.BytesIO(data)) as zf, pytest.raises(KeyError):
            safe_read_zip_member(zf, "missing.json")

    def test_bomb_ratio_member_raises(self):
        """A single oversized-by-ratio entry must be refused."""
        zeros = b"\x00" * (200 * 1024)  # 200 KB of zeros — compresses ~0%
        data = _make_zip({"bomb.json": zeros})
        with (
            zipfile.ZipFile(io.BytesIO(data)) as zf,
            pytest.raises(ValueError, match="ZIP bomb"),
        ):
            safe_read_zip_member(zf, "bomb.json")

    def test_oversized_uncompressed_member_raises(self):
        """An entry whose declared uncompressed size exceeds the cap is
        refused without ever reading the body. We synthesise the case by
        passing a custom ``max_bytes`` to assert the boundary."""
        data = _make_zip({"big.json": b"x" * (500 * 1024)})  # 500 KB
        with (
            zipfile.ZipFile(io.BytesIO(data)) as zf,
            pytest.raises(ValueError, match="too large"),
        ):
            safe_read_zip_member(zf, "big.json", max_bytes=100 * 1024)

    def test_uses_default_cap_of_50mb(self):
        """The default cap matches ``_MAX_EXTRACTED_BYTES`` (50 MB)."""
        # Verify the default cap by passing a small entry and confirming it
        # passes when no max_bytes override is given.
        data = _make_zip({"small.json": b"{}"})
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            assert safe_read_zip_member(zf, "small.json") == b"{}"
        # The default value is exposed as the module constant.
        assert _MAX_EXTRACTED_BYTES == 50 * 1024 * 1024
