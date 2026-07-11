"""HI interjection removal must never eat ordinary words of other languages.

The bundled interjection list is English ("Um", "Uh", "Eh", "Nah", ...) but it
was applied to subtitles of EVERY language, matching ANYWHERE in a sentence via
a bare ``\\b(?:...)\\b`` substitution. In German that silently destroyed text:

    "darf ich dich um eine Sache bitten?"  ->  "darf ich dich  eine Sache bitten?"

"um" is one of the most common German words (a preposition/conjunction), and so
are "eh" ("das ist eh klar") and "nah" ("nah am Fluss"). Verified on production:
a downloaded German subtitle had all 8 occurrences of "um" removed, each leaving
the tell-tale double space behind.

An interjection is only an interjection when it stands alone as an utterance:
the whole line, line-initial followed by sentence punctuation, or delimited by
commas on both sides. Anywhere else it is a content word and must survive.
"""

import pysubs2
import pytest


@pytest.fixture
def process_srt(tmp_path):
    """Run HI removal over the given cue lines; return the resulting cue texts."""

    def _run(lines):
        from subtitle_processor import ModConfig, ModName, apply_mods

        subs = pysubs2.SSAFile()
        for i, line in enumerate(lines):
            subs.events.append(
                pysubs2.SSAEvent(start=(i * 3 + 1) * 1000, end=(i * 3 + 3) * 1000, text=line)
            )
        path = tmp_path / "test.de.srt"
        subs.save(str(path), format_="srt", encoding="utf-8")

        apply_mods(str(path), [ModConfig(mod=ModName.HI_REMOVAL)], dry_run=False)

        out = pysubs2.load(str(path), format_="srt", encoding="utf-8")
        return [e.plaintext.strip() for e in out.events]

    return _run


# ---------------------------------------------------------------------------
# German content words must survive (the reported bug)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "darf ich dich um eine Sache bitten?",
        "Ehm... bist du hier, um mich zu pflegen?",
        "Das übersteigt Universal-Drag-Rides um ein Vielfaches.",
        "Ich bin hier, um zu helfen.",
        "Um Himmels willen!",
    ],
)
def test_german_um_is_never_removed(process_srt, line):
    """ "um" mid-sentence is a preposition, not an interjection."""
    assert process_srt([line]) == [line]


def test_german_eh_and_nah_are_never_removed(process_srt):
    """ "eh" (= anyway) and "nah" (= near) are ordinary German words."""
    lines = ["Das ist eh klar.", "Er wohnt nah am Fluss."]
    assert process_srt(lines) == lines


def test_removal_never_leaves_a_double_space(process_srt):
    """The old bare-substitution left "dich  eine" behind — a visible artifact."""
    for text in process_srt(["darf ich dich um eine Sache bitten?"]):
        assert "  " not in text


# ---------------------------------------------------------------------------
# Genuine English interjections must still be removed
# ---------------------------------------------------------------------------


def test_line_initial_interjection_with_comma_is_removed(process_srt):
    assert process_srt(["Um, I think so."]) == ["I think so."]


def test_line_initial_interjection_with_ellipsis_is_removed(process_srt):
    assert process_srt(["Uh... maybe."]) == ["maybe."]


def test_comma_delimited_interjection_is_removed(process_srt):
    """A filler wedged between commas is a standalone utterance."""
    assert process_srt(["Well, um, I think so."]) == ["Well, I think so."]


def test_whole_cue_interjection_drops_the_cue(process_srt):
    """A cue that is nothing but an interjection carries no content."""
    assert process_srt(["Hmm", "Real dialogue."]) == ["Real dialogue."]


def test_existing_behaviour_hmm_comma_still_removed(process_srt):
    """Pins the behaviour test_interjection_whole_word_only already relied on."""
    assert process_srt(["Hmm, that's odd"]) == ["that's odd"]
