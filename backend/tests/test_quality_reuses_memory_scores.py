"""The quality pass must not re-score what it already scored.

Every line of a file costs one model round trip in the quality pass, plus up to
two more when it scores badly. For a file served entirely from the translation
memory that is hundreds of calls producing no new translation at all.

Skipping cache hits is only safe once the memory holds the *checked* text,
though, and it did not: ``_translate_in_batches`` writes each batch the moment
it is verified — before the quality pass runs — and the pass's improvements
were never written back. A cache hit therefore returned the unimproved line,
and skipping its evaluation would have quietly lowered the output quality of
every repeated line instead of merely making it cheaper.

So the two halves belong together: write the checked line and its score back,
and skip only lines that carry such a score.
"""

from __future__ import annotations

import os

import pytest

from config import reload_settings
from db import close_db, init_db


@pytest.fixture(autouse=True)
def _isolate_db(tmp_path):
    from app import create_app

    os.environ["SUBLARR_DB_PATH"] = str(tmp_path / "quality_memory.db")
    os.environ["SUBLARR_API_KEY"] = ""
    os.environ["SUBLARR_LOG_LEVEL"] = "ERROR"
    reload_settings()
    app = create_app(testing=True)
    with app.app_context():
        init_db()
        yield app
    close_db()
    for key in ("SUBLARR_DB_PATH", "SUBLARR_API_KEY", "SUBLARR_LOG_LEVEL"):
        os.environ.pop(key, None)


class _CountingManager:
    """Counts the model round trips the quality pass makes."""

    def __init__(self, score=90, improved=None):
        self.eval_calls = 0
        self.translate_calls = 0
        self._score = score
        self._improved = improved

    def evaluate_line_quality(self, src, trans, source_lang, target_lang, chain):
        self.eval_calls += 1
        if self._improved is not None and trans == self._improved:
            return 95
        return self._score

    def translate_with_fallback(self, lines, source_lang, target_lang, chain, glossary):
        self.translate_calls += 1
        from translation.base import TranslationResult

        return TranslationResult(
            translated_lines=[self._improved or lines[0]], backend_name="stub", success=True
        )


@pytest.fixture()
def use_manager(monkeypatch):
    def _install(manager):
        import translation

        monkeypatch.setattr(translation, "get_translation_manager", lambda: manager)
        return manager

    return _install


def _evaluate(lines, translated, threshold=35, retries=1):
    from translator.quality import _evaluate_and_retry_lines

    return _evaluate_and_retry_lines(
        lines, translated, "en", "de", ["ollama"], None, threshold=threshold, max_retries=retries
    )


def test_a_checked_line_is_written_back_with_its_score(_isolate_db, use_manager):
    """The memory has to end up holding what the quality pass produced."""
    from db.translation import lookup_quality_scores, store_translation_cache

    store_translation_cache("en", "de", "Good morning.", "Guten Tag.")
    manager = use_manager(_CountingManager(score=10, improved="Guten Morgen."))

    with _isolate_db.app_context():
        final, scores = _evaluate(["Good morning."], ["Guten Tag."])

        assert final == ["Guten Morgen."], "the improved line was not returned"
        stored = lookup_quality_scores("en", "de", ["Good morning."])
        assert stored == [("Guten Morgen.", 95)], stored
    assert manager.translate_calls == 1
    assert scores == [95]


def test_a_line_with_a_stored_score_is_not_evaluated_again(_isolate_db, use_manager):
    from db.translation import store_translation_cache

    with _isolate_db.app_context():
        store_translation_cache("en", "de", "Good morning.", "Guten Morgen.", quality_score=88)
        manager = use_manager(_CountingManager(score=90))

        final, scores = _evaluate(["Good morning."], ["Guten Morgen."])

        assert manager.eval_calls == 0, "the model was asked about an already-scored line"
        assert manager.translate_calls == 0
        assert final == ["Guten Morgen."]
        assert scores == [88], "the stored score must be reported, not invented"


def test_a_legacy_row_without_a_score_is_evaluated_once(_isolate_db, use_manager):
    """Rows written before this change carry no score and must still be checked."""
    from db.translation import lookup_quality_scores, store_translation_cache

    with _isolate_db.app_context():
        store_translation_cache("en", "de", "Good morning.", "Guten Morgen.")
        manager = use_manager(_CountingManager(score=77))

        _evaluate(["Good morning."], ["Guten Morgen."])
        assert manager.eval_calls == 1

        assert lookup_quality_scores("en", "de", ["Good morning."]) == [("Guten Morgen.", 77)]

        # Second run over the same line costs nothing.
        again = use_manager(_CountingManager(score=77))
        _, scores = _evaluate(["Good morning."], ["Guten Morgen."])
        assert again.eval_calls == 0
        assert scores == [77]


def test_a_stored_score_for_different_text_is_not_reused(_isolate_db, use_manager):
    """The score belongs to one translation, not to the source line."""
    from db.translation import store_translation_cache

    with _isolate_db.app_context():
        store_translation_cache("en", "de", "Good morning.", "Guten Morgen.", quality_score=88)
        manager = use_manager(_CountingManager(score=40))

        _, scores = _evaluate(["Good morning."], ["Ein anderer Satz."])

        assert manager.eval_calls == 1, "a different translation must be scored on its own"
        assert scores == [40]


def test_a_file_entirely_from_memory_costs_no_model_calls(_isolate_db, use_manager):
    from db.translation import store_translation_cache

    lines = [f"Line number {n}." for n in range(50)]
    translated = [f"Zeile Nummer {n}." for n in range(50)]

    with _isolate_db.app_context():
        for src, dst in zip(lines, translated):
            store_translation_cache("en", "de", src, dst, quality_score=80)
        manager = use_manager(_CountingManager(score=80))

        final, scores = _evaluate(lines, translated)

        assert manager.eval_calls == 0
        assert manager.translate_calls == 0
        assert final == translated
        assert scores == [80] * 50


def test_the_memory_being_disabled_changes_nothing(_isolate_db, use_manager, monkeypatch):
    """Without a memory there is nothing to reuse and nothing to write back."""
    import translator.quality as quality_module

    monkeypatch.setattr(quality_module, "_memory_enabled", lambda: False)
    manager = use_manager(_CountingManager(score=90))

    with _isolate_db.app_context():
        final, scores = _evaluate(["Good morning."], ["Guten Morgen."])

    assert manager.eval_calls == 1
    assert final == ["Guten Morgen."]
    assert scores == [90]
