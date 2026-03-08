"""Security regression tests for download security and subtitle sanitization.

Tests three areas:
- TestArchiveUtils: ZIP bomb, oversized archives, ZIP Slip, RAR, filtering
- TestSubtitleSanitizer: size limits, ASS sanitization, SRT/VTT HTML stripping
- TestProviderArchiveConsolidation: inline extraction removed from providers
"""

import io
import os
import sys
import zipfile
from unittest.mock import MagicMock, patch

import pytest

# Ensure backend root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from archive_utils import (
    _MAX_ARCHIVE_BYTES,
    _MAX_COMPRESSION_RATIO,
    _MAX_EXTRACTED_BYTES,
    extract_subtitles_from_rar,
    extract_subtitles_from_zip,
)
from providers.base import SubtitleFormat
from subtitle_sanitizer import (
    _MAX_SUBTITLE_BYTES,
    sanitize_ass_content,
    sanitize_srt_vtt_content,
    sanitize_subtitle,
    validate_content_type,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_zip(*entries: tuple[str, bytes]) -> bytes:
    """Create an in-memory ZIP containing the given (name, content) entries."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in entries:
            zf.writestr(name, content)
    return buf.getvalue()


def _mock_zip_infolist(file_size: int, compress_size: int, filename: str = "test.srt"):
    """Return a mock ZipFile context manager with custom infolist values."""
    info = MagicMock()
    info.filename = filename
    info.file_size = file_size
    info.compress_size = compress_size

    mock_zf = MagicMock()
    mock_zf.__enter__ = MagicMock(return_value=mock_zf)
    mock_zf.__exit__ = MagicMock(return_value=False)
    mock_zf.infolist.return_value = [info]
    return mock_zf


_VALID_SRT = b"1\n00:00:01,000 --> 00:00:02,000\nHello World\n\n"

_VALID_ASS = (
    b"[Script Info]\n"
    b"ScriptType: v4.00+\n"
    b"Title: Test\n\n"
    b"[V4+ Styles]\n"
    b"Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour,"
    b" OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut,"
    b" ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow,"
    b" Alignment, MarginL, MarginR, MarginV, Encoding\n"
    b"Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,"
    b"&H00000000,0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1\n\n"
    b"[Events]\n"
    b"Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    b"Dialogue: 0,0:00:01.00,0:00:05.00,Default,,0,0,0,,Hello World!\n"
)


# ---------------------------------------------------------------------------
# TestArchiveUtils
# ---------------------------------------------------------------------------


class TestArchiveUtils:
    def test_zip_bomb_rejected(self):
        """ZIP claiming uncompressed size > _MAX_EXTRACTED_BYTES should raise ValueError."""
        zip_bytes = _make_zip(("test.srt", _VALID_SRT))

        with patch("archive_utils.zipfile.ZipFile") as mock_zip_cls:
            mock_zip_cls.return_value = _mock_zip_infolist(
                file_size=_MAX_EXTRACTED_BYTES + 1_000_000,
                compress_size=200,
            )
            with pytest.raises(ValueError, match="too large"):
                extract_subtitles_from_zip(zip_bytes)

    def test_zip_bomb_ratio_rejected(self):
        """ZIP with compression ratio exceeding _MAX_COMPRESSION_RATIO should raise ValueError."""
        zip_bytes = _make_zip(("test.srt", _VALID_SRT))

        with patch("archive_utils.zipfile.ZipFile") as mock_zip_cls:
            # compress_size=1, file_size=(_MAX_COMPRESSION_RATIO+100) → ratio > limit
            mock_zip_cls.return_value = _mock_zip_infolist(
                file_size=_MAX_COMPRESSION_RATIO + 100,
                compress_size=1,
            )
            with pytest.raises(ValueError, match="bomb|ratio"):
                extract_subtitles_from_zip(zip_bytes)

    def test_oversized_archive_rejected(self):
        """Archive raw bytes > _MAX_ARCHIVE_BYTES should raise ValueError before opening."""
        oversized = b"PK\x03\x04" + b"\x00" * (_MAX_ARCHIVE_BYTES + 1)
        with pytest.raises(ValueError, match="too large"):
            extract_subtitles_from_zip(oversized)

    def test_zip_slip_member_stripped(self):
        """Members with ../../ path traversal are basename-stripped, not path-traversed."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            info = zipfile.ZipInfo("../../evil.srt")
            zf.writestr(info, _VALID_SRT)
        entries = extract_subtitles_from_zip(buf.getvalue())
        assert len(entries) == 1
        assert entries[0][0] == "evil.srt"

    def test_rar_extraction_basic(self):
        """extract_subtitles_from_rar returns (name, bytes) tuples for subtitle files."""
        mock_info = MagicMock()
        mock_info.filename = "show.srt"

        mock_rf = MagicMock()
        mock_rf.__enter__ = lambda s: s
        mock_rf.__exit__ = MagicMock(return_value=False)
        mock_rf.infolist.return_value = [mock_info]
        mock_rf.read.return_value = _VALID_SRT

        mock_rarfile = MagicMock()
        mock_rarfile.RarFile.return_value = mock_rf

        with patch.dict("sys.modules", {"rarfile": mock_rarfile}):
            entries = extract_subtitles_from_rar(b"\x00" * 100)

        assert entries == [("show.srt", _VALID_SRT)]

    def test_non_subtitle_filtered(self):
        """Files with non-subtitle extensions are excluded from extraction results."""
        zip_bytes = _make_zip(
            ("malware.exe", b"\x4d\x5a\x90\x00"),  # PE header
            ("subtitles.srt", _VALID_SRT),
        )
        entries = extract_subtitles_from_zip(zip_bytes)
        assert len(entries) == 1
        assert entries[0][0] == "subtitles.srt"

    def test_bad_zip_returns_empty(self):
        """Corrupted ZIP data should be caught and return an empty list."""
        result = extract_subtitles_from_zip(b"Not a ZIP at all!!")
        assert result == []


# ---------------------------------------------------------------------------
# TestSubtitleSanitizer
# ---------------------------------------------------------------------------


class TestSubtitleSanitizer:
    def test_size_limit_enforced(self):
        """Content larger than _MAX_SUBTITLE_BYTES should raise ValueError."""
        big = b"\x00" * (_MAX_SUBTITLE_BYTES + 1)
        with pytest.raises(ValueError, match="too large"):
            sanitize_subtitle(big, SubtitleFormat.SRT)

    def test_ass_lua_stripped(self):
        """pysubs2 re-serialization strips non-standard ASS sections."""
        ass_with_extras = _VALID_ASS.decode() + "\n[Custom Script]\nsome_lua_here()\n"
        result = sanitize_ass_content(ass_with_extras.encode())
        assert b"Custom Script" not in result
        assert b"some_lua_here" not in result
        assert b"Hello World" in result

    def test_ass_drawing_mode_stripped(self):
        """ASS drawing-mode blocks ({\\p1}...{\\p0}) should be removed."""
        drawing_ass = (
            _VALID_ASS.decode()
            .replace(
                "Hello World!",
                r"{\p1}m 0 0 l 100 0 100 100 0 100{\p0}",
            )
            .encode()
        )
        result = sanitize_ass_content(drawing_ass)
        assert b"\\p1" not in result
        assert b"\\p0" not in result
        assert b"m 0 0 l 100" not in result

    def test_ass_valid_content_preserved(self):
        """Normal ASS dialogue, formatting, and positions should be preserved."""
        formatted = (
            _VALID_ASS.decode()
            .replace("Hello World!", r"{\i1}Hello{\i0} {\b1}World{\b0}!")
            .encode()
        )
        result = sanitize_ass_content(formatted)
        assert b"Hello" in result
        assert b"World" in result
        assert b"[Script Info]" in result
        assert b"[Events]" in result

    def test_srt_html_stripped(self):
        """<script> tags and their content should be stripped from SRT."""
        xss_srt = (
            b"1\n00:00:01,000 --> 00:00:02,000\n"
            b"<script>alert('xss')</script>Hello<script>alert(2)</script>\n\n"
        )
        result = sanitize_srt_vtt_content(xss_srt)
        assert b"<script>" not in result
        assert b"alert" not in result
        assert b"Hello" in result

    def test_srt_allowed_tags_preserved(self):
        """<i>, <b>, <u> tags should survive SRT sanitization."""
        formatted_srt = (
            b"1\n00:00:01,000 --> 00:00:02,000\n"
            b"<i>Italic</i> and <b>Bold</b> and <u>Underlined</u>\n\n"
        )
        result = sanitize_srt_vtt_content(formatted_srt)
        assert b"<i>" in result
        assert b"<b>" in result
        assert b"<u>" in result

    def test_srt_event_handlers_stripped(self):
        """Event handler attributes should be removed but the tag itself survives."""
        srt_with_handler = (
            b'1\n00:00:01,000 --> 00:00:02,000\n<b onmouseover="malicious()">Click me</b>\n\n'
        )
        result = sanitize_srt_vtt_content(srt_with_handler)
        assert b"onmouseover" not in result
        assert b"<b>" in result
        assert b"Click me" in result

    def test_content_type_ass_validated(self):
        """Content not starting with [Script Info] fails ASS content-type check."""
        assert validate_content_type(b"Not ASS content", SubtitleFormat.ASS) is False
        assert (
            validate_content_type(b"[Script Info]\nScriptType: v4.00+", SubtitleFormat.ASS) is True
        )

    def test_content_type_srt_validated(self):
        """Content not starting with a sequence digit fails SRT content-type check."""
        assert validate_content_type(b"Not SRT", SubtitleFormat.SRT) is False
        assert validate_content_type(_VALID_SRT, SubtitleFormat.SRT) is True

    def test_unknown_format_passthrough(self):
        """UNKNOWN format should pass through sanitize_subtitle unchanged."""
        content = b"arbitrary content"
        result = sanitize_subtitle(content, SubtitleFormat.UNKNOWN)
        assert result == content


# ---------------------------------------------------------------------------
# TestProviderArchiveConsolidation
# ---------------------------------------------------------------------------

_PROVIDERS_WITH_INLINE_ZIP = [
    "providers.jimaku",
    "providers.subdl",
    "providers.podnapisi",
    "providers.titrari",
    "providers.legendasdivx",
    "providers.tvsubtitles",
    "providers.animetosho",
    "providers.kitsunekko",
    "providers.napisy24",
    "providers.subscene",
    "providers.turkcealtyazi",
]


class TestProviderArchiveConsolidation:
    """Verify providers use archive_utils instead of inline ZIP extraction."""

    @pytest.mark.parametrize("module_name", _PROVIDERS_WITH_INLINE_ZIP)
    def test_no_inline_extract_from_zip(self, module_name):
        """Each provider should not have a module-level _extract_from_zip function."""
        import importlib

        module = importlib.import_module(module_name)
        assert not hasattr(module, "_extract_from_zip"), (
            f"{module_name} still has an inline _extract_from_zip — "
            "consolidation to archive_utils may be incomplete"
        )

    @pytest.mark.parametrize("module_name", ["providers.titrari", "providers.legendasdivx"])
    def test_no_inline_extract_from_archive(self, module_name):
        """Titrari and LegendasDivx should not have _extract_subtitle_from_archive."""
        import importlib

        module = importlib.import_module(module_name)
        assert not hasattr(module, "_extract_subtitle_from_archive"), (
            f"{module_name} still has inline _extract_subtitle_from_archive"
        )

    def test_subdl_calls_archive_utils(self):
        """SubDL download() should delegate ZIP extraction to extract_subtitles_from_zip."""
        from providers.base import SubtitleFormat, SubtitleResult
        from providers.subdl import SubDLProvider

        zip_bytes = _make_zip(("test.srt", _VALID_SRT))
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = zip_bytes

        provider = SubDLProvider(api_key="test")
        provider.session = MagicMock()
        provider.session.get.return_value = mock_resp

        result = SubtitleResult(
            provider_name="subdl",
            subtitle_id="123",
            language="en",
            format=SubtitleFormat.SRT,
            filename="test.srt",
            download_url="http://test.com/123.zip",
            provider_data={"sd_id": "123", "query_episode": 1, "query_season": 1},
        )

        with patch("providers.subdl.extract_subtitles_from_zip") as mock_extract:
            mock_extract.return_value = [("test.srt", _VALID_SRT)]
            provider.download(result)
            mock_extract.assert_called_once()

    def test_podnapisi_calls_archive_utils(self):
        """Podnapisi download() should delegate ZIP extraction to extract_subtitles_from_zip."""
        from providers.base import SubtitleFormat, SubtitleResult
        from providers.podnapisi import PodnapisiProvider

        zip_bytes = _make_zip(("test.srt", _VALID_SRT))
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = zip_bytes

        provider = PodnapisiProvider()
        provider.session = MagicMock()
        provider.session.get.return_value = mock_resp

        result = SubtitleResult(
            provider_name="podnapisi",
            subtitle_id="pid-42",
            language="en",
            format=SubtitleFormat.SRT,
            filename="test.srt",
            download_url="https://www.podnapisi.net/subtitles/pid-42/download",
            provider_data={"pid": "pid-42"},
        )

        with patch("providers.podnapisi.extract_subtitles_from_zip") as mock_extract:
            mock_extract.return_value = [("test.srt", _VALID_SRT)]
            provider.download(result)
            mock_extract.assert_called_once()
