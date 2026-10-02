"""Typeset ASS is allowed to be larger than a plain-text subtitle.

Prod 2026-10-02: 16 episodes in 22 hours (Attack on Titan, Sword Oratoria,
Demon Slayer, Chainsaw Man …) were offered by animetosho as ASS files of
5.5-14.7 MB and every one was rejected by the 5 MB sanitizer limit, then
downloaded again on the next search. Fansub typesetting — signs, karaoke,
drawings — makes an ASS several times the size of its dialogue. SRT/VTT
stay at 5 MB; the provider download cap (50 MB) still bounds everything.
"""

from __future__ import annotations

import pytest

from providers.base import SubtitleFormat
from subtitle_sanitizer import _MAX_ASS_BYTES, _MAX_SUBTITLE_BYTES, sanitize_subtitle

_HEADER = (
    "[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\n\n"
    "[V4+ Styles]\n"
    "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
    "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
    "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
    "Style: Default,Arial,48,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,"
    "100,100,0,0,1,2,0,2,10,10,10,1\n\n"
    "[Events]\n"
    "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
)


def _typeset_ass(min_bytes: int) -> bytes:
    """An ASS that is large the way real typesetting is: many positioned,
    styled sign lines, each carrying a long run of override tags."""
    line = (
        "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,"
        "{\\an7\\pos(%d,540)\\fs40\\bord0\\shad0\\c&H2A2A2A&\\alpha&H10&"
        "\\t(0,500,\\fscx105\\fscy105)\\blur0.6}Sign text %d\n"
    )
    parts = [_HEADER]
    size = len(_HEADER)
    i = 0
    while size < min_bytes:
        row = line % (i % 1920, i)
        parts.append(row)
        size += len(row)
        i += 1
    return "".join(parts).encode("utf-8")


def test_ass_above_the_text_limit_is_accepted():
    content = _typeset_ass(10 * 1024 * 1024)
    assert len(content) > _MAX_SUBTITLE_BYTES

    result = sanitize_subtitle(content, SubtitleFormat.ASS)

    assert b"Sign text 0" in result


def test_ass_above_its_own_limit_is_rejected():
    content = b"[Script Info]\n" + b"x" * _MAX_ASS_BYTES

    with pytest.raises(ValueError, match="too large"):
        sanitize_subtitle(content, SubtitleFormat.ASS)


def test_srt_keeps_the_text_limit():
    entry = b"1\n00:00:01,000 --> 00:00:02,000\nline\n\n"
    content = entry * (_MAX_SUBTITLE_BYTES // len(entry) + 1)

    with pytest.raises(ValueError, match="too large"):
        sanitize_subtitle(content, SubtitleFormat.SRT)


def test_ass_limit_stays_below_the_download_cap():
    from providers.download_manager import _MAX_SUBTITLE_SIZE

    assert _MAX_SUBTITLE_BYTES < _MAX_ASS_BYTES < _MAX_SUBTITLE_SIZE
