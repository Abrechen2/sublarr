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


def test_a_single_line_first_attempt_keeps_the_un_numbered_shape():
    """The fine-tune was trained on it and delivers 16/16 with it."""
    template = get_settings().get_prompt_template()

    prompt = build_prompt_with_glossary(template, None, ["Hello there"])

    assert "not numbered" in prompt.lower()
    assert "1: Hello there" not in prompt


def test_the_strict_retry_of_a_single_line_numbers_it_instead():
    """The retry changes the shape rather than repeating the same one louder.

    The un-numbered shape leaves the payload with no marker at all: a long
    instruction block whose last line is a bare subtitle fragment. gemma3:12b
    reads that as no input and answers with an invented batch. Measured
    against both live models on 2026-09-11, 4 lines x 2 shapes x 3 runs,
    counting answers of exactly one line:

                                    un-numbered   numbered
      gemma3:12b (prod)                 18/24        24/24
      anime-translator-en-de-v15        16/16        14/16

    All six gemma3 failures were one production line, "or else it's
    pointless!" -- 0/6 un-numbered, 6/6 numbered. The two models want
    opposite shapes, so the first attempt serves the fine-tune and the retry
    serves the general model, instead of one fixed choice losing one of them.
    """
    template = get_settings().get_prompt_template()

    retry = build_prompt_with_glossary(template, None, ["Hello there"], strict=True)

    assert "1: Hello there" in retry
    assert "not numbered" not in retry.lower()


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
