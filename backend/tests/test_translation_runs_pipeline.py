"""A saved translation goes through the processing pipeline like a download.

Prod 2026-10-30, Slime S02E20: HI removal was on, yet the German translation
of an English CC track kept "[HERMES stöhnt]" and 140 more markers — only
provider downloads ran the pipeline.
"""

import json
from unittest.mock import MagicMock, patch

import pysubs2

from translator._helpers import process_translated_output

SETTINGS = MagicMock(
    auto_process_common_fixes=False,
    auto_process_hi_removal=True,
    auto_process_credit_removal=False,
)
LINES = ((1000, "[HERMES stöhnt]"), (3000, "Nein, Sir Gabiru..."), (5000, "[lacht] Ja."))


def _write(path):
    subs = pysubs2.SSAFile()
    for start, text in LINES:
        subs.events.append(pysubs2.SSAEvent(start=start, end=start + 1500, text=text))
    subs.save(str(path))


def _process(out, series_row=None, wanted=()):
    with (
        patch("routes.subtitle_processor.get_settings", return_value=SETTINGS),
        patch("services.standalone_owner_keys.get_row", return_value=series_row),
        patch("db.wanted.get_wanted_items_by_path", side_effect=lambda p: list(wanted)),
    ):
        process_translated_output(str(out))


def test_hi_markers_leave_a_saved_translation(tmp_path):
    out = tmp_path / "Show - S02E20.de.srt"
    _write(out)

    _process(out)

    assert [e.text for e in pysubs2.load(str(out)).events] == ["Nein, Sir Gabiru...", "Ja."]


def test_the_quality_scores_stay_on_their_cues(tmp_path):
    """Codex review 2026-10-30: a removed cue left the scores one off, and the
    editor drops scores whose count does not match the cues."""
    out = tmp_path / "Show - S02E20.de.srt"
    _write(out)
    (tmp_path / "Show - S02E20.de.srt.quality.json").write_text(json.dumps([90, 80, 70]))

    _process(out)

    assert json.loads((tmp_path / "Show - S02E20.de.srt.quality.json").read_text()) == [80, 70]


def test_a_series_override_is_honoured(tmp_path):
    """Codex review 2026-10-30: the series' own "no HI removal" was ignored."""
    out = tmp_path / "Show - S02E20.de.srt"
    _write(out)
    (tmp_path / "Show - S02E20.mkv").write_bytes(b"")
    row = MagicMock(processing_config=json.dumps({"hi_removal": False}))

    _process(out, series_row=row, wanted=[{"sonarr_series_id": 7}])

    assert len(pysubs2.load(str(out)).events) == 3


def test_a_failing_pipeline_keeps_the_translation(tmp_path):
    out = tmp_path / "Show - S02E20.de.srt"
    _write(out)
    with patch("routes.subtitle_processor._run_pipeline_for_path", side_effect=RuntimeError("x")):
        process_translated_output(str(out))

    assert len(pysubs2.load(str(out)).events) == 3
