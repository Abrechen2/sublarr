import pytest

from services.subtitle_upload import MAX_UPLOAD_BYTES, UploadError, prepare_upload

_SRT = b"1\n00:00:01,000 --> 00:00:02,000\nHallo Welt\n"

_VALID_ASS_WITH_DRAWING = (
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
    b"Dialogue: 0,0:00:01.00,0:00:05.00,Default,,0,0,0,,{\\p1}m 0 0 l 100 0{\\p0}Hello World!\n"
)


def test_valid_srt_returns_content_and_ext():
    content, ext = prepare_upload("Movie.de.srt", _SRT)
    assert ext == "srt"
    assert b"Hallo Welt" in content


def test_archive_rejected_with_415():
    with pytest.raises(UploadError) as exc:
        prepare_upload("subs.zip", b"PK\x03\x04whatever")
    assert exc.value.status == 415


def test_unknown_extension_rejected():
    with pytest.raises(UploadError) as exc:
        prepare_upload("movie.txt", _SRT)
    assert exc.value.status == 415


def test_empty_rejected():
    with pytest.raises(UploadError) as exc:
        prepare_upload("a.srt", b"")
    assert exc.value.status == 422


def test_oversize_rejected_with_413():
    with pytest.raises(UploadError) as exc:
        prepare_upload("a.srt", b"x" * (MAX_UPLOAD_BYTES + 1))
    assert exc.value.status == 413


def test_binary_bitmap_content_rejected_with_422():
    with pytest.raises(UploadError) as exc:
        prepare_upload("a.srt", b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
    assert exc.value.status == 422


def test_valid_vtt_returns_content_and_ext():
    content, ext = prepare_upload("cap.vtt", b"WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nHallo\n")
    assert ext == "vtt"
    assert b"Hallo" in content


def test_vtt_content_beats_srt_extension():
    content, ext = prepare_upload("cap.srt", b"WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nHi\n")
    assert ext == "vtt"
    assert b"Hi" in content


def test_sub_extension_rejected_with_415():
    with pytest.raises(UploadError) as exc:
        prepare_upload("x.sub", _SRT)
    assert exc.value.status == 415


def test_binary_content_with_ass_decoy_header_rejected():
    """An ASS-looking header followed by binary must not slip past the
    first-line-only content-type check — the whole-payload magic-byte/
    control-byte validation (P4 defense) must reject it before sanitizing."""
    with pytest.raises(UploadError) as exc:
        prepare_upload("evil.srt", b"[Script Info]\n" + bytes(range(256)) * 4)
    assert exc.value.status == 422


def test_binary_content_with_srt_decoy_header_rejected():
    """Same bypass, SRT-shaped decoy header ('1\\n') followed by binary."""
    with pytest.raises(UploadError) as exc:
        prepare_upload("evil2.srt", b"1\n" + bytes(range(256)) * 4)
    assert exc.value.status == 422


def test_content_beats_extension_ass_in_srt_file():
    """Format detection must follow CONTENT, never the filename extension:
    an .srt-named upload containing genuine ASS (with a drawing-mode block)
    must be detected as ass and sanitized (drawing block stripped) — not
    written through untouched because the name said .srt."""
    content, ext = prepare_upload("evil.srt", _VALID_ASS_WITH_DRAWING)
    assert ext == "ass"
    assert b"\\p1" not in content
    assert b"\\p0" not in content
    assert b"m 0 0 l 100" not in content
    assert b"Hello World" in content
