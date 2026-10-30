"""A saved translation goes through the processing pipeline like a download.

Prod 2026-10-30, Slime S02E20: HI removal was on, yet the German translation
of an English CC track kept "[HERMES stöhnt]" and 140 more markers — only
provider downloads ran the pipeline.
"""

from unittest.mock import MagicMock, patch

import pysubs2

from translator._helpers import save_translated_output

SETTINGS = MagicMock(
    auto_process_common_fixes=False,
    auto_process_hi_removal=True,
    auto_process_credit_removal=False,
)


def _subs():
    subs = pysubs2.SSAFile()
    for start, text in (
        (1000, "[HERMES stöhnt]"),
        (3000, "Nein, Sir Gabiru..."),
        (5000, "[lacht] Ja."),
    ):
        subs.events.append(pysubs2.SSAEvent(start=start, end=start + 1500, text=text))
    return subs


def test_hi_markers_leave_a_saved_translation(tmp_path):
    out = tmp_path / "Show - S02E20.de.srt"
    with (
        patch("routes.subtitle_processor.get_settings", return_value=SETTINGS),
        patch("services.standalone_owner_keys.get_row", return_value=None),
        patch("translator._helpers._fire_after_translate"),
    ):
        save_translated_output(_subs(), str(out), "srt")

    assert [e.text for e in pysubs2.load(str(out)).events] == ["Nein, Sir Gabiru...", "Ja."]


def test_a_failing_pipeline_keeps_the_translation(tmp_path):
    out = tmp_path / "Show - S02E20.de.srt"
    with (
        patch("routes.subtitle_processor._run_pipeline_for_path", side_effect=RuntimeError("x")),
        patch("translator._helpers._fire_after_translate"),
    ):
        save_translated_output(_subs(), str(out), "srt")

    assert len(pysubs2.load(str(out)).events) == 3
