"""The prompt asks the model to number its output, and the retry agrees with it.

Until now the default template forbade numbering outright ("Do NOT add
numbering or prefixes to the output lines"), and the strict retry repeated the
ban. Measured over 65 real batches against gemma3:12b on the production host,
turning that around took the batches that die even after the retry from 10 to
1, and more than halved the invented hard breaks (319 to 129) as a side
effect. A blind third-model judge scored the two templates level, so the
mapping is bought without paying in German.

The numbers themselves are not a mapping -- the model renumbers contiguously
after it merges two lines, measured 6 runs out of 6. They are evidence of where
one output line ends and the next begins, which is what
``llm_utils.repair_line_mapping`` needs.
"""

from __future__ import annotations

from config import get_settings
from translation.llm_utils import build_prompt_with_glossary


def test_the_default_template_asks_the_model_to_number_its_output():
    """Deliberately not a bare 'number' match — the old ban contained that word."""
    template = get_settings().get_prompt_template()

    assert "same number" in template.lower()


def test_the_default_template_no_longer_forbids_numbering():
    """The ban and the request cannot both stand in one prompt."""
    template = get_settings().get_prompt_template().lower()

    assert "do not add numbering" not in template


def test_the_strict_retry_does_not_contradict_the_template():
    """The retry used to append 'no numbering' to a prompt asking for numbers.

    That contradiction was live during the measurement, so the 10-to-1 result
    was reached in spite of it.
    """
    template = get_settings().get_prompt_template()

    strict = build_prompt_with_glossary(template, None, ["Hello", "World"], strict=True)

    assert "no numbering" not in strict.lower()


def test_a_single_line_request_does_not_claim_to_be_numbered():
    """The template says every input line is numbered — one-line batches are not.

    Single lines stay un-numbered because the fine-tune was trained that way,
    so the prompt would otherwise contradict what it goes on to show. That
    matters more than it used to: a batch that fails is now split, and the
    split bottoms out at exactly this shape — historically the shape that
    answered with conversation rather than a translation.
    """
    template = get_settings().get_prompt_template()

    prompt = build_prompt_with_glossary(template, None, ["Hello there"])

    assert "not numbered" in prompt.lower()


def test_a_multi_line_request_says_nothing_about_being_unnumbered():
    template = get_settings().get_prompt_template()

    prompt = build_prompt_with_glossary(template, None, ["Hello", "World"])

    assert "not numbered" not in prompt.lower()
    assert "1: Hello" in prompt


def test_the_strict_retry_still_hardens_the_line_count():
    template = get_settings().get_prompt_template()

    normal = build_prompt_with_glossary(template, None, ["Hello", "World"])
    strict = build_prompt_with_glossary(template, None, ["Hello", "World"], strict=True)

    assert strict != normal
    assert "no more, no fewer" in strict
