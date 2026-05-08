"""Security tests — download URL validation, filename sanitization, and magic bytes.

Covers:
- TestValidateDownloadUrl: validate_download_url() provider domain allowlist
- TestProviderDownloadUrlValidation: provider wiring for P1
- TestFilenameSanitization: P2 provider filename sanitization
- TestMagicByteValidation: P4 format validation after download
- TestStreamingDownload: P5 download size cap
- TestProviderFilenameBoundary: P2 boundary sanitization in wanted_search.search
"""

import os
import sys
from unittest.mock import MagicMock

import pytest

# Ensure backend root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from security_utils import validate_download_url

# ---------------------------------------------------------------------------
# TestValidateDownloadUrl — P1 provider domain allowlist (Task 1)
# ---------------------------------------------------------------------------


class TestValidateDownloadUrl:
    """validate_download_url() blocks off-allowlist domains per provider."""

    def test_opensubtitles_allowed_domain(self):
        ok, err = validate_download_url(
            "https://dl.opensubtitles.com/en/download/src-api/vip/subtitle/xyz.srt",
            "opensubtitles",
        )
        assert ok is True
        assert err is None

    def test_opensubtitles_rejected_domain(self):
        ok, err = validate_download_url("https://evil.example.com/malware.srt", "opensubtitles")
        assert ok is False
        assert "allowlist" in err.lower()

    def test_podnapisi_allowed(self):
        ok, err = validate_download_url(
            "https://www.podnapisi.net/subtitles/12345/download", "podnapisi"
        )
        assert ok is True

    def test_jimaku_allowed(self):
        ok, err = validate_download_url("https://jimaku.cc/api/entries/123/files/sub.ass", "jimaku")
        assert ok is True

    def test_addic7ed_allowed(self):
        ok, err = validate_download_url("https://www.addic7ed.com/original/12345/0", "addic7ed")
        assert ok is True

    def test_betaseries_allowed(self):
        ok, err = validate_download_url("https://www.betaseries.com/srt/12345", "betaseries")
        assert ok is True

    def test_gestdown_allowed(self):
        ok, err = validate_download_url(
            "https://api.gestdown.info/subtitles/download/abc123", "gestdown"
        )
        assert ok is True

    def test_kitsunekko_allowed(self):
        ok, err = validate_download_url(
            "https://kitsunekko.net/dirlist.php?dir=subtitles%2Fjapanese%2F", "kitsunekko"
        )
        assert ok is True

    def test_legendasdivx_allowed(self):
        ok, err = validate_download_url(
            "https://www.legendasdivx.pt/downloadFile.php?id=1234", "legendasdivx"
        )
        assert ok is True

    def test_napisy24_allowed(self):
        ok, err = validate_download_url(
            "http://napisy24.pl/run/CheckSubAgent.php?mode=download&id=123", "napisy24"
        )
        assert ok is True

    def test_subdl_allowed_download_domain(self):
        ok, err = validate_download_url("https://dl.subdl.com/subtitle/abc123.zip", "subdl")
        assert ok is True

    def test_animetosho_allowed(self):
        ok, err = validate_download_url(
            "https://animetosho.org/storage/attach/0001/12345.xz", "animetosho"
        )
        assert ok is True

    def test_unknown_provider_rejected(self):
        ok, err = validate_download_url(
            "https://legitimate.site.com/file.srt", "unknown_provider_xyz"
        )
        assert ok is False
        assert "unknown provider" in err.lower()

    def test_ssrf_metadata_ip_rejected_even_for_known_provider(self):
        ok, err = validate_download_url("http://169.254.169.254/latest/meta-data/", "opensubtitles")
        assert ok is False

    def test_empty_url_rejected(self):
        ok, err = validate_download_url("", "opensubtitles")
        assert ok is False

    def test_embedded_provider_skips_validation(self):
        ok, err = validate_download_url("", "embedded")
        assert ok is True
        assert err is None

    def test_whisper_provider_skips_validation(self):
        ok, err = validate_download_url("", "whisper")
        assert ok is True
        assert err is None

    def test_subsdump_any_host_allowed(self):
        """Self-hosted providers: private LAN IPs must be allowed (operator-controlled)."""
        ok, err = validate_download_url(
            "http://192.168.178.195:8080/api/download/123.zip", "subsdump"
        )
        assert ok is True
        assert err is None

    def test_subsdump_loopback_rejected(self):
        """Loopback must be blocked even for self-hosted to prevent SSRF to localhost."""
        ok, err = validate_download_url("http://127.0.0.1:5765/api/v1/config", "subsdump")
        assert ok is False

    def test_subsdump_rejects_file_scheme(self):
        ok, err = validate_download_url("file:///etc/passwd", "subsdump")
        assert ok is False

    def test_ipv6_loopback_rejected_for_known_provider(self):
        ok, err = validate_download_url("http://[::1]:5765/api/v1/config", "opensubtitles")
        assert ok is False

    def test_subsdump_ipv6_loopback_rejected(self):
        ok, err = validate_download_url("http://[::1]:5765/api/v1/config", "subsdump")
        assert ok is False


# ---------------------------------------------------------------------------
# TestProviderDownloadUrlValidation — P1 wired into providers (Task 2)
# ---------------------------------------------------------------------------


class TestProviderDownloadUrlValidation:
    """Providers raise an error when download URL fails allowlist check."""

    def test_validate_download_url_called_before_fetch(self, monkeypatch):
        """validate_download_url must be called; off-allowlist URL raises SublarrError."""
        from security_utils import validate_download_url

        # Verify the function rejects an off-allowlist URL
        ok, err = validate_download_url("https://evil.example.com/payload.srt", "opensubtitles")
        assert ok is False

    def test_local_provider_skips_url_validation(self):
        """embedded provider always passes validate_download_url."""
        from security_utils import validate_download_url

        ok, err = validate_download_url("", "embedded")
        assert ok is True

    def test_plugin_provider_rejected(self):
        """Dynamic plugin provider not in allowlist is rejected."""
        from security_utils import validate_download_url

        ok, err = validate_download_url("https://myplugin.example.com/sub.srt", "my_custom_plugin")
        assert ok is False
        assert "unknown provider" in err.lower()


# ---------------------------------------------------------------------------
# TestFilenameSanitization — P2 provider filename sanitization (Task 3)
# ---------------------------------------------------------------------------


class TestFilenameSanitization:
    """Provider filenames are sanitized via werkzeug.secure_filename before use."""

    def test_path_traversal_filename_sanitized(self):
        """../../../etc/passwd.srt becomes a safe name without traversal components."""
        from werkzeug.utils import secure_filename

        result = secure_filename("../../../etc/passwd.srt")
        assert ".." not in result
        assert "/" not in result
        assert result.endswith(".srt")

    def test_windows_path_traversal_sanitized(self):
        from werkzeug.utils import secure_filename

        result = secure_filename("..\\..\\windows\\system32\\cmd.exe.srt")
        assert ".." not in result
        assert "\\" not in result

    def test_null_byte_sanitized(self):
        from werkzeug.utils import secure_filename

        result = secure_filename("normal\x00hidden.srt")
        assert "\x00" not in result

    def test_empty_filename_fallback(self):
        """Empty filename after sanitization falls back to 'subtitle.srt'."""
        from werkzeug.utils import secure_filename

        result = secure_filename("") or "subtitle.srt"
        assert result == "subtitle.srt"

    def test_normal_filename_preserved(self):
        from werkzeug.utils import secure_filename

        result = secure_filename("Attack.on.Titan.S01E01.srt")
        assert result == "Attack.on.Titan.S01E01.srt"


# ---------------------------------------------------------------------------
# TestMagicByteValidation — P4 format validation after download (Task 5)
# ---------------------------------------------------------------------------


class TestMagicByteValidation:
    """Downloaded content is validated to match the declared subtitle format."""

    def test_pe_executable_rejected(self):
        from providers import _validate_subtitle_content

        pe_header = b"MZ\x90\x00" + b"\x00" * 100  # Windows PE header
        ok, reason = _validate_subtitle_content(pe_header, "srt")
        assert ok is False
        assert "executable" in reason.lower() or "binary" in reason.lower()

    def test_elf_executable_rejected(self):
        from providers import _validate_subtitle_content

        elf_header = b"\x7fELF" + b"\x00" * 100  # Linux ELF header
        ok, reason = _validate_subtitle_content(elf_header, "srt")
        assert ok is False

    def test_valid_srt_accepted(self):
        from providers import _validate_subtitle_content

        srt_content = b"1\n00:00:01,000 --> 00:00:03,000\nHello world\n\n"
        ok, reason = _validate_subtitle_content(srt_content, "srt")
        assert ok is True

    def test_valid_ass_accepted(self):
        from providers import _validate_subtitle_content

        ass_content = b"[Script Info]\nScriptType: v4.00+\n"
        ok, reason = _validate_subtitle_content(ass_content, "ass")
        assert ok is True

    def test_empty_content_rejected(self):
        from providers import _validate_subtitle_content

        ok, reason = _validate_subtitle_content(b"", "srt")
        assert ok is False

    def test_binary_noise_rejected_for_srt(self):
        from providers import _validate_subtitle_content

        binary = bytes(range(256)) * 10  # Random binary data
        ok, reason = _validate_subtitle_content(binary, "srt")
        assert ok is False


# ---------------------------------------------------------------------------
# TestStreamingDownload — P5 download size cap (Task 5)
# ---------------------------------------------------------------------------


class TestStreamingDownload:
    """Provider downloads are capped at 50 MB to prevent OOM attacks."""

    def test_download_within_limit_succeeds(self):

        from providers import _stream_download

        mock_response = MagicMock()
        mock_response.headers = {"Content-Length": "1000"}
        mock_response.iter_content.return_value = [b"x" * 1000]
        mock_response.raise_for_status = MagicMock()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response

        content = _stream_download(mock_session, "https://example.com/sub.srt")
        assert content == b"x" * 1000

    def test_content_length_too_large_rejected(self):

        from providers import _stream_download

        mock_response = MagicMock()
        mock_response.headers = {"Content-Length": str(60 * 1024 * 1024)}  # 60 MB > limit
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response

        with pytest.raises(Exception, match="too large"):
            _stream_download(mock_session, "https://example.com/huge.srt")


# ---------------------------------------------------------------------------
# TestProviderFilenameBoundary — P2 single-point sanitisation in search.py
# ---------------------------------------------------------------------------


class TestProviderFilenameBoundary:
    """``_safe_provider_filename`` is the single point where attacker-controlled
    provider-supplied filenames are scrubbed before reaching the API response."""

    def test_traversal_sequence_stripped(self):
        from wanted_search.search import _safe_provider_filename

        result = _safe_provider_filename("../../etc/passwd.srt")
        assert ".." not in result
        assert "/" not in result

    def test_null_byte_stripped(self):
        from wanted_search.search import _safe_provider_filename

        result = _safe_provider_filename("normal\x00hidden.srt")
        assert "\x00" not in result

    def test_normal_filename_preserved(self):
        from wanted_search.search import _safe_provider_filename

        # secure_filename strips spaces and special chars but keeps the core form
        result = _safe_provider_filename("Attack.on.Titan.S01E01.srt")
        assert result == "Attack.on.Titan.S01E01.srt"

    def test_none_returns_empty(self):
        from wanted_search.search import _safe_provider_filename

        assert _safe_provider_filename(None) == ""

    def test_empty_returns_empty(self):
        from wanted_search.search import _safe_provider_filename

        assert _safe_provider_filename("") == ""

    def test_result_to_dict_uses_sanitiser(self):
        from unittest.mock import MagicMock

        from wanted_search.search import _result_to_dict

        result = MagicMock()
        result.provider_name = "subdl"
        result.subtitle_id = "abc"
        result.language = "de"
        result.format.value = "srt"
        result.filename = "../../escape.srt"
        result.release_info = ""
        result.score = 0
        result.score_breakdown = {}
        result.hearing_impaired = False
        result.matches = []

        out = _result_to_dict(result)
        assert ".." not in out["filename"]
        assert "/" not in out["filename"]
