"""The output lines must map onto the source lines they belong to.

Three defects hide behind a single "line count mismatch", and they were told
apart by reading 65 recorded gemma3:12b batches rather than by reasoning:

* the model writes a hard break and then a real newline, so the marker ends up
  alone on a line of its own -- 29 such lines across 3 of the 65 batches, and
  two batches came back with 29 lines instead of 15 purely because of it;
* the same habit at the end of a content line puts the rest of that
  translation on the following line;
* and sometimes the model genuinely merges two source events that carry one
  sentence, which no parser can undo.

Only the first two are repairable here. The third is a count mismatch and stays
one.
"""

from __future__ import annotations

from decimal import Decimal

from translation.llm_base import LLMBackend, LLMResponse
from translation.llm_utils import repair_line_mapping

HARD_BREAK = chr(92) + "N"
SOFT_BREAK = chr(92) + "n"


class _RecordingBackend(LLMBackend):
    """Minimal LLM backend that replays a fixed set of raw model lines."""

    name = "recording"
    cost_per_1m_tokens_in = Decimal("0")
    cost_per_1m_tokens_out = Decimal("0")
    default_model = "recording"

    def __init__(self, raw_lines: list[str]):
        self._raw_lines = raw_lines

    def _build_request(self, messages: list[dict], max_tokens: int) -> dict:
        return {}

    def _call_api(self, payload: dict, timeout_s: int) -> dict:
        return {}

    def _parse_response(self, raw: dict) -> LLMResponse:
        return LLMResponse(
            translations=list(self._raw_lines),
            tokens_in=0,
            tokens_out=0,
            model="recording",
            finish_reason=None,
            raw_latency_ms=0,
        )

    def health_check(self) -> tuple[bool, str]:
        return True, "OK"

    def get_config_fields(self) -> list[dict]:
        return []


# --------------------------------------------------------------------------
# Stray break markers
# --------------------------------------------------------------------------


def test_a_line_that_is_only_a_break_marker_is_dropped():
    """Recorded shape: 15 translations separated by 14 lone markers = 29 lines."""
    raw = ["Erste Zeile", HARD_BREAK, "Zweite Zeile", HARD_BREAK, "Dritte Zeile"]

    assert repair_line_mapping(raw) == ["Erste Zeile", "Zweite Zeile", "Dritte Zeile"]


def test_a_trailing_break_marker_line_is_dropped():
    """lord_marksman b8 came back as 15 translations plus one trailing marker."""
    assert repair_line_mapping(["Nur eine Zeile", HARD_BREAK]) == ["Nur eine Zeile"]


def test_the_soft_break_marker_counts_too():
    assert repair_line_mapping(["Text", SOFT_BREAK, "Mehr"]) == ["Text", "Mehr"]


def test_a_blank_line_is_dropped():
    """The backends' own splitters used to do this; the shared step owns it now."""
    assert repair_line_mapping(["Eins", "   ", "", "Zwei"]) == ["Eins", "Zwei"]


def test_a_break_inside_a_line_survives():
    """The subtitle asked for that break; only a marker ALONE on a line goes."""
    line = "Oben" + HARD_BREAK + "Unten"

    assert repair_line_mapping([line]) == [line]


# --------------------------------------------------------------------------
# Numbering
# --------------------------------------------------------------------------


def test_the_number_of_a_line_is_stripped():
    assert repair_line_mapping(["1: Eins", "2: Zwei"]) == ["Eins", "Zwei"]


def test_a_dot_after_the_number_is_stripped_too():
    assert repair_line_mapping(["1. Eins", "2. Zwei"]) == ["Eins", "Zwei"]


def test_forms_the_old_pattern_missed_are_stripped():
    """Measured leak: 14 lines kept a prefix that ``^\\d+[.:]`` does not match."""
    assert repair_line_mapping(["1) Eins", " 2: Zwei", "3 : Drei"]) == ["Eins", "Zwei", "Drei"]


def test_a_number_that_is_not_this_line_s_number_is_left_alone():
    """``13: Das Bankett`` on line one is content, not numbering.

    The old strip removed any leading number and silently ate it. The model
    numbers contiguously from one, so a number that does not match the
    position it sits at was never numbering.
    """
    assert repair_line_mapping(["13: Das Bankett"]) == ["13: Das Bankett"]


def test_a_number_the_model_wrote_twice_is_removed_twice():
    """Recorded live on lord_marksman batch 18: ``2: 2: Wenn wir jetzt ...``.

    Asked to prefix each line with the number of its input line, gemma3 copies
    the input's number and adds its own. Stripping one prefix leaves the other
    in the finished subtitle — 14 lines of that batch carried one.
    """
    raw = ["1: Nein."] + [f"{i}: {i}: Zeile {i}" for i in range(2, 16)]

    repaired = repair_line_mapping(raw)

    assert len(repaired) == 15
    assert repaired[0] == "Nein."
    assert repaired[1] == "Zeile 2"
    assert repaired[-1] == "Zeile 15"


def test_a_different_second_number_is_content_and_stays():
    """Only a repeat of the same number is duplicated numbering.

    ``5: 13: Das Bankett`` is line five, and its text opens with a number.
    Stripping greedily would eat it.
    """
    raw = ["1: Eins", "2: 13: Das Bankett"]

    assert repair_line_mapping(raw) == ["Eins", "13: Das Bankett"]


def test_one_missing_number_does_not_leak_all_the_others():
    """Robustness, not an observed shape — kept because the cost is one branch.

    A counter that insists on starting at one would never advance past a line
    whose number the model dropped, and every number behind it would reach the
    subtitle. Judging the batch as a whole survives that.
    """
    raw = ["Nein."] + [f"{i}: Zeile {i}" for i in range(2, 16)]

    repaired = repair_line_mapping(raw)

    assert len(repaired) == 15
    assert repaired[0] == "Nein."
    assert repaired[1] == "Zeile 2"


def test_two_content_lines_starting_with_years_are_not_numbering():
    """Ascending leading numbers alone are not proof — the range has to fit."""
    raw = ["1995: Der Anfang", "2001: Das Ende"]

    assert repair_line_mapping(raw) == raw


def test_a_lone_numbered_looking_line_is_content():
    """One number cannot establish a run, so it stays where it is."""
    assert repair_line_mapping(["13: Das Bankett"]) == ["13: Das Bankett"]


def test_unnumbered_output_is_left_exactly_as_it_is():
    """Today's contract, and any user template that forbids numbering."""
    raw = ["Eins", "Zwei", "Drei"]

    assert repair_line_mapping(raw) == raw


# --------------------------------------------------------------------------
# Wrapped translations
# --------------------------------------------------------------------------


def test_an_unnumbered_line_continues_the_numbered_one_before_it():
    """sakura b16 / lord b4: the model broke one translation across two lines."""
    raw = ["1: Wir haben Gutscheine verteilt,", "also wird die Stadt voll sein!", "2: Zweite"]

    assert repair_line_mapping(raw) == [
        "Wir haben Gutscheine verteilt, also wird die Stadt voll sein!",
        "Zweite",
    ]


def test_a_wrapped_line_keeps_the_break_the_model_asked_for():
    """The break belongs to the text; only the stray newline after it goes."""
    raw = ["1: Erste Haelfte" + HARD_BREAK, "zweite Haelfte", "2: Zweite"]

    assert repair_line_mapping(raw) == [
        "Erste Haelfte" + HARD_BREAK + "zweite Haelfte",
        "Zweite",
    ]


def test_nothing_is_merged_when_no_line_carries_a_number():
    """Without numbering there is no evidence of continuation -- guessing here
    would destroy correct batches (measured: 33 of 57 healthy ones)."""
    raw = ["Erste", "Zweite", "Dritte"]

    assert repair_line_mapping(raw) == raw


def test_a_continuation_before_any_number_stays_its_own_line():
    assert repair_line_mapping(["Vorspann", "1: Eins"]) == ["Vorspann", "Eins"]


# --------------------------------------------------------------------------
# Whole recorded batches
# --------------------------------------------------------------------------


def test_the_recorded_29_line_batch_comes_back_as_15():
    """lord_marksman_s01e05 batch 1, verbatim shape from alignment.json."""
    raw: list[str] = []
    for i in range(1, 16):
        raw.append(f"Zeile {i}")
        if i < 15:
            raw.append(HARD_BREAK)

    assert len(repair_line_mapping(raw)) == 15


def test_every_llm_backend_gets_the_repair():
    """It belongs to the shared attempt, not to each backend's parser.

    ChatGPT and Claude never stripped numbering at all -- they split on
    newlines and hand the result on. Asking the model to number its output
    would write digits into their subtitles unless the repair sits where every
    LLM backend passes through.
    """
    raw_from_model = ["1: Eins", HARD_BREAK, "2: Zwei", "und weiter", "3: Drei"]

    backend = _RecordingBackend(raw_from_model)
    resp = backend._attempt(["a", "b", "c"], "en", "de", None)

    assert resp.translations == ["Eins", "Zwei und weiter", "Drei"]


def test_a_genuinely_merged_batch_stays_short():
    """The model folded two source events into one sentence -- there is nothing
    in the output to split it back by, and inventing a split point would be
    worse than reporting the mismatch."""
    raw = ["1: Eins", "2: Zwei und Drei zusammengefasst", "3: Vier"]

    assert len(repair_line_mapping(raw)) == 3
