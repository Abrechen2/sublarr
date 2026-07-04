"""Combined-subtitle files must surface as editable sidecars (V1.6 #1, C4c).

A combined file is named ``<base>.<l1>-<l2>[-<l3>].combined.<ext>``. The shared
``parse_subtitle_filename`` deliberately returns None for it (so the keep-langs
cleanup never trashes it — the dual "de-en" tag is not a target language). This
test covers the additive path: ``parse_combined_filename`` recognizes it and
``scan_subtitle_sidecars`` lists it with a ``combined`` marker so the UI can
open it in the editor.
"""

from __future__ import annotations

import os
from pathlib import Path

from subtitle_filename import parse_combined_filename, parse_subtitle_filename


def test_parse_combined_filename_recognizes_dual_lang():
    r = parse_combined_filename("/m/Show - S01E01.de-en.combined.ass")
    assert r == ("de-en", "ass")


def test_parse_combined_filename_recognizes_triple_lang():
    r = parse_combined_filename("/m/Movie.de-en-ja.combined.srt")
    assert r == ("de-en-ja", "srt")


def test_parse_combined_filename_rejects_non_combined():
    assert parse_combined_filename("/m/Show.de.srt") is None
    assert parse_combined_filename("/m/Show.de-en.ass") is None  # missing .combined
    assert parse_combined_filename("/m/Show.combined.ass") is None  # no lang tag
    # Syntactic check only (like the rest of the parser): tokens must be 2-3
    # letters, so a spelled-out pair is rejected.
    assert parse_combined_filename("/m/Show.german-english.combined.ass") is None


def test_shared_parser_still_rejects_combined():
    # Must stay None so keep-langs cleanup never treats "de-en" as a language.
    assert parse_subtitle_filename("/m/Show.de-en.combined.ass") is None


def test_scan_includes_combined_file(tmp_path):
    from routes.subtitles.helpers import scan_subtitle_sidecars

    video = str(tmp_path / "ep.mkv")
    Path(video).touch()
    Path(tmp_path / "ep.de.srt").write_text("1\n00:00:01,000 --> 00:00:02,000\nHallo\n")
    combined = tmp_path / "ep.de-en.combined.ass"
    combined.write_text("[Script Info]\n[Events]\n")

    entries = scan_subtitle_sidecars(video)
    combined_entry = next((e for e in entries if e.get("combined")), None)
    assert combined_entry is not None
    assert combined_entry["path"] == str(combined)
    assert combined_entry["language"] == "de-en"
    assert combined_entry["format"] == "ass"
    # The plain sidecar still surfaces normally.
    assert any(e.get("language") == "de" and not e.get("combined") for e in entries)


def test_combined_not_treated_as_source_by_resolve(tmp_path):
    # resolve_combine_sources must never pick the combined file as a language source.
    from services.combine_service import resolve_combine_sources

    video = str(tmp_path / "ep.mkv")
    Path(video).touch()
    Path(tmp_path / "ep.de.srt").write_text("x")
    Path(tmp_path / "ep.en.srt").write_text("x")
    Path(tmp_path / "ep.de-en.combined.ass").write_text("x")

    present, missing = resolve_combine_sources(video, ["de", "en"])
    assert missing == []
    assert {p["language"] for p in present} == {"de", "en"}
    assert all(not p["path"].endswith(".combined.ass") for p in present)
