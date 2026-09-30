"""Translated output is repaired and sanitized before it is written, not after.

The three translator flows used to write the result, then repair the file,
then sanitize it in place. A result the sanitizer could not read stayed on
disk as written — and the previous subtitle at that path was already gone.
Owner decision 2026-09-30, before the 1.15.0 release: sanitize in memory, and
when that fails, abort the save and keep whatever was at the target before.
"""

from unittest.mock import patch

import pysubs2
import pytest

ASS_HEADER = """[Script Info]
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _subs(text: str) -> pysubs2.SSAFile:
    return pysubs2.SSAFile.from_string(
        ASS_HEADER + f"Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,{text}\n"
    )


def test_the_result_is_sanitized_before_it_reaches_the_disk(app_ctx, tmp_path):
    from translator._helpers import save_translated_output

    target = tmp_path / "ep.de.ass"
    save_translated_output(_subs(r"{\p1}m 0 0 l 9 9{\p0}Hallo"), str(target), "ass")

    written = target.read_text(encoding="utf-8")
    assert r"{\p1}{\p0}Hallo" in written
    assert "m 0 0 l 9 9" not in written


def test_a_result_the_sanitizer_cannot_read_keeps_the_previous_subtitle(app_ctx, tmp_path):
    from translator._helpers import TranslatedOutputRejectedError, save_translated_output

    target = tmp_path / "ep.de.ass"
    target.write_text("the subtitle that was here before", encoding="utf-8")

    with (
        patch("subtitle_sanitizer.sanitize_ass_content", side_effect=ValueError("unreadable")),
        pytest.raises(TranslatedOutputRejectedError, match="unreadable"),
    ):
        save_translated_output(_subs("Hallo"), str(target), "ass")

    assert target.read_text(encoding="utf-8") == "the subtitle that was here before"
    files = sorted(p.name for p in tmp_path.iterdir() if p.is_file())
    assert files == ["ep.de.ass"], "no temp file left"


def test_a_rejected_result_does_not_trigger_post_processing(app_ctx, tmp_path):
    from translator._helpers import TranslatedOutputRejectedError, save_translated_output

    with (
        patch("subtitle_sanitizer.sanitize_srt_vtt_content", side_effect=ValueError("bad")),
        patch("translator._helpers._fire_after_translate") as fire,
        pytest.raises(TranslatedOutputRejectedError),
    ):
        save_translated_output(_subs("Hallo"), str(tmp_path / "ep.de.srt"), "srt")

    fire.assert_not_called()


def test_a_saved_result_triggers_post_processing_once(app_ctx, tmp_path):
    from translator._helpers import save_translated_output

    target = tmp_path / "ep.de.srt"
    with patch("translator._helpers._fire_after_translate") as fire:
        save_translated_output(_subs("Hallo"), str(target), "srt")

    fire.assert_called_once_with(str(target))
    assert "Hallo" in target.read_text(encoding="utf-8")


def test_a_failing_repair_pass_still_saves(app_ctx, tmp_path):
    """Unchanged: repair is best-effort and never aborts a translation."""
    from translator._helpers import save_translated_output

    target = tmp_path / "ep.de.srt"
    with patch("subtitle_repair.repair_bytes", side_effect=RuntimeError("repair broke")):
        save_translated_output(_subs("Hallo"), str(target), "srt")

    assert "Hallo" in target.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "flow",
    ["translator/srt_flow.py", "translator/ass_flow.py"],
)
def test_the_flows_no_longer_sanitize_after_writing(flow):
    """All three save sites go through the helper; the old write-then-fix
    steps must not come back next to it."""
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / flow).read_text(encoding="utf-8")
    assert "save_translated_output(" in source
    assert "sanitize_subtitle_file(" not in source
    assert "atomic_save_subs(" not in source
