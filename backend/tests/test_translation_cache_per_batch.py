"""A translation that dies partway must keep the batches it finished.

`_store_translations_in_cache` used to run once, after the whole file. A run
that stopped at batch 9 of 25 — a line-count mismatch, a container restart, a
scheduler timeout — cached nothing, so the next attempt paid for all nine
again.

Prod 2026-08-16 made the cost concrete: 176 failed translation jobs against
160 successful ones in 24 hours, with failures observed as deep as batch 150.
Every one of those discarded everything before it. And since the same day's
release stopped recording a failed translation as finished, those files are
now correctly retried — which doubles the bill for throwing the work away.

Caching per batch also makes the existing translation memory the resume
mechanism: no progress column, no partial file on disk, no new state.
"""

from __future__ import annotations

import pytest

from translation.base import TranslationResult


class _FailAtChunk:
    """Echoes ``T_<line>`` per line, but fails once it reaches chunk N."""

    def __init__(self, fail_on_call: int) -> None:
        self.fail_on_call = fail_on_call
        self.calls = 0

    def translate_with_fallback(
        self,
        lines,
        source_lang,
        target_lang,
        fallback_chain,
        glossary_entries=None,
        *,
        lookback=None,
        lookahead=None,
    ) -> TranslationResult:
        self.calls += 1
        if self.calls == self.fail_on_call:
            return TranslationResult(
                success=False,
                translated_lines=[],
                backend_name="fake",
                error="ollama returned 29 lines after retry, expected 15",
            )
        return TranslationResult(
            success=True,
            translated_lines=[f"T_{line}" for line in lines],
            backend_name="fake",
            response_time_ms=10,
            characters_used=sum(len(line) for line in lines),
            error=None,
        )


@pytest.fixture
def stored(monkeypatch):
    """Capture everything handed to the translation memory."""
    captured: list[tuple[list[str], list[str]]] = []

    def _capture(source_lines, translated_lines, source_lang, target_lang, backend=None):
        captured.append((list(source_lines), list(translated_lines)))

    import translator.manager as mod

    monkeypatch.setattr(mod, "_store_translations_in_cache", _capture)
    return captured


@pytest.fixture
def no_context(monkeypatch):
    """Keep chunk boundaries simple — context windows are not what this tests."""
    from config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "translation_context_enabled", False, raising=False)
    return s


def _lines(n: int) -> list[str]:
    return [f"line{i}" for i in range(n)]


class TestPartialWorkSurvivesAFailure:
    def test_finished_batches_are_cached_before_the_failure(self, stored, no_context):
        """The whole point: batch 3 dying must not cost batches 1 and 2."""
        from translator.manager import _translate_in_batches

        manager = _FailAtChunk(fail_on_call=3)

        with pytest.raises(RuntimeError):
            _translate_in_batches(manager, _lines(10), "en", "de", ["fake"], None, 3)

        cached_sources = [line for call in stored for line in call[0]]
        assert cached_sources == ["line0", "line1", "line2", "line3", "line4", "line5"], (
            "the two batches that completed before the failure must be in the cache"
        )

    def test_the_cached_translations_belong_to_their_lines(self, stored, no_context):
        from translator.manager import _translate_in_batches

        manager = _FailAtChunk(fail_on_call=3)

        with pytest.raises(RuntimeError):
            _translate_in_batches(manager, _lines(10), "en", "de", ["fake"], None, 3)

        for sources, translations in stored:
            assert translations == [f"T_{s}" for s in sources], "pairing must not slip"

    def test_nothing_from_the_failed_batch_is_cached(self, stored, no_context):
        """A batch that returned the wrong line count is not usable memory."""
        from translator.manager import _translate_in_batches

        manager = _FailAtChunk(fail_on_call=3)

        with pytest.raises(RuntimeError):
            _translate_in_batches(manager, _lines(10), "en", "de", ["fake"], None, 3)

        cached_sources = [line for call in stored for line in call[0]]
        assert "line6" not in cached_sources
        assert "line7" not in cached_sources


class TestTheHappyPathIsUnchanged:
    def test_every_line_still_reaches_the_cache(self, stored, no_context):
        from translator.manager import _translate_in_batches

        manager = _FailAtChunk(fail_on_call=0)  # never fails

        translated, _ = _translate_in_batches(manager, _lines(10), "en", "de", ["fake"], None, 3)

        assert translated == [f"T_{line}" for line in _lines(10)]
        cached_sources = [line for call in stored for line in call[0]]
        assert cached_sources == _lines(10), "no line may be lost by moving the write"

    def test_a_single_batch_file_is_cached_too(self, stored, no_context):
        """Files below one batch take a separate code path — it caches as well."""
        from translator.manager import _translate_in_batches

        manager = _FailAtChunk(fail_on_call=0)

        _translate_in_batches(manager, _lines(2), "en", "de", ["fake"], None, 15)

        cached_sources = [line for call in stored for line in call[0]]
        assert cached_sources == ["line0", "line1"]

    def test_no_line_is_written_to_the_cache_twice(self, stored, no_context):
        """The bulk write after the loop has to go, or every line is stored twice."""
        from translator.manager import _translate_in_batches

        manager = _FailAtChunk(fail_on_call=0)

        _translate_in_batches(manager, _lines(9), "en", "de", ["fake"], None, 3)

        cached_sources = [line for call in stored for line in call[0]]
        assert len(cached_sources) == len(set(cached_sources)) == 9
