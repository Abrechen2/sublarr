r"""A correct line count does not mean the lines are against the right sources.

Found on 2026-08-24 while reading translation quality data, and invisible to
every guard the pipeline had. gemma3:12b split one source line across two
output lines and merged two others further down, so the batch came back with
exactly the 15 lines that were asked for while lines 0 to 6 sat one place too
late. On screen that is dialogue running out of sync, and because an accepted
batch is written to the translation memory it would be re-served on every
later hit.

The fixtures below are the measured output of that batch, not invented ones.
"""

import os

import pytest

from config import reload_settings
from db import close_db, init_db
from translation.base import TranslationContentError
from translation.llm_base import LineMisalignmentError, LLMBackend, LLMResponse
from translation.llm_utils import find_line_shift

HB = chr(92) + "N"  # literal ASS hard line break

# sakura_s01e13, batch 1 — the real source lines and gemma3:12b's real answer.
SAKURA_SOURCE = [
    "Oh, yeah... Lodging is a bit of a problem.",
    '"Episode 13: The Marionette\'s Banquet"',
    f"If we're going to hold an event that goes{HB}beyond Manoyama's normal capacity,",
    "we've got to think about that stuff, too.",
    '"Manoyama Tourism Center"',
]
SAKURA_SHIFTED = [
    f"Oh ja...{HB}",
    "Unterkünfte sind ein bisschen das Problem.",
    '"Folge 13: Das Marionettenfest"',
    f"Wenn wir ein Event veranstalten, das{HB}über Manoyamas normale Kapazität hinausgeht,",
    "müssen wir auch da ran.",
]
SAKURA_ALIGNED = [
    "Oh, ja... Die Unterkünfte sind etwas schwierig.",
    '"Episode 13: Das Festmahl der Marionette"',
    f"Wenn wir ein Event veranstalten wollen, das{HB}über die normale Kapazität "
    "von Manoyama hinausgeht,",
    "müssen wir auch darüber nachdenken.",
    '"Manoyama Tourismuszentrum"',
]


def test_the_measured_shift_is_found():
    assert find_line_shift(SAKURA_SOURCE, SAKURA_SHIFTED) == 1


def test_the_same_batch_translated_in_order_is_not_flagged():
    assert find_line_shift(SAKURA_SOURCE, SAKURA_ALIGNED) is None


def test_one_wandering_anchor_is_a_coincidence_not_a_shift():
    """Measured: over 11 aligned batches exactly one anchor ever moved."""
    source = ["Are you okay over there?", "We start at dawn.", "Nobody told me."]
    translated = [
        "Alles klar bei dir?",
        "Wir starten okay im Morgengrauen.",
        "Mir sagt keiner was.",
    ]

    assert find_line_shift(source, translated) is None


def test_a_token_on_several_source_lines_anchors_nothing():
    """It could be matched to any of its occurrences and would invent offsets."""
    source = ["Manoyama is quiet.", "Manoyama is loud.", "Manoyama sleeps."]
    translated = ["Manoyama ist laut.", "Manoyama schläft.", "Manoyama ist still."]

    assert find_line_shift(source, translated) is None


def test_a_length_mismatch_is_the_callers_line_count_failure():
    assert find_line_shift(["one", "two"], ["eins"]) is None


def test_a_single_line_batch_cannot_be_shifted():
    assert find_line_shift(["Only line."], ["Einzige Zeile."]) is None


def test_a_backwards_shift_reports_a_negative_offset():
    source = [
        "Nothing here.",
        "Ellenora is waiting.",
        "Chapter 12 begins.",
        "Manoyama is quiet.",
    ]
    translated = [
        "Ellenora wartet.",
        "Kapitel 12 beginnt.",
        "Manoyama ist still.",
        "Nichts hier.",
    ]

    assert find_line_shift(source, translated) == -1


# ---------------------------------------------------------------------------
# Wiring — a detector nobody calls fixes nothing.
# ---------------------------------------------------------------------------


@pytest.fixture()
def _app_context(tmp_path):
    from app import create_app

    os.environ["SUBLARR_DB_PATH"] = str(tmp_path / "align.db")
    os.environ["SUBLARR_API_KEY"] = ""
    os.environ["SUBLARR_LOG_LEVEL"] = "ERROR"
    reload_settings()
    app = create_app(testing=True)
    with app.app_context():
        init_db()
        yield
    close_db()
    for key in ("SUBLARR_DB_PATH", "SUBLARR_API_KEY", "SUBLARR_LOG_LEVEL"):
        os.environ.pop(key, None)


class _ShiftingBackend(LLMBackend):
    """Answers with shifted lines, then with whatever ``recovers`` says."""

    name = "shifting"
    display_name = "Shifting"
    config_fields = []
    default_model = "stub"
    cost_per_1m_tokens_in = 0
    cost_per_1m_tokens_out = 0
    recovers = True

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.calls = 0

    def _build_request(self, messages, max_tokens):
        return {"messages": messages}

    def _call_api(self, payload, timeout_s):
        return {}

    def _parse_response(self, raw):
        self.calls += 1
        if self.calls == 1 or not self.recovers:
            return self._respond(SAKURA_SHIFTED)
        return self._respond(SAKURA_ALIGNED)

    def _respond(self, translations):
        return LLMResponse(
            translations=list(translations),
            tokens_in=10,
            tokens_out=10,
            model="stub",
            finish_reason="stop",
            raw_latency_ms=1,
        )

    def health_check(self):
        return (True, "stub")

    def get_config_fields(self):
        return self.config_fields


def _register(backend_cls):
    from translation.concurrency import get_concurrency

    get_concurrency().register(backend_cls.name, 2)
    return backend_cls()


def test_a_shifted_batch_is_retried_and_the_aligned_retry_is_used(_app_context):
    backend = _register(_ShiftingBackend)

    result = backend.translate_batch(SAKURA_SOURCE, "en", "de")

    assert backend.calls == 2, "the shifted first answer should have been retried"
    assert result.translated_lines == SAKURA_ALIGNED


def test_a_shift_that_survives_the_retry_is_rejected(_app_context):
    backend = _register(_ShiftingBackend)
    backend.recovers = False

    with pytest.raises(LineMisalignmentError) as excinfo:
        backend.translate_batch(SAKURA_SOURCE, "en", "de")

    assert "+1" in str(excinfo.value)


def test_both_attempts_are_billed_when_the_batch_is_rejected(_app_context, monkeypatch):
    """The event row is written from the rejected response — it paid twice."""
    billed = {}

    def _capture(**kwargs):
        billed.update(kwargs)

    monkeypatch.setattr("translation.llm_base.write_translation_event", _capture)
    backend = _register(_ShiftingBackend)
    backend.recovers = False

    with pytest.raises(LineMisalignmentError):
        backend.translate_batch(SAKURA_SOURCE, "en", "de")

    assert billed["tokens_in"] == 20, "one attempt's tokens would be 10"
    assert billed["tokens_out"] == 20


def test_the_rejection_is_a_content_error_so_it_spares_the_breaker(_app_context):
    """A wrong-shaped answer is not a sick backend — the 1.13.3 rule."""
    assert issubclass(LineMisalignmentError, TranslationContentError)

    backend = _register(_ShiftingBackend)
    backend.recovers = False

    with pytest.raises(TranslationContentError):
        backend.translate_batch(SAKURA_SOURCE, "en", "de")


class _MisalignsLargeBatches:
    """Shifts any batch above ``limit`` lines, translates smaller ones straight.

    Stands in for the measured shape: the model splits and merges when it is
    handed a full batch, and stops doing it once the request is small enough to
    hold in one piece. Sits at the manager's seam rather than the backend's, so
    the split path is what is under test.
    """

    def __init__(self, limit: int) -> None:
        self.limit = limit
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
        if len(lines) > self.limit:
            return TranslationResult(
                success=False,
                translated_lines=[],
                backend_name="fake",
                error="fake returned lines shifted by +1 against their sources after retry",
            )
        return TranslationResult(
            success=True,
            translated_lines=[f"T_{line}" for line in lines],
            backend_name="fake",
            response_time_ms=10,
            characters_used=sum(len(line) for line in lines),
            error=None,
        )


def test_a_rejected_alignment_costs_the_batch_a_retry_not_the_episode(monkeypatch):
    """The rebase onto the splitting path changed what a rejection costs.

    On the branch this check was written against, a batch the retry could not
    straighten ended the file the way a count mismatch did. Master translates a
    batch it cannot deliver in halves instead, and a misalignment is a
    ``TranslationContentError`` like any other, so it reaches that path — the
    file completes and only the offending batch pays.
    """
    import translator.manager as mod
    from config import get_settings
    from translator.manager import _translate_in_batches

    monkeypatch.setattr(mod, "_store_translations_in_cache", lambda *a, **k: None)
    monkeypatch.setattr(get_settings(), "translation_context_enabled", False, raising=False)

    manager = _MisalignsLargeBatches(limit=8)
    lines = [f"line{i}" for i in range(30)]

    translated, _last = _translate_in_batches(
        manager, lines, "en", "de", ["fake"], None, batch_size=15
    )

    assert translated == [f"T_line{i}" for i in range(30)]
    assert 15 in manager.sizes, "the full batch must be tried before it is halved"
    assert 1 not in manager.sizes, "halving stops at the point the model can deliver"
