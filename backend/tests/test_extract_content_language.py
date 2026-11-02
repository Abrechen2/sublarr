"""An SRT whose words are the wrong language must not be adopted or kept.

Prod 2026-11-02: 495 ``.de.srt`` files held English dialogue; 403 were written
by extract passes on 2026-08-30 and nothing noticed for two months. The script
check (``script_mismatch``) cannot tell English from German - both are Latin -
so the content has to be read.
"""

from __future__ import annotations

import pytest

_ENGLISH = "".join(
    f"{i}\n00:00:{i:02d},000 --> 00:00:{i:02d},900\n{line}\n\n"
    for i, line in enumerate(
        [
            "I have heard that she is quite the terror around here.",
            "We should never have left the village without telling anyone.",
            "Please tell me what happened to you after the festival ended.",
            "This is the third time you have said that to me today.",
            "There is nothing more that we can do for them now.",
        ],
        start=1,
    )
)
_GERMAN = "".join(
    f"{i}\n00:00:{i:02d},000 --> 00:00:{i:02d},900\n{line}\n\n"
    for i, line in enumerate(
        [
            "Ich habe gehört, dass sie hier ziemlich gefürchtet ist.",
            "Wir hätten das Dorf nie verlassen sollen, ohne jemandem Bescheid zu sagen.",
            "Bitte sag mir, was dir nach dem Fest zugestoßen ist.",
            "Das ist heute schon das dritte Mal, dass du mir das sagst.",
            "Wir können jetzt nichts mehr für sie tun.",
        ],
        start=1,
    )
)


def _write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


@pytest.mark.parametrize(
    ("text", "tag", "name", "expected"),
    [
        (_ENGLISH, "de", "Show.de.srt", False),
        (_ENGLISH, "ger", "Show.ger.srt", False),
        (_GERMAN, "de", "Show.de.srt", True),
        (_GERMAN, "en", "Show.en.srt", False),
        (_ENGLISH, "en", "Show.en.srt", True),
        (_ENGLISH, "fr", "Show.fr.srt", True),  # the detector knows only en/de
    ],
)
def test_sidecar_is_judged_by_its_words(tmp_path, text, tag, name, expected):
    import services.embedded_extractor as ee

    path = _write(tmp_path, name, text)
    assert ee._sidecar_matches_tag(path, tag, "test") is expected


def test_short_text_is_trusted(tmp_path):
    import services.embedded_extractor as ee

    path = _write(tmp_path, "Show.de.srt", "1\n00:00:01,000 --> 00:00:02,000\nYes.\n\n")
    assert ee._sidecar_matches_tag(path, "de", "test") is True


def test_an_ass_file_is_not_judged_by_words(tmp_path):
    """Signs and songs stay English in a German ASS on purpose."""
    import services.embedded_extractor as ee

    body = (
        "[Script Info]\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL,"
        " MarginR, MarginV, Effect, Text\n"
        + "".join(
            f"Dialogue: 0,0:00:{i:02d}.00,0:00:{i:02d}.90,Songs,,0,0,0,,We will never forget"
            " the days we spent together under this sky\n"
            for i in range(1, 8)
        )
    )
    path = _write(tmp_path, "Show.de.ass", body)
    assert ee._sidecar_matches_tag(path, "de", "test") is True


def test_a_fresh_extract_of_the_wrong_language_is_dropped_and_the_stream_kept(
    tmp_path, monkeypatch
):
    import services.embedded_extractor as ee

    mkv = str(tmp_path / "Show - S01E01.mkv")
    (tmp_path / "Show - S01E01.mkv").write_bytes(b"\x00")

    def fake_extract(video, stream, out):
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(_ENGLISH)

    trashed = []
    monkeypatch.setattr("ass_utils.extract_subtitle_stream", fake_extract)
    monkeypatch.setattr(ee, "_trash_path", lambda p: trashed.append(p) or True)

    streams = [{"language": "ger", "format": "srt", "sub_index": 0, "stream_index": 3}]
    any_extracted, to_remove, extracted = ee.extract_streams(mkv, streams, log_label="test")

    assert any_extracted is False
    assert extracted == []
    assert to_remove == [], "a rejected stream must stay in the container"
    assert len(trashed) == 1 and trashed[0].endswith(".srt")
