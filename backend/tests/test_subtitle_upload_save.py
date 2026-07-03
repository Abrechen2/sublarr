import os

import pytest

from services.subtitle_upload import UploadError, build_sidecar_path, save_manual_subtitle

_SRT = b"1\n00:00:01,000 --> 00:00:02,000\nHallo\n"


def test_build_sidecar_path_plain():
    p = build_sidecar_path("/media/Show/Show - S01E01.mkv", "de", None, "srt")
    assert p == "/media/Show/Show - S01E01.de.srt"


def test_build_sidecar_path_with_modifier():
    p = build_sidecar_path("/media/Show/Show - S01E01.mkv", "en", "forced", "ass")
    assert p == "/media/Show/Show - S01E01.en.forced.ass"


def test_save_writes_file_and_returns_path(tmp_path):
    video = tmp_path / "Movie (2020).mkv"
    video.write_bytes(b"fakevideo")
    saved = save_manual_subtitle(
        str(video), _SRT, "srt", "de", None, overwrite=False, media_path=str(tmp_path)
    )
    assert os.path.exists(saved)
    assert saved.endswith(".de.srt")
    assert open(saved, "rb").read() == _SRT


def test_existing_without_overwrite_conflicts_409(tmp_path):
    video = tmp_path / "M.mkv"
    video.write_bytes(b"v")
    save_manual_subtitle(str(video), _SRT, "srt", "de", None, False, str(tmp_path))
    with pytest.raises(UploadError) as exc:
        save_manual_subtitle(str(video), _SRT, "srt", "de", None, False, str(tmp_path))
    assert exc.value.status == 409


def test_path_escaping_media_rejected_400(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    media = tmp_path / "media"
    media.mkdir()
    video = outside / "M.mkv"
    video.write_bytes(b"v")
    with pytest.raises(UploadError) as exc:
        save_manual_subtitle(str(video), _SRT, "srt", "de", None, False, str(media))
    assert exc.value.status == 400


def test_overwrite_same_ext_replaces_content(tmp_path):
    video = tmp_path / "M.mkv"
    video.write_bytes(b"v")
    save_manual_subtitle(str(video), _SRT, "srt", "de", None, False, str(tmp_path))

    new_content = b"1\n00:00:01,000 --> 00:00:02,000\nHallo neu\n"
    saved = save_manual_subtitle(str(video), new_content, "srt", "de", None, True, str(tmp_path))

    assert saved.endswith(".de.srt")
    assert open(saved, "rb").read() == new_content


def test_overwrite_different_ext_trashes_old_sidecar(tmp_path):
    video = tmp_path / "M.mkv"
    video.write_bytes(b"v")
    save_manual_subtitle(str(video), _SRT, "srt", "de", None, False, str(tmp_path))
    old_srt = tmp_path / "M.de.srt"
    assert old_srt.exists()

    new_content = b"[Script Info]\n"
    saved = save_manual_subtitle(str(video), new_content, "ass", "de", None, True, str(tmp_path))

    assert saved.endswith(".de.ass")
    assert open(saved, "rb").read() == new_content
    # The old .srt sidecar must be gone from next to the video (moved to
    # trash) — not left behind as an orphaned duplicate.
    assert not old_srt.exists()


def test_invalid_language_traversal_rejected_400(tmp_path):
    video = tmp_path / "M.mkv"
    video.write_bytes(b"v")
    with pytest.raises(UploadError) as exc:
        save_manual_subtitle(str(video), _SRT, "srt", "../etc", None, False, str(tmp_path))
    assert exc.value.status == 400


def test_invalid_modifier_traversal_rejected_400(tmp_path):
    video = tmp_path / "M.mkv"
    video.write_bytes(b"v")
    with pytest.raises(UploadError) as exc:
        save_manual_subtitle(str(video), _SRT, "srt", "de", "../x", False, str(tmp_path))
    assert exc.value.status == 400


def test_language_with_trailing_newline_rejected_400(tmp_path):
    video = tmp_path / "M.mkv"
    video.write_bytes(b"v")
    with pytest.raises(UploadError) as exc:
        save_manual_subtitle(str(video), _SRT, "srt", "de\n", None, False, str(tmp_path))
    assert exc.value.status == 400


def test_language_uppercase_rejected_400(tmp_path):
    video = tmp_path / "M.mkv"
    video.write_bytes(b"v")
    with pytest.raises(UploadError) as exc:
        save_manual_subtitle(str(video), _SRT, "srt", "EN", None, False, str(tmp_path))
    assert exc.value.status == 400


def test_valid_language_code_still_works(tmp_path):
    video = tmp_path / "M.mkv"
    video.write_bytes(b"v")
    saved = save_manual_subtitle(str(video), _SRT, "srt", "de", None, False, str(tmp_path))
    assert os.path.exists(saved)
    assert saved.endswith(".de.srt")
