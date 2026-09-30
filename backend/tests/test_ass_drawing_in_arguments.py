"""``\\p1`` inside another tag's arguments, measured against libass.

An external review of 1.15.0-rc.17 (2026-09-30) reported that these events
render visible dialogue but are read as drawings and deleted. Measured on the
PC with ffmpeg 8.0.1 / libass (320x180 frame, lit pixels > 40 of 255), the
lexer already agreed with the renderer on every one of them; the report
describes the regex reading that 1.14.4 replaced. The reference table in
``fixtures/ass_libass_0173.json`` has no ``\\t`` case at all, so the transform
rule was never pinned against pixels until now:

    2128 px  {\\p1(0)}Good morning.{\\p0}             paren arg wins: p0
    2128 px  {\\t(0,1000,2,3,\\p1)}Good morning.{\\p0} 5 args: no transform
       0 px  {\\t(0,1000,2,\\p1)}Good morning.{\\p0}   4 args: drawing on
       0 px  {\\t(\\p1)}Good morning.{\\p0}             1 arg: drawing on
    2128 px  {\\zzz(\\p1)}Good morning.{\\p0}           unknown tag
       0 px  {\\p1}m 0 0 l 1 1{\\c&H0000FF&}Good morning.{\\p0}
                                        the text is inside the drawing
"""

import os
import shutil
import subprocess

import pytest

from ass_utils import text_outside_drawing
from subtitle_sanitizer import sanitize_ass_content

LINE = "Good morning."

MEASURED = [
    (r"{\p1(0)}Good morning.{\p0}", True),
    (r"{\t(0,1000,2,3,\p1)}Good morning.{\p0}", True),
    (r"{\t(0,1000,2,\p1)}Good morning.{\p0}", False),
    (r"{\t(\p1)}Good morning.{\p0}", False),
    (r"{\zzz(\p1)}Good morning.{\p0}", True),
    (r"{\p1}m 0 0 l 1 1{\c&H0000FF&}Good morning.{\p0}", False),
]

HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 320
PlayResY: 180

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,40,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,5,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _event(text: str) -> str:
    return f"Dialogue: 0,0:00:00.00,0:00:05.00,Default,,0,0,0,,{text}\n"


@pytest.mark.parametrize("text, visible", MEASURED)
def test_the_lexer_reads_the_line_as_libass_renders_it(text, visible):
    assert (text_outside_drawing(text) == LINE) is visible


@pytest.mark.parametrize("text, visible", [m for m in MEASURED if m[1]])
def test_the_sanitizer_keeps_visible_dialogue(text, visible):
    cleaned = sanitize_ass_content((HEADER + _event(text)).encode()).decode()
    assert text in cleaned


def test_tags_inside_a_removed_span_keep_applying():
    """Only geometry leaves; colour, alignment and position stay in order."""
    text = r"{\p1}m 0 0 l 1 1{\c&H0000FF&\an8\pos(10,20)}l 2 2{\p0}Hello"

    cleaned = sanitize_ass_content((HEADER + _event(text)).encode()).decode()

    assert r"{\p1}{\c&H0000FF&\an8\pos(10,20)}{\p0}Hello" in cleaned


def _has_libass() -> bool:
    if shutil.which("ffmpeg") is None:
        return False
    out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True)
    return " subtitles " in out.stdout


def _lit_pixels(tmp_path, text: str) -> int:
    ass = tmp_path / "s.ass"
    ass.write_text(HEADER + _event(text), encoding="utf-8")
    # The subtitles filter parses ':' and '\' itself — pass a relative path.
    rel = os.path.relpath(ass).replace("\\", "/")
    out = subprocess.run(
        [
            "ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=black:s=320x180:d=5",
            "-ss", "1", "-vf", f"subtitles={rel}", "-frames:v", "1",
            "-f", "rawvideo", "-pix_fmt", "gray", "-",
        ],
        capture_output=True,
        check=True,
    )  # fmt: skip
    return sum(1 for b in out.stdout if b > 40)


@pytest.mark.skipif(not _has_libass(), reason="needs ffmpeg built with libass")
@pytest.mark.parametrize("text, visible", MEASURED)
def test_the_renderer_still_agrees(tmp_path, monkeypatch, text, visible):
    monkeypatch.chdir(tmp_path)
    assert (_lit_pixels(tmp_path, text) > 0) is visible
