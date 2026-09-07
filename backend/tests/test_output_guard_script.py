"""translator.output_guard — a batch that comes back in the wrong writing
system is not a translation, whatever the line count says.

The existing chat-filler guard catches the model talking; this catches the
model echoing. A Chinese source pushed through an "English → German" prompt
comes back Chinese, one line per line, and the count check is satisfied.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from translator.manager import _verify_batch
from translator.output_guard import find_script_mismatch

CHINESE_LINES = [
    "彷彿在夢境中遨遊",
    "因淡淡的期待而心情雀躍",
    "將胸口的光芒緊緊藏起",
    "某天的日常變得格外令人懷念呢",
]
GERMAN_LINES = ["Das werde ich beschlagnahmen.", "Bist du bereit, loszufahren?", "Ich bin bereit."]


class TestFindScriptMismatch:
    def test_chinese_output_for_a_latin_target_is_flagged(self):
        assert find_script_mismatch(CHINESE_LINES, "de") is not None

    def test_german_output_for_a_german_target_passes(self):
        assert find_script_mismatch(GERMAN_LINES, "de") is None

    def test_chinese_output_for_a_chinese_target_passes(self):
        assert find_script_mismatch(CHINESE_LINES, "zh") is None

    def test_unknown_target_gives_no_opinion(self):
        assert find_script_mismatch(CHINESE_LINES, "und") is None

    def test_a_single_untranslated_sign_does_not_fail_a_german_batch(self):
        lines = GERMAN_LINES + ["東京"]
        assert find_script_mismatch(lines, "de") is None


class TestVerifyBatch:
    def _result(self, lines):
        return SimpleNamespace(translated_lines=list(lines), success=True)

    def test_echoed_chinese_fails_the_batch(self):
        with pytest.raises(RuntimeError, match="script"):
            _verify_batch(
                self._result(CHINESE_LINES), len(CHINESE_LINES), "Batch 1", target_lang="de"
            )

    def test_german_lines_pass(self):
        _verify_batch(self._result(GERMAN_LINES), len(GERMAN_LINES), "Batch 1", target_lang="de")

    def test_target_language_is_optional_for_old_callers(self):
        _verify_batch(self._result(GERMAN_LINES), len(GERMAN_LINES), "Batch 1")
