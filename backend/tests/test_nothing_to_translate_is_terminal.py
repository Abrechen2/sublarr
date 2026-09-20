"""A source with no dialogue will still have no dialogue in five hours.

Anime releases often ship a signs-and-songs track: karaoke romaji for the
opening, typeset signs, and no spoken dialogue at all. Measured on the
reference install, ``A Certain Scientific Railgun`` S02E13 carries 7 856 events
and **zero** in a dialog style — every one of them ``OPRomaji``, ``RomajiED``
or ``Sign-*``.

The translator recognises that correctly and reports "No dialog lines found".
What went wrong is what happened next: the automation queue booked it as a
failure and walked the backoff ladder, so 64 such entries burned up to ten
attempts each on an answer that cannot change. Each attempt costs a probe and a
file read for the same verdict.

``_fallback_translate_file`` already draws the right line in a comment — a
failed translation is "an environment fault (LLM down, quota), not a property
of the item". A source without dialogue is exactly a property of the item.
"""

from __future__ import annotations

import pytest


def _signs_only(tmp_path):
    """An ASS whose every style is karaoke or signs, like the real ones."""
    import pysubs2

    subs = pysubs2.SSAFile()
    for name in ("OPRomaji", "RomajiED", "Sign-EpisodeTitle"):
        subs.styles[name] = pysubs2.SSAStyle()
    for n, style in enumerate(("OPRomaji", "RomajiED", "Sign-EpisodeTitle")):
        subs.events.append(
            pysubs2.SSAEvent(
                start=n * 1000, end=n * 1000 + 900, style=style, text=f"kimi no na wa {n}"
            )
        )
    path = tmp_path / "Show.eng.ass"
    subs.save(str(path))
    return path


def test_the_flow_says_why_it_produced_nothing(tmp_path, app_ctx):
    """The reason has to be machine-readable, not a sentence to match on."""
    pytest.importorskip("pysubs2")
    from translator.ass_flow import _translate_external_ass

    result = _translate_external_ass(
        str(tmp_path / "video.mkv"),
        str(_signs_only(tmp_path)),
        target_language="de",
        source_language="en",
    )

    assert result["success"] is False
    assert result["reason"] == "no_translatable_dialogue", result


def test_an_ordinary_failure_carries_no_such_reason(tmp_path, app_ctx, monkeypatch):
    """The distinction is the point: an outage must stay retryable."""
    pytest.importorskip("pysubs2")
    import pysubs2

    import translator.core as _core
    from translator.ass_flow import _translate_external_ass

    subs = pysubs2.SSAFile()
    subs.styles["Default"] = pysubs2.SSAStyle()
    subs.events.append(pysubs2.SSAEvent(start=0, end=1000, style="Default", text="Good morning."))
    src = tmp_path / "Show.eng.ass"
    subs.save(str(src))

    def _backend_down(*_args, **_kwargs):
        raise RuntimeError("All backends failed")

    monkeypatch.setattr(_core._pkg(), "_translate_with_manager", _backend_down)

    result = _translate_external_ass(
        str(tmp_path / "video.mkv"), str(src), target_language="de", source_language="en"
    )

    assert result["success"] is False
    assert result.get("reason") is None, "an outage must not look like a property of the item"


def test_the_runner_stops_retrying_a_source_without_dialogue(monkeypatch, app_ctx):
    from db.models.core import SubtitleAutomationQueueEntry
    from services.subtitle_automation_runner import SubtitleAutomationRunner
    from translator.errors import NothingToTranslateError

    calls: dict = {"failed": [], "released": [], "done": []}

    claim = {
        "id": 51,
        "wanted_item_id": 9,
        "file_path": "/media/show.mkv",
        "target_language": "de",
        "task_type": SubtitleAutomationQueueEntry.TASK_SIDECAR_TRANSLATE,
        "attempt_count": 0,
    }

    class _Repo:
        def claim_next(self, now=None, task_types=None):
            return claim

        def mark_failed(self, entry_id, error="", next_retry_at=None):
            calls["failed"].append((entry_id, error, next_retry_at))

        def release_for_retry(self, entry_id, reason=""):
            calls["released"].append(entry_id)

        def mark_done(self, entry_id):
            calls["done"].append(entry_id)

    runner = SubtitleAutomationRunner(repo=_Repo())

    def _nothing(*_args, **_kwargs):
        raise NothingToTranslateError("the source carries no dialogue, only signs and songs")

    monkeypatch.setattr(runner, "_translate_sidecar", _nothing)

    assert runner.process_one() is True

    assert calls["failed"], "the entry was not closed out at all"
    _entry, error, next_retry_at = calls["failed"][0]
    assert next_retry_at is None, "a source without dialogue was scheduled for another attempt"
    assert "dialogue" in error


def test_an_environment_fault_is_still_retried(monkeypatch, app_ctx):
    """The non-regression that matters: an outage must keep its backoff."""
    from db.models.core import SubtitleAutomationQueueEntry
    from services.subtitle_automation_runner import SubtitleAutomationRunner

    calls: dict = {"failed": []}

    claim = {
        "id": 52,
        "wanted_item_id": 10,
        "file_path": "/media/show.mkv",
        "target_language": "de",
        "task_type": SubtitleAutomationQueueEntry.TASK_SIDECAR_TRANSLATE,
        "attempt_count": 0,
    }

    class _Repo:
        def claim_next(self, now=None, task_types=None):
            return claim

        def mark_failed(self, entry_id, error="", next_retry_at=None):
            calls["failed"].append((entry_id, error, next_retry_at))

        def release_for_retry(self, entry_id, reason=""):
            pass

        def mark_done(self, entry_id):
            pass

    runner = SubtitleAutomationRunner(repo=_Repo())

    def _outage(*_args, **_kwargs):
        raise RuntimeError("All backends failed. Last error: HTTPConnectionPool")

    monkeypatch.setattr(runner, "_translate_sidecar", _outage)
    runner.process_one()

    assert calls["failed"], "the outage was not recorded"
    _entry, _error, next_retry_at = calls["failed"][0]
    assert next_retry_at is not None, "an outage must stay on the backoff ladder"


def test_the_bridge_translates_the_reason_into_the_exception(monkeypatch, app_ctx):
    """The queue only ever sees exceptions, so the reason has to become one."""
    from services.subtitle_automation_runner import SubtitleAutomationRunner
    from translator.errors import NothingToTranslateError

    runner = SubtitleAutomationRunner()

    monkeypatch.setattr(
        "db.wanted.get_wanted_item",
        lambda item_id: {"id": item_id, "target_language": "de", "file_path": "/media/show.mkv"},
    )
    monkeypatch.setattr(
        "wanted_search.process._fallback_translate_file",
        lambda ctx: {
            "wanted_id": 9,
            "status": "failed",
            "error": "No dialog lines found in external ASS",
            "reason": "no_translatable_dialogue",
        },
    )

    with pytest.raises(NothingToTranslateError):
        runner._translate_sidecar(9, "/media/show.mkv", "de")
