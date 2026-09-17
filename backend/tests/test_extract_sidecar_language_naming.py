"""Extracted sidecars must be named with the canonical language code.

``get_subtitle_stream_output_path`` took the language straight from the MKV
track tag, which carries ISO 639-2/B ("ger", "eng"), and wrote it into the
filename unchanged. Two things follow from that:

* the library grows a second German subtitle — ``.ger.srt`` next to an existing
  ``.de.srt`` — and players list both. On the reference install 2 406 episodes
  carried German under more than one code, 1 946 of them with different
  content; the ``.ger`` files were the recent ones (median 2026-08-08).
* the extractor's own "already on disk" guard checks that same un-normalised
  path, so it never sees the ``.de`` sidecar sitting right beside it and
  extracts the track again.

Normalising the code fixes both: the name matches what the rest of the code
already treats as German (``config_language_data.normalize_language_code``),
and the guard starts recognising the file it should have recognised all along.
"""

from __future__ import annotations

import os

import pytest


@pytest.mark.parametrize(
    ("tag", "fmt", "expected"),
    [
        ("ger", "srt", ".de.srt"),
        ("deu", "srt", ".de.srt"),
        ("eng", "ass", ".en.ass"),
        ("de", "srt", ".de.srt"),  # already canonical — unchanged
        ("GER", "srt", ".de.srt"),  # case is irrelevant
        ("jpn", "ass", ".ja.ass"),  # not a target language, still canonicalised
    ],
)
def test_output_path_uses_canonical_code(tag, fmt, expected):
    from ass_probe import get_subtitle_stream_output_path

    out = get_subtitle_stream_output_path(
        "/media/Show - S01E01.mkv", {"language": tag, "format": fmt}
    )
    assert out == "/media/Show - S01E01" + expected


def test_missing_language_stays_undetermined():
    from ass_probe import get_subtitle_stream_output_path

    out = get_subtitle_stream_output_path("/media/Show - S01E01.mkv", {"format": "ass"})
    assert out.endswith(".und.ass")


def test_unknown_code_is_left_alone():
    """An unrecognised tag must not be mangled into something else."""
    from ass_probe import get_subtitle_stream_output_path

    out = get_subtitle_stream_output_path(
        "/media/Show - S01E01.mkv", {"language": "qqq", "format": "srt"}
    )
    assert out.endswith(".qqq.srt")


def test_existing_canonical_sidecar_stops_a_second_extraction(tmp_path):
    """The regression that produced the duplicates, end to end.

    A German track plus a ``.de.srt`` already on disk must extract nothing.
    Before the fix the guard looked for ``.ger.srt``, missed the file, and
    wrote a second German subtitle next to the first.
    """
    from ass_probe import get_subtitle_stream_output_path

    mkv = str(tmp_path / "Show - S01E02.mkv")
    with open(mkv, "wb") as fh:
        fh.write(b"\x00")
    existing = str(tmp_path / "Show - S01E02.de.srt")
    with open(existing, "w", encoding="utf-8") as fh:
        fh.write("1\n00:00:01,000 --> 00:00:02,000\nHallo\n\n")

    out = get_subtitle_stream_output_path(mkv, {"language": "ger", "format": "srt"})

    assert out == existing
    assert os.path.exists(out), "the guard in embedded_extractor keys off exactly this path"


def test_legacy_named_sidecar_still_counts_as_extracted(tmp_path, monkeypatch):
    """Canonicalising the name must not re-extract what is already on disk.

    Installs that ran the old code have sidecars under the raw tag. If the
    guard only looked for the new canonical name it would miss them and write
    a second copy — the very duplication this change removes. The legacy name
    stays a valid answer to "is this track already extracted?".
    """
    import services.embedded_extractor as ee

    mkv = str(tmp_path / "Show - S01E03.mkv")
    with open(mkv, "wb") as fh:
        fh.write(b"\x00")
    legacy = str(tmp_path / "Show - S01E03.ger.srt")
    with open(legacy, "w", encoding="utf-8") as fh:
        fh.write("1\n00:00:01,000 --> 00:00:02,000\nHallo\n\n")

    calls = []
    monkeypatch.setattr(
        "ass_utils.extract_subtitle_stream",
        lambda *a, **kw: calls.append(a),
    )

    streams = [{"language": "ger", "format": "srt", "sub_index": 0, "index": 0}]
    _any, to_remove, extracted = ee.extract_streams(mkv, streams, log_label="test")

    assert calls == [], "the track was extracted again despite a legacy sidecar"
    assert to_remove == [], "a stream that was not freshly extracted must not be removed"
    assert extracted and extracted[0]["output_path"] == legacy


def test_existing_ass_covers_an_embedded_srt_track(tmp_path, monkeypatch):
    """An .ass for the language is coverage; extracting the .srt next to it is churn.

    Prod 2026-09-17: a provider ``.de.ass`` sat next to the video, every pass
    over the episode extracted the embedded German track as ``.de.srt`` anyway,
    and the "keep ass" format rule trashed it the next morning — the same file
    was in the trash on the 12th, 14th and 16th, 7-20 of them a day.
    """
    import services.embedded_extractor as ee

    mkv = str(tmp_path / "Show - S01E04.mkv")
    with open(mkv, "wb") as fh:
        fh.write(b"\x00")
    provider_ass = str(tmp_path / "Show - S01E04.de.ass")
    with open(provider_ass, "w", encoding="utf-8") as fh:
        fh.write(
            "[Script Info]\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL,"
            " MarginR, MarginV, Effect, Text\n"
            "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,Kürzlich löste ein Spieler\n"
        )

    calls = []
    monkeypatch.setattr(
        "ass_utils.extract_subtitle_stream",
        lambda *a, **kw: calls.append(a),
    )

    streams = [{"language": "ger", "format": "srt", "sub_index": 0, "stream_index": 2}]
    any_extracted, to_remove, extracted = ee.extract_streams(mkv, streams, log_label="test")

    assert calls == [], "the srt track was extracted although an .ass covers the language"
    assert any_extracted is True
    assert to_remove == [], "a track that was not extracted must stay in the container"
    assert extracted[0]["output_path"] == provider_ass
    assert extracted[0]["format"] == "ass"
    assert not os.path.exists(str(tmp_path / "Show - S01E04.de.srt"))


def test_existing_srt_does_not_stop_an_ass_track(tmp_path, monkeypatch):
    """The other direction stays as it was: an ass track is still worth extracting."""
    import services.embedded_extractor as ee

    mkv = str(tmp_path / "Show - S01E05.mkv")
    with open(mkv, "wb") as fh:
        fh.write(b"\x00")
    with open(tmp_path / "Show - S01E05.de.srt", "w", encoding="utf-8") as fh:
        fh.write("1\n00:00:01,000 --> 00:00:02,000\nHallo\n\n")

    calls = []
    monkeypatch.setattr(
        "ass_utils.extract_subtitle_stream",
        lambda *a, **kw: calls.append(a),
    )

    streams = [{"language": "ger", "format": "ass", "sub_index": 0, "stream_index": 2}]
    ee.extract_streams(mkv, streams, log_label="test")

    assert len(calls) == 1
