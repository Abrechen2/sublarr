"""Tests for translator.output_guard — rejecting chat filler in LLM output.

Prod 2026-08-18: 1124 translation-memory rows held the model's chat replies
("Okay, please provide the English anime subtitle lines...") instead of
translations. They entered through single-line batches, where the existing
line-count check cannot catch them — a chat reply is exactly one line.
"""

import pytest

from translator.output_guard import find_chat_filler

# Real poisoned lines found in the prod translation memory on 2026-08-18.
POISONED_PROD_LINES = [
    "Okay, please provide the English anime subtitle lines you want me to translate. "
    "I'm ready when you are!",
    "Okay, please provide the English subtitle lines you want me to translate.",
    "Okay, I'm ready. Please provide the English subtitle lines.",
    "Absolutely! Please provide the English subtitle lines. I'm ready when you are!",
]

LEGIT_GERMAN_LINES = [
    "Das werde ich beschlagnahmen.",
    "Bist du bereit, loszufahren?",
    "Ich bin bereit.",
    "Sei einfach froh, dass ich es nicht wegwerfe.",
    "Okay, machen wir das.",
    "Gib mir das Schwert!",
    "",
]


class TestFindChatFiller:
    """Tests for find_chat_filler."""

    @pytest.mark.parametrize("line", POISONED_PROD_LINES)
    def test_detects_real_prod_poison(self, line):
        hits = find_chat_filler([line])
        assert hits == [(0, line)]

    def test_detects_meta_preamble(self):
        hits = find_chat_filler(["Here is the translation of your subtitle lines:"])
        assert len(hits) == 1

    def test_detects_german_meta_preamble(self):
        hits = find_chat_filler(["Hier ist die Übersetzung der Zeilen:"])
        assert len(hits) == 1

    def test_detects_refusal(self):
        hits = find_chat_filler(["As an AI language model, I cannot translate this."])
        assert len(hits) == 1

    def test_legit_lines_pass(self):
        assert find_chat_filler(LEGIT_GERMAN_LINES) == []

    def test_reports_index_within_batch(self):
        lines = ["Hallo.", POISONED_PROD_LINES[0], "Welt."]
        hits = find_chat_filler(lines)
        assert hits == [(1, POISONED_PROD_LINES[0])]

    def test_none_lines_are_skipped(self):
        assert find_chat_filler([None, "Hallo."]) == []

    def test_empty_input(self):
        assert find_chat_filler([]) == []
