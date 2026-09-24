"""Regressions measured with libass, plus both production save paths."""

import json
from pathlib import Path
from unittest.mock import patch

import pysubs2
import pytest

from ass_lexer import ASSNeedsReviewError, lex, remove_closed_geometry, validate_translation
from ass_utils import text_outside_drawing

REFERENCES = json.loads(
    Path(__file__).with_name("fixtures").joinpath("ass_libass_0173.json").read_text()
)


@pytest.mark.parametrize("reference", REFERENCES, ids=lambda row: row["name"])
def test_matches_independent_renderer(reference):
    if reference["needs_review"]:
        with pytest.raises(ASSNeedsReviewError):
            text_outside_drawing(reference["text"])
    else:
        assert text_outside_drawing(reference["text"]) == reference["expected"]


@pytest.mark.parametrize(
    "source, expected",
    [
        (r"{\p1(0)}Good morning.{\p0}", r"{\p1(0)}Good morning.{\p0}"),
        (r"{\zzz(\p1)}Good morning.{\p0}", r"{\zzz(\p1)}Good morning.{\p0}"),
        (
            r"{\p1}m 0 0{\c&H0000FF&}l 10 10{\p0}Hello",
            r"{\p1}{\c&H0000FF&}{\p0}Hello",
        ),
        (r"{\p1}m 0 0{\p2\an8}l 10 10{\p0}Hello", r"{\p1}{\p2\an8}{\p0}Hello"),
        (r"{\t(0,1000,\p1)}m 0 0{\p0}Hello", r"{\t(0,1000,\p1)}{\p0}Hello"),
        (r"{\p1}m 0 0", r"{\p1}m 0 0"),
    ],
)
def test_geometry_cleanup_preserves_every_override(source, expected):
    cleaned = remove_closed_geometry(source)
    assert cleaned == expected
    assert remove_closed_geometry(cleaned) == cleaned


@pytest.mark.parametrize(
    "source",
    ["x" * 131073, "{unclosed", "a\x00b", "a\rb", "a\nb", "{" + r"\p1" * 4097 + "}"],
    # Short ids: Windows caps PYTEST_CURRENT_TEST at 32 767 characters.
    ids=["oversize", "unclosed", "nul", "cr", "lf", "tag-budget"],
)
def test_ambiguous_or_excessive_events_require_review(source):
    with pytest.raises(ASSNeedsReviewError):
        lex(source)


@pytest.mark.parametrize("digits", [1000, 10000, 100000])
def test_large_numeric_arguments_need_no_integer_conversion(digits):
    assert text_outside_drawing("{\\p" + "9" * digits + "}m 0 0") == ""


@pytest.mark.parametrize(
    "answer", [r"{\p1}m 0 0", r"hello\bad", "hello\nworld", "", None, "a\x00b"]
)
def test_model_cannot_create_ass_syntax(answer):
    with pytest.raises(ASSNeedsReviewError):
        validate_translation("Good morning.", answer)


@pytest.mark.parametrize("escape", [r"\n", r"\N", r"\h"])
def test_original_layout_escape_is_preserved(escape):
    validate_translation("Good" + escape + "morning.", "Guten" + escape + "Morgen.")


def _translate(tmp_path, monkeypatch, source, answer, embedded, *, hi=False):
    import copy

    import translator
    from translation.base import TranslationResult
    from translator.ass_flow import _translate_external_ass, translate_ass

    subs = pysubs2.SSAFile()
    sources = [source] if isinstance(source, str) else source
    subs.events = [
        pysubs2.SSAEvent(start=i * 1000, end=(i + 1) * 1000, text=text)
        for i, text in enumerate(sources)
    ]
    src = tmp_path / "Show.en.ass"
    subs.save(str(src))
    before = src.read_bytes()
    target = tmp_path / "Show.de.ass"
    target.write_bytes(b"existing output must survive a rejected answer")
    if hi:
        settings = copy.copy(translator.get_settings())
        settings.hi_removal_enabled = True
        monkeypatch.setattr(translator, "get_settings", lambda: settings)

    def model(lines, **kwargs):
        values = [answer(line) if callable(answer) else answer for line in lines]
        return values, TranslationResult(translated_lines=values, backend_name="test", success=True)

    monkeypatch.setattr(translator, "_get_quality_config", lambda: (False, 35, 1))
    monkeypatch.setattr(
        translator,
        "extract_subtitle_stream",
        lambda _video, _stream, dest: Path(dest).write_bytes(before),
    )
    with patch.object(translator, "_translate_with_manager", side_effect=model) as manager:
        if embedded:
            result = translate_ass(
                str(tmp_path / "Show.mkv"), {}, {}, target_language="de", source_language="en"
            )
        else:
            result = _translate_external_ass(
                str(tmp_path / "Show.mkv"), str(src), target_language="de", source_language="en"
            )
    assert src.read_bytes() == before
    return result, target, manager


@pytest.mark.parametrize("embedded", [False, True])
@pytest.mark.parametrize(
    "source",
    [
        r"{\p1(0)}Good morning.{\p0}",
        r"{\t(0,1000,2,3,\p1)}Good morning.{\p0}",
        r"{\zzz(\p1)}Good morning.{\p0}",
        r"Good\nmorning.",
    ],
)
def test_visible_dialogue_survives_real_save(tmp_path, app_ctx, monkeypatch, embedded, source):
    answer = r"Guten\nMorgen." if r"\n" in source else "Guten Morgen."
    result, target, manager = _translate(tmp_path, monkeypatch, source, answer, embedded)
    assert result["success"], result
    assert manager.call_count == 1
    saved = pysubs2.load(str(target)).events[0].text
    assert saved == source.replace("Good", "Guten").replace("morning", "Morgen")


@pytest.mark.parametrize("embedded", [False, True])
@pytest.mark.parametrize("answer", [r"{\p1}m 0 0", r"Guten\bMorgen.", ""])
def test_unsafe_model_output_never_replaces_existing_file(
    tmp_path, app_ctx, monkeypatch, embedded, answer
):
    result, target, _ = _translate(tmp_path, monkeypatch, "Good morning.", answer, embedded)
    assert not result["success"]
    assert result["reason"] == "ass_review_required"
    assert target.read_bytes() == b"existing output must survive a rejected answer"


@pytest.mark.parametrize("embedded", [False, True])
@pytest.mark.parametrize("source", [r"Good{\p1}m 0 0{\p0}morning.", "Good{unclosed"])
def test_unsupported_source_is_not_an_empty_track(tmp_path, app_ctx, monkeypatch, embedded, source):
    result, target, manager = _translate(tmp_path, monkeypatch, source, "unused", embedded)
    assert not result["success"]
    assert result["reason"] == "ass_review_required"
    assert result["stats"]["untranslated"] == 1
    assert manager.call_count == 0
    assert target.read_bytes() == b"existing output must survive a rejected answer"


@pytest.mark.parametrize("embedded", [False, True])
def test_explicit_hi_removal_may_clear_a_caption(tmp_path, app_ctx, monkeypatch, embedded):
    result, target, _ = _translate(
        tmp_path, monkeypatch, r"{\an8}[DOOR SLAMS]", "", embedded, hi=True
    )
    assert result["success"], result
    assert pysubs2.load(str(target)).events[0].text == r"{\an8}"


def test_quality_retry_cannot_silently_drop_events():
    from translator.ass_flow import _collect_translatable_events, _restore_translations

    subs = pysubs2.SSAFile()
    subs.events = [pysubs2.SSAEvent(text="Good morning.")]
    indices, texts, tags, lengths, prefixes, suffixes, _ = _collect_translatable_events(
        subs, {"Default"}
    )
    with pytest.raises(ASSNeedsReviewError, match="count mismatch"):
        _restore_translations(subs, indices, [], tags, lengths, prefixes, suffixes, texts)
    assert subs.events[0].text == "Good morning."


# --- Line breaks: the model re-spells them, which must not cost the file ----
#
# Prod translation memory, 2026-09-20..24: of 8 005 answers to a source with a
# break, 4 811 spelled it ``\n`` and 828 had a different number of breaks. The
# first cut of this module rejected the whole file for either.


@pytest.mark.parametrize(
    "source, answer, expected",
    [
        (r"Good\Nmorning.", r"Guten\nMorgen.", r"Guten\NMorgen."),
        (r"Good\Nmorning.", "Guten\nMorgen.", r"Guten\NMorgen."),
        (r"Good\Nmorning.", "Guten\r\nMorgen.", r"Guten\NMorgen."),
        (r"Good\nmorning.", r"Guten\NMorgen.", r"Guten\nMorgen."),
        (r"Good\Nmorning\nfriend.", r"Guten\nMorgen\NFreund.", r"Guten\nMorgen\NFreund."),
        ("Good morning.", r"Guten\NMorgen.", "Guten Morgen."),
        ("Good morning.", r"Guten\nMorgen.", "Guten Morgen."),
        ("Good morning.", "Guten\nMorgen.", "Guten Morgen."),
        (r"Good\Nmorning.", r"Guten\hMorgen.", r"Guten\hMorgen."),
    ],
)
def test_break_spelling_follows_the_source(source, answer, expected):
    from ass_lexer import align_break_spelling

    assert align_break_spelling(source, answer) == expected


@pytest.mark.parametrize("embedded", [False, True])
@pytest.mark.parametrize(
    "source, answer, expected",
    [
        (r"Good\Nmorning.", r"Guten\nMorgen.", r"Guten\NMorgen."),
        (r"Good\Nmorning.", "Guten\nMorgen.", r"Guten\NMorgen."),
        # A reflow: one break fewer is a different wrap, not damage.
        (r"Good morning,\Nmy friend.", "Guten Morgen, mein Freund.", "Guten Morgen, mein Freund."),
        (r"Good\Nmorning.", r"Guten\NMorgen,\Nhallo.", r"Guten\NMorgen,\Nhallo."),
    ],
)
def test_a_respelled_or_reflowed_break_is_saved(
    tmp_path, app_ctx, monkeypatch, embedded, source, answer, expected
):
    result, target, _ = _translate(tmp_path, monkeypatch, source, answer, embedded)
    assert result["success"], result
    assert pysubs2.load(str(target)).events[0].text == expected


@pytest.mark.parametrize("embedded", [False, True])
def test_one_unsafe_answer_costs_one_line_not_the_file(tmp_path, app_ctx, monkeypatch, embedded):
    sources = [r"{\an8}Good morning.", "Hello there.", "See you."]
    answers = {
        "Good morning.": "Guten Morgen.",
        "Hello there.": r"{\p1}m 0 0 l 640 0",
        "See you.": "Bis dann.",
    }
    result, target, _ = _translate(tmp_path, monkeypatch, sources, answers.__getitem__, embedded)
    assert result["success"], result
    saved = [event.text for event in pysubs2.load(str(target)).events]
    assert saved == [r"{\an8}Guten Morgen.", "Hello there.", "Bis dann."]
    assert result["stats"]["translated"] == 2
    assert result["stats"]["untranslated"] == 1
    rejected = result["stats"]["untranslated_events"][0]
    assert rejected["index"] == 1
    assert rejected["start_ms"] == 1000
    assert "syntax" in rejected["reason"]
