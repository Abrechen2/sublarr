"""Tests for providers.format_validator."""

from providers.base import SubtitleFormat


def test_detect_ass_by_script_info_header():
    from providers.format_validator import detect_format_from_content

    content = b"[Script Info]\nTitle: Test"
    assert detect_format_from_content(content) == SubtitleFormat.ASS


def test_detect_ass_by_v4_header():
    from providers.format_validator import detect_format_from_content

    content = b"[V4+ Styles]\nFormat: Name"
    assert detect_format_from_content(content) == SubtitleFormat.ASS


def test_detect_srt_by_default():
    from providers.format_validator import detect_format_from_content

    content = b"1\n00:00:01,000 --> 00:00:02,000\nHello world"
    assert detect_format_from_content(content) == SubtitleFormat.SRT


def test_detect_strips_utf8_bom():
    from providers.format_validator import detect_format_from_content

    content = b"\xef\xbb\xbf[Script Info]\nTitle: Test"
    assert detect_format_from_content(content) == SubtitleFormat.ASS


def test_detect_handles_empty_bytes():
    from providers.format_validator import detect_format_from_content

    assert detect_format_from_content(b"") == SubtitleFormat.SRT


def test_detect_handles_binary_garbage():
    from providers.format_validator import detect_format_from_content

    assert detect_format_from_content(b"\x00\x01\x02\x03") == SubtitleFormat.SRT
