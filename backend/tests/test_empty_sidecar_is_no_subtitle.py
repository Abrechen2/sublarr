"""An empty or header-only sidecar is no subtitle — for every caller alike.

Audit #61 A21: the wanted scan counted a header-only ``Film.de.ass`` as an
existing German subtitle and never searched the episode, while the format
cleanup already called the same file unusable.
"""

import os

import pytest

from subtitle_content import has_subtitle_lines
from translator.output_paths import detect_existing_target_for_lang

HEADER = "[Script Info]\nScriptType: v4.00+\n\n[Events]\nFormat: Layer, Start, End, Style, Text\n"
EVENT = "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,Hallo\n"


def _video(tmp_path):
    video = tmp_path / "Film.mkv"
    video.write_bytes(b"")
    return str(video)


@pytest.mark.parametrize("content", ["", HEADER])
def test_an_empty_ass_does_not_count_as_existing(tmp_path, content):
    video = _video(tmp_path)
    (tmp_path / "Film.de.ass").write_text(content, encoding="utf-8")

    assert detect_existing_target_for_lang(video, "de") is None


def test_an_ass_with_a_line_counts(tmp_path):
    video = _video(tmp_path)
    (tmp_path / "Film.de.ass").write_text(HEADER + EVENT, encoding="utf-8")

    assert detect_existing_target_for_lang(video, "de") == "ass"


def test_an_empty_srt_next_to_nothing_does_not_count(tmp_path):
    video = _video(tmp_path)
    (tmp_path / "Film.de.srt").write_text("", encoding="utf-8")

    assert detect_existing_target_for_lang(video, "de") is None


def test_the_first_line_after_a_big_fonts_section_is_found(tmp_path):
    """Embedded fonts can push the first event past any fixed sample."""
    path = tmp_path / "Film.de.ass"
    path.write_text(HEADER + "[Fonts]\n" + "x" * 300_000 + "\n" + EVENT, encoding="utf-8")

    assert has_subtitle_lines(str(path))


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads mode-000 files")
def test_an_unreadable_sidecar_still_counts_so_it_is_not_downloaded_forever(tmp_path):
    video = _video(tmp_path)
    path = tmp_path / "Film.de.ass"
    path.write_text(HEADER + EVENT, encoding="utf-8")
    path.chmod(0)
    try:
        assert detect_existing_target_for_lang(video, "de") == "ass"
        assert not has_subtitle_lines(str(path))
    finally:
        path.chmod(0o644)


SRT = "1\n00:00:01,000 --> 00:00:02,000\nHallo Welt\n"


@pytest.mark.parametrize(
    "data",
    [
        SRT.encode("utf-8"),
        SRT.encode("utf-8-sig"),
        SRT.encode("utf-16"),  # with BOM
        SRT.encode("utf-16-le"),
        SRT.encode("utf-16-be"),
    ],
    ids=["utf8", "utf8-bom", "utf16-bom", "utf16le", "utf16be"],
)
def test_a_valid_srt_counts_in_every_supported_encoding(tmp_path, data):
    """#63: the byte search missed UTF-16 files, so a covered language was searched again."""
    video = _video(tmp_path)
    (tmp_path / "Film.de.srt").write_bytes(data)

    assert detect_existing_target_for_lang(video, "de") == "srt"


@pytest.mark.parametrize("encoding", ["utf-16", "utf-16-be"])
def test_a_utf16_ass_with_a_line_counts_and_a_header_only_one_does_not(tmp_path, encoding):
    path = tmp_path / "Film.de.ass"
    path.write_bytes((HEADER + EVENT).encode(encoding))
    assert has_subtitle_lines(str(path))

    path.write_bytes(HEADER.encode(encoding))
    assert not has_subtitle_lines(str(path))
