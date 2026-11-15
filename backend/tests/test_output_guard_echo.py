"""translator.output_guard — a batch that comes back as its own input is not a
translation, even when source and target share a writing system.

Benchmark 2026-11-14 (gemma3:12b, Mushoku S01E17 de → en): one batch came
back with ten of its fifteen lines still German, byte for byte. The count
check passed, there was no filler, and the script check has no opinion
between two Latin languages — so the echo would have gone to disk and into
the translation memory.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from translator.manager import _verify_batch
from translator.output_guard import find_untranslated_echo

# The batch from the benchmark, lines 45-59, with what the model returned.
BENCH_SOURCE = [
    "Hm, Geese? Lag ich damit falsch?",
    "Natürlich.",
    "Du liegst immer falsch.",
    "Geese!",
    "Du warst noch nie auf dem Dämonenkontinent, oder?",
    "Na und?",
    "Wie du weißt, wurde ich dort geboren.",
    "Wenn du mich fragst, unterschätzt du den Kontinent gewaltig.",
    "Und was genau unterschätze ich?",
    "Ihr verhätschelten Zentralkontinentler",
    "kriegt es einfach nicht in eure Köpfe.",
    "Außerhalb der Städte wartet ein einziges Brachland.",
    "Mittags ist es verdammt heiß.",
    "Abends schweinekalt. Für Feuerholz muss man sich mit Monstern rumschlagen.",
    "Du hast Durst? Pech, es gibt kaum Wasser und es regnet nie.",
]
BENCH_OUTPUT = [
    "Hm, Geese? Was, lag ich damit falsch?",
    "Natürlich.",
    "Du liegst immer falsch.",
    "Geese!",
    "Du warst noch nie auf dem Dämonenkontinent, oder?",
    "So what?",
    "Wie du weißt, wurde ich dort geboren.",
    "Wenn du mich fragst, unterschätzt du den Kontinent gewaltig.",
    "Und was genau unterschätze ich?",
    "Ihr verwöhnten Zentralkontinentler",
    "kriegt es einfach nicht in eure Köpfe.",
    "Außerhalb der Städte wartet ein einziges Brachland.",
    "Mittags ist es verdammt heiß.",
    "Abends schweinekalt. Für Feuerholz muss man sich mit Monstern rumschlagen.",
    "Du hast Durst? Pech, es gibt kaum Wasser und es regnet nie.",
]
TRANSLATED = [
    "Of course.",
    "You're always wrong.",
    "You've never been to the Demon Continent, have you?",
    "As you know, I was born there.",
    "If you ask me, you seriously underestimate the continent.",
]
GERMAN_SOURCE = [
    "Natürlich.",
    "Du liegst immer falsch.",
    "Du warst noch nie auf dem Dämonenkontinent, oder?",
    "Wie du weißt, wurde ich dort geboren.",
    "Wenn du mich fragst, unterschätzt du den Kontinent gewaltig.",
]


class TestFindUntranslatedEcho:
    def test_the_echoed_benchmark_batch_is_flagged(self):
        assert find_untranslated_echo(BENCH_SOURCE, BENCH_OUTPUT) is not None

    def test_a_translated_batch_passes(self):
        assert find_untranslated_echo(GERMAN_SOURCE, TRANSLATED) is None

    def test_names_and_exclamations_left_as_they_are_do_not_count(self):
        # Lines a correct translation keeps unchanged: names, calls, a title.
        source = [
            "Papa … Papa!",
            "Zenith, Lillia, Aisha …",
            "Paul …",
            "Rudi …",
            "Norn …",
            "Vera! Shera!",
        ]
        assert find_untranslated_echo(source, list(source)) is None

    def test_one_kept_line_in_a_translated_batch_passes(self):
        source = GERMAN_SOURCE + ["Mushoku Tensei: Jobless Reincarnation"]
        output = TRANSLATED + ["Mushoku Tensei: Jobless Reincarnation"]
        assert find_untranslated_echo(source, output) is None

    def test_a_small_batch_gives_no_opinion(self):
        # Too few lines to tell an echo from lines that legitimately stay:
        # refusing here would end in a single line that can never pass.
        source = GERMAN_SOURCE[1:3]
        assert find_untranslated_echo(source, list(source)) is None

    def test_markup_and_case_differences_still_count_as_an_echo(self):
        output = [
            line.upper() if i % 2 else f"{{\\i1}}{line}" for i, line in enumerate(BENCH_SOURCE)
        ]
        assert find_untranslated_echo(BENCH_SOURCE, output) is not None


class TestVerifyBatchEcho:
    def _result(self, lines):
        return SimpleNamespace(translated_lines=list(lines), success=True)

    def test_an_echoed_batch_fails(self):
        with pytest.raises(RuntimeError, match="untranslated"):
            _verify_batch(
                self._result(BENCH_OUTPUT),
                len(BENCH_OUTPUT),
                "Batch 4",
                target_lang="en",
                source_lines=BENCH_SOURCE,
            )

    def test_a_translated_batch_passes(self):
        _verify_batch(
            self._result(TRANSLATED),
            len(TRANSLATED),
            "Batch 1",
            target_lang="en",
            source_lines=GERMAN_SOURCE,
        )

    def test_source_lines_are_optional_for_old_callers(self):
        _verify_batch(self._result(BENCH_OUTPUT), len(BENCH_OUTPUT), "Batch 4", target_lang="en")


class _EchoesFirstRequest:
    """Returns the first request unchanged, translates every later one.

    The benchmark echo was a one-off: the same lines in a fresh request came
    back translated.
    """

    def __init__(self) -> None:
        self.sizes: list[int] = []

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
    ):
        from translation.base import TranslationResult

        self.sizes.append(len(lines))
        out = list(lines) if len(self.sizes) == 1 else [f"EN {line}" for line in lines]
        return TranslationResult(
            success=True, translated_lines=out, backend_name="fake", error=None
        )


def test_an_echoed_batch_is_retranslated_and_never_cached(monkeypatch):
    import translator.manager as mod
    from config import get_settings

    cached: list[list[str]] = []
    monkeypatch.setattr(
        mod, "_store_translations_in_cache", lambda src, out, *a, **k: cached.append(list(out))
    )
    monkeypatch.setattr(get_settings(), "translation_context_enabled", False, raising=False)
    manager = _EchoesFirstRequest()

    translated, _ = mod._translate_in_batches(
        manager, BENCH_SOURCE, "de", "en", ["fake"], None, batch_size=15
    )

    assert translated == [f"EN {line}" for line in BENCH_SOURCE]
    assert manager.sizes[0] == 15 and len(manager.sizes) > 1
    assert all(line.startswith("EN ") for batch in cached for line in batch)
