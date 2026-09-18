"""A file that kept English lines must say so, not just log it.

An event with real dialogue on both sides of a drawing cannot be put back
together from one translated string, so it is left alone. That is the right
call — the alternative corrupts both halves — but rc.10's version only wrote an
INFO line and still reported success. The sandbox VM's objection stands: the
user gets what looks like a finished target language with English remnants in
it, and nothing in the result says which lines or where.

So the outcome carries the count and the events themselves, the log says it at
warning level, and the decision log — the thing a user actually opens to ask
"what happened to this item" — shows it.
"""

from __future__ import annotations

import pytest


def _subs_with(texts):
    import pysubs2

    subs = pysubs2.SSAFile()
    subs.styles["Default"] = pysubs2.SSAStyle()
    for n, text in enumerate(texts):
        subs.events.append(
            pysubs2.SSAEvent(start=n * 1000, end=n * 1000 + 900, style="Default", text=text)
        )
    return subs


def test_an_interleaved_event_is_reported_with_its_place():
    pytest.importorskip("pysubs2")
    from translator.ass_flow import _collect_translatable_events

    subs = _subs_with(["Good morning.", r"Good{\p1}m 0 0{\p0}morning."])
    *_rest, untranslated = _collect_translatable_events(subs, {"Default"})

    assert len(untranslated) == 1, untranslated
    entry = untranslated[0]
    assert entry["index"] == 1
    assert entry["start_ms"] == 1000
    assert entry["end_ms"] == 1900
    assert "dialogue" in entry["reason"]
    # The text is what lets a user recognise the line in their player.
    assert "morning" in entry["text"]


def test_a_pure_drawing_is_not_reported_as_untranslated():
    """Skipping geometry loses nothing; saying so would be noise."""
    pytest.importorskip("pysubs2")
    from translator.ass_flow import _collect_translatable_events

    subs = _subs_with(["Good morning.", r"{\p1}m 0 0 l 10 10"])
    *_rest, untranslated = _collect_translatable_events(subs, {"Default"})

    assert untranslated == []


def test_the_flow_reports_it_in_its_stats(tmp_path, app_ctx, monkeypatch):
    pytest.importorskip("pysubs2")
    import pysubs2

    import translator.core as _core
    from translator.ass_flow import _translate_external_ass

    src = tmp_path / "source.ass"
    _subs_with(["Good morning.", r"Good{\p1}m 0 0{\p0}morning."]).save(str(src))

    class _Result:
        backend_name = "stub"
        success = True

    def _fake_translate(lines, **_kwargs):
        return ["Guten Morgen."] * len(lines), _Result()

    monkeypatch.setattr(_core._pkg(), "_translate_with_manager", _fake_translate)
    monkeypatch.setattr(_core._pkg(), "_get_quality_config", lambda: (False, 35, 1))

    result = _translate_external_ass(
        str(tmp_path / "video.mkv"), str(src), target_language="de", source_language="en"
    )

    stats = result["stats"]
    assert stats["untranslated"] == 1
    assert len(stats["untranslated_events"]) == 1
    assert stats["untranslated_events"][0]["index"] == 1


def test_it_warns_rather_than_mentioning_it_in_passing(caplog):
    """An INFO line among thousands is not "reported"."""
    import logging

    pytest.importorskip("pysubs2")
    from translator.ass_flow import _collect_translatable_events

    subs = _subs_with(["Good morning.", r"Good{\p1}m 0 0{\p0}morning."])
    with caplog.at_level(logging.WARNING, logger="translator.ass_flow"):
        _collect_translatable_events(subs, {"Default"})

    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warnings, "the partial translation was not raised above INFO"
    assert "1" in warnings[0].getMessage()


def test_the_decision_log_carries_it():
    """The modal a user opens to ask what happened has to show it."""
    pytest.importorskip("pysubs2")
    import decision_log
    from translator.ass_flow import _collect_translatable_events

    log = decision_log.start({"id": 7, "title": "Probe"})
    try:
        subs = _subs_with(["Good morning.", r"Good{\p1}m 0 0{\p0}morning."])
        _collect_translatable_events(subs, {"Default"})
        payload = log.to_dict()
    finally:
        decision_log.finish()

    partial = payload.get("partial_translation")
    assert partial, "the decision log says nothing about the untranslated line"
    assert partial["count"] == 1
    assert partial["events"][0]["index"] == 1


def test_nothing_is_recorded_when_everything_was_translated():
    pytest.importorskip("pysubs2")
    import decision_log
    from translator.ass_flow import _collect_translatable_events

    log = decision_log.start({"id": 8, "title": "Probe"})
    try:
        _collect_translatable_events(_subs_with(["Good morning."]), {"Default"})
        payload = log.to_dict()
    finally:
        decision_log.finish()

    assert "partial_translation" not in payload


def test_the_activity_log_shows_it_for_the_automation_path(tmp_path, app_ctx, monkeypatch):
    """The decision log only exists inside process_wanted_item.

    Most translations reach the translate step through the subtitle-automation
    queue, which calls it directly — so reporting only there would put the note
    everywhere except where the dominant path can be seen.
    """
    pytest.importorskip("pysubs2")

    import translator.core as _core
    from translator.ass_flow import _translate_external_ass

    src = tmp_path / "source.ass"
    _subs_with(["Good morning.", r"Good{\p1}m 0 0{\p0}morning."]).save(str(src))

    recorded = []

    class _Result:
        backend_name = "stub"
        success = True

    def _fake_translate(lines, **_kwargs):
        return ["Guten Morgen."] * len(lines), _Result()

    import translator.ass_flow as ass_flow

    monkeypatch.setattr(_core._pkg(), "_translate_with_manager", _fake_translate)
    monkeypatch.setattr(_core._pkg(), "_get_quality_config", lambda: (False, 35, 1))
    monkeypatch.setattr(
        ass_flow,
        "_report_partial_translation",
        lambda path, events: recorded.append((path, events)),
    )

    _translate_external_ass(
        str(tmp_path / "video.mkv"), str(src), target_language="de", source_language="en"
    )

    assert recorded, "nothing was reported outside the decision log"
    _path, events = recorded[0]
    assert len(events) == 1 and events[0]["index"] == 1


def test_a_fully_translated_file_records_no_activity(app_ctx):
    """No finding, no entry — the tab must not fill with non-events."""
    from translator.ass_flow import _report_partial_translation

    calls = []
    try:
        import db.activity as activity_module

        original = activity_module.log_activity
        activity_module.log_activity = lambda *a, **k: calls.append((a, k))
        _report_partial_translation("/media/show.de.ass", [])
    finally:
        activity_module.log_activity = original

    assert calls == []
