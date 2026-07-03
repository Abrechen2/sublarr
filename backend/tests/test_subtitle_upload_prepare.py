import pytest

from services.subtitle_upload import MAX_UPLOAD_BYTES, UploadError, prepare_upload

_SRT = b"1\n00:00:01,000 --> 00:00:02,000\nHallo Welt\n"


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
    with pytest.raises(UploadError):
        prepare_upload("a.srt", b"")


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
