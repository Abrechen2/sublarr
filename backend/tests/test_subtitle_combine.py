"""Unit tests for the combined/bilingual subtitle composition engine
(V1.6 Feature #1, C2). Pure — no Flask/DB, only tmp files on disk.

Covers: alignment detection (sibling/offset/overlap), ASS overlay positioning,
SRT stacking, source-priority selection, sanitize-on-input, and rejection of
bitmap / unsupported formats and degenerate input.
"""

from __future__ import annotations

import pysubs2
import pytest

from services.subtitle_combine import (
    CombineError,
    combine_subtitles,
    detect_alignment,
    pick_best_sidecar,
)


def _write(tmp_path, name: str, cues: list[tuple[int, int, str]], fmt: str = "srt") -> str:
    subs = pysubs2.SSAFile()
    for start, end, text in cues:
        ev = pysubs2.SSAEvent(start=start, end=end)
        ev.plaintext = text
        subs.events.append(ev)
    path = str(tmp_path / name)
    subs.save(path, format_=fmt)
    return path


# ── detect_alignment ────────────────────────────────────────────────────────


def test_alignment_sibling_when_equal_counts():
    mode, off = detect_alignment([1000, 2000, 3000], [1010, 2020, 3030])
    assert mode == "sibling"
    assert off == 0


def test_alignment_offset_when_shifted_subset():
    # secondary is primary[1..3] → each primary[i] pairs secondary[i-1]
    primary = [1000, 2000, 3000, 4000, 5000]
    secondary = [2000, 3000, 4000]
    mode, off = detect_alignment(primary, secondary)
    assert mode == "offset"
    assert off == -1


def test_alignment_overlap_fallback():
    primary = [1000, 5000]
    secondary = [900, 1100, 1200, 4800, 5200, 8000]
    mode, _ = detect_alignment(primary, secondary)
    assert mode == "overlap"


# ── ASS overlay ─────────────────────────────────────────────────────────────


def test_combine_ass_overlays_both_languages_with_positions(tmp_path):
    de = _write(tmp_path, "m.de.ass", [(1000, 3000, "Hallo Welt")], fmt="ass")
    en = _write(tmp_path, "m.en.ass", [(1000, 3000, "Hello world")], fmt="ass")

    out = combine_subtitles(
        [
            {"language": "de", "path": de, "format": "ass"},
            {"language": "en", "path": en, "format": "ass"},
        ],
        output_format="ass",
        position={"primary": "bottom", "secondary": "top"},
    )
    result = pysubs2.SSAFile.from_string(out.decode("utf-8"))
    texts = [e.text for e in result.events]
    assert any("Hallo Welt" in t for t in texts)
    assert any("Hello world" in t for t in texts)
    # primary (de) bottom = \an2, secondary (en) top = \an8
    de_ev = next(e for e in result.events if "Hallo Welt" in e.text)
    en_ev = next(e for e in result.events if "Hello world" in e.text)
    assert "\\an2" in de_ev.text
    assert "\\an8" in en_ev.text


def test_combine_ass_respects_custom_position(tmp_path):
    de = _write(tmp_path, "m.de.ass", [(1000, 3000, "Hallo")], fmt="ass")
    en = _write(tmp_path, "m.en.ass", [(1000, 3000, "Hello")], fmt="ass")
    out = combine_subtitles(
        [
            {"language": "de", "path": de, "format": "ass"},
            {"language": "en", "path": en, "format": "ass"},
        ],
        output_format="ass",
        position={"primary": "top", "secondary": "bottom"},
    )
    result = pysubs2.SSAFile.from_string(out.decode("utf-8"))
    de_ev = next(e for e in result.events if "Hallo" in e.text)
    en_ev = next(e for e in result.events if "Hello" in e.text)
    assert "\\an8" in de_ev.text  # primary now top
    assert "\\an2" in en_ev.text  # secondary now bottom


# ── SRT stacking ────────────────────────────────────────────────────────────


def test_combine_srt_stacks_sibling_cues_under_primary_timestamps(tmp_path):
    de = _write(tmp_path, "m.de.srt", [(1000, 3000, "Hallo"), (4000, 6000, "Tschüss")])
    en = _write(tmp_path, "m.en.srt", [(1010, 3020, "Hello"), (4010, 6020, "Bye")])

    out = combine_subtitles(
        [
            {"language": "de", "path": de, "format": "srt"},
            {"language": "en", "path": en, "format": "srt"},
        ],
        output_format="srt",
        position={"primary": "bottom", "secondary": "top"},
    )
    result = pysubs2.SSAFile.from_string(out.decode("utf-8"))
    assert len(result.events) == 2
    first = result.events[0]
    # both languages present, on separate lines, primary timing preserved
    assert "Hallo" in first.plaintext and "Hello" in first.plaintext
    assert first.start == 1000
    # secondary is 'top' → EN line rendered before DE line
    assert first.plaintext.index("Hello") < first.plaintext.index("Hallo")


def test_combine_srt_overlap_join(tmp_path):
    de = _write(tmp_path, "m.de.srt", [(1000, 6000, "Ein langer Satz")])
    en = _write(tmp_path, "m.en.srt", [(1000, 3000, "A long"), (3000, 6000, "sentence")])
    out = combine_subtitles(
        [
            {"language": "de", "path": de, "format": "srt"},
            {"language": "en", "path": en, "format": "srt"},
        ],
        output_format="srt",
    )
    result = pysubs2.SSAFile.from_string(out.decode("utf-8"))
    joined = result.events[0].plaintext
    assert "A long" in joined and "sentence" in joined
    assert "Ein langer Satz" in joined


# ── source priority ─────────────────────────────────────────────────────────


def test_pick_best_sidecar_prefers_plain_over_hi_over_forced():
    candidates = [
        {"language": "de", "modifier": "forced", "path": "a"},
        {"language": "de", "modifier": "hi", "path": "b"},
        {"language": "de", "modifier": None, "path": "c"},
    ]
    assert pick_best_sidecar(candidates)["path"] == "c"

    assert pick_best_sidecar(candidates[:2])["path"] == "b"  # hi beats forced
    assert pick_best_sidecar(candidates[:1])["path"] == "a"  # only forced left
    assert pick_best_sidecar([]) is None


# ── sanitize-on-input ───────────────────────────────────────────────────────


def test_combine_sanitizes_ass_drawing_mode(tmp_path):
    # An ASS drawing (\p1 ... \p0) must be stripped before composing.
    malicious = (
        "[Script Info]\nScriptType: v4.00+\n[V4+ Styles]\n"
        "Format: Name\nStyle: Default\n[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,{\\p1}m 0 0 l 100 0 100 100{\\p0}Echt\n"
    )
    de = str(tmp_path / "m.de.ass")
    with open(de, "w", encoding="utf-8") as f:
        f.write(malicious)
    en = _write(tmp_path, "m.en.ass", [(1000, 3000, "Hello")], fmt="ass")

    out = combine_subtitles(
        [
            {"language": "de", "path": de, "format": "ass"},
            {"language": "en", "path": en, "format": "ass"},
        ],
        output_format="ass",
    )
    text = out.decode("utf-8")
    assert "m 0 0 l 100 0" not in text  # drawing coordinates stripped


# ── rejections ──────────────────────────────────────────────────────────────


def test_combine_rejects_bitmap_format(tmp_path):
    en = _write(tmp_path, "m.en.srt", [(1000, 3000, "Hello")])
    with pytest.raises(CombineError):
        combine_subtitles(
            [
                {"language": "de", "path": "x.sup", "format": "pgs"},
                {"language": "en", "path": en, "format": "srt"},
            ],
            output_format="srt",
        )


def test_combine_rejects_single_input(tmp_path):
    en = _write(tmp_path, "m.en.srt", [(1000, 3000, "Hello")])
    with pytest.raises(CombineError):
        combine_subtitles([{"language": "en", "path": en, "format": "srt"}], output_format="srt")


def test_combine_srt_skips_comment_events(tmp_path):
    # An ASS Comment line (karaoke/typeset template) must not leak into SRT output.
    de = str(tmp_path / "m.de.ass")
    with open(de, "w", encoding="utf-8") as f:
        f.write(
            "[Script Info]\nScriptType: v4.00+\n[V4+ Styles]\nFormat: Name\nStyle: Default\n"
            "[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            "Comment: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,KARAOKE TEMPLATE\n"
            "Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,Echter Text\n"
        )
    en = _write(tmp_path, "m.en.srt", [(1000, 3000, "Real text")])
    out = combine_subtitles(
        [
            {"language": "de", "path": de, "format": "ass"},
            {"language": "en", "path": en, "format": "srt"},
        ],
        output_format="srt",
    )
    text = out.decode("utf-8")
    assert "KARAOKE TEMPLATE" not in text
    assert "Echter Text" in text


def test_combine_rejects_invalid_output_format(tmp_path):
    de = _write(tmp_path, "m.de.srt", [(1, 2, "a")])
    en = _write(tmp_path, "m.en.srt", [(1, 2, "b")])
    with pytest.raises(CombineError):
        combine_subtitles(
            [
                {"language": "de", "path": de, "format": "srt"},
                {"language": "en", "path": en, "format": "srt"},
            ],
            output_format="vtt",
        )
