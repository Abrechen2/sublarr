"""The per-line quality pass must stop when the scheduler asks it to.

Prod 2026-09-17, run ``253d42bc``: asked to stop at 22:08:10, reached its next
check point at 23:19:28 — 71 minutes later, against a 900 s grace, and was
recorded ``timeout_abandoned``. The abort event is only read between queue
items, and one item contains a whole translation *plus* this loop, which calls
the LLM once per line and up to twice more per weak line.

``translator/quality.py`` had no abort check at all, and its retry handler
catches ``Exception`` broadly — so even a check placed inside it would have
been swallowed rather than ending the run.
"""

from __future__ import annotations

import threading

import pytest

from services.scheduler import cancellation
from translator.errors import TranslationAbortedError


@pytest.fixture()
def stop_event():
    """Bind a scheduler stop event to this thread, as a tick's worker does."""
    event = threading.Event()
    token = cancellation.activate(event)
    try:
        yield event
    finally:
        cancellation.deactivate(token)


class _CountingManager:
    """Stands in for the translation manager, counting LLM round trips."""

    def __init__(self, stop_after=None, stop_event=None, score=10):
        self.eval_calls = 0
        self.translate_calls = 0
        self._stop_after = stop_after
        self._stop_event = stop_event
        self._score = score

    def evaluate_line_quality(self, src, trans, source_lang, target_lang, chain):
        self.eval_calls += 1
        if self._stop_after is not None and self.eval_calls >= self._stop_after:
            # The scheduler's timeout fires mid-file, exactly as on prod.
            self._stop_event.set()
        return self._score

    def translate_with_fallback(self, lines, source_lang, target_lang, chain, glossary):
        self.translate_calls += 1
        from translation.base import TranslationResult

        return TranslationResult(translated_lines=["neu"], backend_name="stub", success=True)


@pytest.fixture()
def patched_manager(monkeypatch):
    def _install(manager):
        import translation

        monkeypatch.setattr(translation, "get_translation_manager", lambda: manager)
        return manager

    return _install


def test_abort_before_a_line_stops_the_loop(stop_event, patched_manager):
    from translator.quality import _evaluate_and_retry_lines

    manager = patched_manager(_CountingManager(stop_after=3, stop_event=stop_event))
    lines = [f"line {n}" for n in range(200)]

    with pytest.raises(TranslationAbortedError):
        _evaluate_and_retry_lines(
            lines, list(lines), "en", "de", ["ollama"], None, threshold=35, max_retries=1
        )

    assert manager.eval_calls < 10, (
        f"kept scoring after the stop request: {manager.eval_calls} of {len(lines)} lines"
    )


def test_abort_is_not_swallowed_by_the_retry_handler(stop_event, patched_manager):
    """The retry's ``except Exception`` must let cancellation through.

    Scores below the threshold send every line into the retry branch, which is
    where a naive check would be caught and turned into "break".
    """
    from translator.quality import _evaluate_and_retry_lines

    manager = patched_manager(_CountingManager(stop_after=1, stop_event=stop_event, score=0))
    lines = [f"line {n}" for n in range(50)]

    with pytest.raises(TranslationAbortedError):
        _evaluate_and_retry_lines(
            lines, list(lines), "en", "de", ["ollama"], None, threshold=35, max_retries=2
        )

    assert manager.translate_calls <= 1, (
        f"kept retranslating after the stop request: {manager.translate_calls}"
    )


def test_without_an_abort_the_loop_completes(patched_manager):
    """The guard must not end runs that nobody asked to stop."""
    from translator.quality import _evaluate_and_retry_lines

    manager = patched_manager(_CountingManager(score=90))
    lines = [f"line {n}" for n in range(20)]

    final, scores = _evaluate_and_retry_lines(
        lines, list(lines), "en", "de", ["ollama"], None, threshold=35, max_retries=1
    )

    assert len(final) == 20
    assert scores == [90] * 20
    assert manager.eval_calls == 20


def test_ass_flow_lets_cancellation_through(monkeypatch, tmp_path, app_ctx):
    """A wrapper that turns the abort into a failure result spends a retry.

    ``_translate_external_ass`` catches ``Exception`` and returns a failure
    result, which the runner reads as "this item failed" — it applies backoff
    instead of taking the ``release_for_retry()`` branch cancellation is meant
    to reach.
    """
    pytest.importorskip("pysubs2")
    import pysubs2

    import translator.core as _core
    from translator.ass_flow import _translate_external_ass

    src = tmp_path / "source.ass"
    subs = pysubs2.SSAFile()
    subs.styles["Default"] = pysubs2.SSAStyle()
    subs.events.append(pysubs2.SSAEvent(start=0, end=1000, style="Default", text="Hallo"))
    subs.save(str(src))

    def _abort(*_args, **_kwargs):
        raise TranslationAbortedError("asked to stop")

    monkeypatch.setattr(_core._pkg(), "_translate_with_manager", _abort)

    with pytest.raises(TranslationAbortedError):
        _translate_external_ass(
            str(tmp_path / "video.mkv"), str(src), target_language="de", source_language="en"
        )


def test_srt_flow_lets_cancellation_through(monkeypatch, tmp_path, app_ctx):
    """Same link, the SRT side of the same fork."""
    import translator.core as _core
    from translator.srt_flow import translate_srt_from_file

    src = tmp_path / "source.srt"
    src.write_text("1\n00:00:01,000 --> 00:00:02,000\nHallo\n", encoding="utf-8")

    def _abort(*_args, **_kwargs):
        raise TranslationAbortedError("asked to stop")

    # Resolved through the translator.core namespace at call time, which is
    # the module-namespace trick both flows document at the top of the file.
    monkeypatch.setattr(_core, "_translate_srt", _abort)

    with pytest.raises(TranslationAbortedError):
        translate_srt_from_file(
            str(tmp_path / "video.mkv"), str(src), target_language="de", source_language="en"
        )


def test_the_runner_requeues_instead_of_spending_an_attempt(monkeypatch, app_ctx):
    """The last link: cancellation must reach release_for_retry(), not backoff.

    ``_fallback_translate_file`` reports failure by *returning* a dict, and its
    own ``except Exception`` used to convert the abort into one of those — so
    the runner saw an ordinary failure, spent the item's attempt and applied
    backoff for work that was never tried.
    """
    from services.subtitle_automation_runner import SubtitleAutomationRunner

    calls = {"released": [], "failed": []}

    from db.models.core import SubtitleAutomationQueueEntry

    claim = {
        "id": 77,
        "wanted_item_id": 5,
        "file_path": "/media/show.de.ass",
        "target_language": "de",
        "task_type": SubtitleAutomationQueueEntry.TASK_SIDECAR_TRANSLATE,
        "attempt_count": 2,
    }

    class _Repo:
        def claim_next(self, now=None, task_types=None):
            return claim

        def release_for_retry(self, entry_id, reason=""):
            calls["released"].append((entry_id, reason))

        def mark_failed(self, entry_id, error="", next_retry_at=None):
            calls["failed"].append((entry_id, error))

        def mark_done(self, entry_id):
            calls["failed"].append((entry_id, "mark_done"))

    runner = SubtitleAutomationRunner(repo=_Repo())

    def _abort(*_args, **_kwargs):
        raise TranslationAbortedError("asked to stop after scoring 12 of 640 line(s)")

    monkeypatch.setattr(runner, "_translate_sidecar", _abort)

    assert runner.process_one() is True

    assert calls["released"], "cancellation did not reach release_for_retry()"
    assert not calls["failed"], f"the item was charged for the stop: {calls['failed']}"
