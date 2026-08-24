r"""A translation must not carry a hard line break the source did not have.

Measured on a real library on 2026-08-24: the written German ASS for one
episode contained 158 lines with a literal ``\N`` where its English source had
28. The extra breaks come from the model, they change how the subtitle renders
against the original, and — because the line *count* is still correct — nothing
in the pipeline notices. Sublarr's contract with the backends is a 1:1 line
mapping; where the source line has no hard break, neither may the translation.
"""

from translation.llm_utils import strip_invented_hard_breaks

HB = chr(92) + "N"  # literal ASS hard line break


def test_trailing_break_is_removed_when_the_source_had_none():
    source = ["By the way, Mariabelle..."]
    translated = [f"Apropos, Mariabelle…{HB}"]

    assert strip_invented_hard_breaks(source, translated) == ["Apropos, Mariabelle…"]


def test_inner_break_becomes_a_space_so_words_do_not_collide():
    source = ["That's the district mayor's message."]
    translated = [f"Das ist die Nachricht{HB}des Bezirksbürgermeisters."]

    assert strip_invented_hard_breaks(source, translated) == [
        "Das ist die Nachricht des Bezirksbürgermeisters."
    ]


def test_a_break_the_source_asked_for_is_kept():
    source = [f"The Founding Festival is{HB}going to be a huge success!"]
    translated = [f"Das Gründungsfest{HB}wird ein voller Erfolg!"]

    assert strip_invented_hard_breaks(source, translated) == translated


def test_lines_without_any_break_are_returned_untouched():
    source = ["What?!", "This is crazy..."]
    translated = ["Was?!", "Das ist verrückt..."]

    assert strip_invented_hard_breaks(source, translated) == translated


def test_a_length_mismatch_leaves_everything_alone():
    """Pairing is meaningless then — the caller handles the mismatch."""
    source = ["one", "two"]
    translated = [f"eins{HB}"]

    assert strip_invented_hard_breaks(source, translated) == translated


def test_multiple_invented_breaks_in_one_line_all_go():
    source = ["Short line."]
    translated = [f"Kurze{HB}Zeile{HB}hier.{HB}"]

    assert strip_invented_hard_breaks(source, translated) == ["Kurze Zeile hier."]


# ---------------------------------------------------------------------------
# Wiring — a helper nobody calls fixes nothing. The two defects this session
# found in the frontend both had this exact shape, so pin the call site too.
# ---------------------------------------------------------------------------

import os

import pytest

from config import reload_settings
from db import close_db, init_db
from translation.llm_base import LLMBackend, LLMResponse


@pytest.fixture()
def _app_context(tmp_path):
    from app import create_app

    os.environ["SUBLARR_DB_PATH"] = str(tmp_path / "hb.db")
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


class _BreakHappyBackend(LLMBackend):
    """A backend whose model appends a hard break to every line."""

    name = "break_happy"
    display_name = "Break Happy"
    config_fields = []
    default_model = "stub"
    cost_per_1m_tokens_in = 0
    cost_per_1m_tokens_out = 0

    def _build_request(self, messages, max_tokens):
        return {"messages": messages}

    def _call_api(self, payload, timeout_s):
        return {"n": len(payload["messages"])}

    def _parse_response(self, raw):
        return LLMResponse(
            translations=[f"Zeile eins{HB}", f"Zeile zwei{HB}"],
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


def test_translate_batch_removes_breaks_the_source_never_had(_app_context):
    from translation.concurrency import get_concurrency

    get_concurrency().register(_BreakHappyBackend.name, 2)
    backend = _BreakHappyBackend()

    result = backend.translate_batch(["Line one", "Line two"], "en", "de")

    assert result.success is True
    assert result.translated_lines == ["Zeile eins", "Zeile zwei"]
