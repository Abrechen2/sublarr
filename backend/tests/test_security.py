"""Security regression tests for download security and subtitle sanitization.

Tests four areas:
- TestArchiveUtils: ZIP bomb, oversized archives, ZIP Slip, RAR, filtering
- TestSubtitleSanitizer: size limits, ASS sanitization, SRT/VTT HTML stripping
- TestProviderArchiveConsolidation: inline extraction removed from providers
- TestValidateServiceUrl: SSRF protection for config URL fields
- TestSocketIOLogSanitizer: DB error details stripped from WebSocket log events
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
from security_utils import validate_service_url
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


# ---------------------------------------------------------------------------
# TestValidateServiceUrl
# ---------------------------------------------------------------------------


class TestValidateServiceUrl:
    """validate_service_url blocks dangerous schemes and metadata IPs."""

    # --- valid URLs (should be accepted) ---

    @pytest.mark.parametrize(
        "url",
        [
            "http://192.168.178.36:8989",  # Sonarr on LAN
            "http://192.168.178.155:11434",  # Ollama on LAN
            "https://192.168.1.1",  # HTTPS private IP
            "http://10.0.0.5:7878",  # Radarr on 10.x network
            "http://172.16.0.1:8096",  # Jellyfin on 172.16.x
            "http://sonarr.local:8989",  # mDNS hostname
            "https://api.opensubtitles.com",  # External provider
        ],
    )
    def test_valid_urls_accepted(self, url):
        ok, reason = validate_service_url(url)
        assert ok is True, f"Expected {url!r} to be accepted, got: {reason}"

    # --- dangerous schemes (must be rejected) ---

    @pytest.mark.parametrize(
        "url",
        [
            "file:///etc/passwd",
            "ftp://192.168.1.1/data",
            "dict://localhost:2628/d:password",
            "gopher://evil.com/1%0d%0aFoo",
            "ldap://127.0.0.1:389/",
            "sftp://host/path",
        ],
    )
    def test_dangerous_schemes_rejected(self, url):
        ok, reason = validate_service_url(url)
        assert ok is False
        assert "scheme" in (reason or "").lower()

    # --- cloud metadata endpoints (must be rejected) ---

    @pytest.mark.parametrize(
        "url",
        [
            "http://169.254.169.254/latest/meta-data/",  # AWS / Azure / GCP
            "http://169.254.169.254/",
            "http://100.100.100.200/latest/meta-data/",  # Alibaba Cloud
            "http://metadata.google.internal/computeMetadata/",  # GCP named endpoint
            "http://metadata.goog/",
        ],
    )
    def test_metadata_endpoints_rejected(self, url):
        ok, reason = validate_service_url(url)
        assert ok is False, f"Expected {url!r} to be rejected"

    # --- edge cases ---

    def test_empty_string_rejected(self):
        ok, reason = validate_service_url("")
        assert ok is False

    def test_no_hostname_rejected(self):
        ok, reason = validate_service_url("http:///no-host")
        assert ok is False

    def test_zero_host_rejected(self):
        ok, reason = validate_service_url("http://0.0.0.0:8989")
        assert ok is False

    def test_link_local_ipv6_rejected(self):
        ok, reason = validate_service_url("http://[fe80::1]/path")
        assert ok is False

    def test_trailing_slash_accepted(self):
        ok, _ = validate_service_url("http://192.168.178.36:8989/")
        assert ok is True


# ---------------------------------------------------------------------------
# TestSocketIOLogSanitizer
# ---------------------------------------------------------------------------


class TestSocketIOLogSanitizer:
    """SocketIOLogHandler._sanitize strips DB-internal error details."""

    def _get_sanitizer(self):
        """Import SocketIOLogHandler without starting a full Flask app."""
        import importlib
        import sys

        # app.py is at backend root — already on path from sys.path.insert above
        app_module = importlib.import_module("app")
        return app_module.SocketIOLogHandler

    def test_psycopg2_error_stripped(self):
        Handler = self._get_sanitizer()
        raw = "[ERROR] Unhandled exception: (psycopg2.errors.UndefinedColumn) column glossary_entries.term_type does not exist"
        result = Handler._sanitize(raw)
        assert "term_type" not in result
        assert "glossary_entries" not in result
        assert "Database error" in result

    def test_sqlalchemy_error_stripped(self):
        Handler = self._get_sanitizer()
        raw = "[ERROR] db: (sqlalchemy.exc.OperationalError) no such table: subtitle_jobs"
        result = Handler._sanitize(raw)
        assert "subtitle_jobs" not in result
        assert "Database error" in result

    def test_undefined_function_stripped(self):
        Handler = self._get_sanitizer()
        raw = "[ERROR] error_handler: (psycopg2.errors.UndefinedFunction) function date(unknown, unknown) does not exist"
        result = Handler._sanitize(raw)
        assert "function date" not in result
        assert "Database error" in result

    def test_normal_log_unchanged(self):
        Handler = self._get_sanitizer()
        normal = "[INFO] sonarr_client: Connected to Sonarr v4.0"
        assert Handler._sanitize(normal) == normal

    def test_warning_log_unchanged(self):
        Handler = self._get_sanitizer()
        warning = "[WARNING] auth: Invalid API key from 192.168.178.50"
        assert Handler._sanitize(warning) == warning

    def test_prefix_preserved_on_db_error(self):
        """Timestamp/level prefix before ']' is kept; only the DB detail is replaced."""
        Handler = self._get_sanitizer()
        raw = "2026-03-18 17:00:00 [ERROR] handler: (psycopg2.errors.UndefinedColumn) col x does not exist"
        result = Handler._sanitize(raw)
        assert "Database error" in result
        assert "col x" not in result


# ---------------------------------------------------------------------------
# TestExtensionUrlValidation (F-13a regression)
# ---------------------------------------------------------------------------


class TestExtensionUrlValidation:
    """PUT /config must validate dot-notation URL extension keys (F-13a).

    Prior to this fix, keys like 'whisper.subgen.url' bypassed SSRF validation
    because they were treated as opaque extension keys.
    """

    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        import os
        import sys

        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        monkeypatch.setenv("SUBLARR_DB_PATH", str(tmp_path / "test.db"))
        monkeypatch.setenv("SUBLARR_API_KEY", "")
        monkeypatch.setenv("SUBLARR_LOG_LEVEL", "ERROR")
        monkeypatch.setenv("SUBLARR_PLUGINS_DIR", str(tmp_path / "plugins"))
        monkeypatch.setenv("SUBLARR_MEDIA_PATH", str(tmp_path))

        from app import create_app
        from config import reload_settings
        from db import init_db

        reload_settings()
        (tmp_path / "plugins").mkdir(exist_ok=True)
        app = create_app()
        init_db()
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c

    @pytest.mark.parametrize(
        "key",
        ["whisper.subgen.url", "whisper.faster_whisper.url", "translation.backend_url"],
    )
    def test_dangerous_scheme_rejected_for_extension_url_keys(self, client, key):
        """Dot-notation URL keys must reject dangerous schemes (e.g. file://)."""
        resp = client.put("/api/v1/config", json={key: "file:///etc/passwd"})
        assert resp.status_code == 400
        data = resp.get_json()
        assert "Invalid URL" in data.get("error", "")

    @pytest.mark.parametrize(
        "key",
        ["whisper.subgen.url", "whisper.faster_whisper.url"],
    )
    def test_metadata_ip_rejected_for_extension_url_keys(self, client, key):
        """Cloud metadata endpoints must also be blocked for extension URL keys."""
        resp = client.put("/api/v1/config", json={key: "http://169.254.169.254/latest"})
        assert resp.status_code == 400

    @pytest.mark.parametrize(
        "key",
        ["whisper.subgen.url", "whisper.faster_whisper.url"],
    )
    def test_valid_lan_url_accepted_for_extension_url_keys(self, client, key):
        """Valid LAN URLs must still be accepted for extension URL keys."""
        resp = client.put("/api/v1/config", json={key: "http://192.168.1.100:9000"})
        # 200 = saved, anything other than 400 means validation passed
        assert resp.status_code != 400 or "Invalid URL" not in resp.get_json().get("error", "")
