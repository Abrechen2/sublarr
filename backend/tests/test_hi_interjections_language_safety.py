"""HI removal must never delete ordinary words. Interjection stripping is gone.

Sublarr used to ship an ENGLISH interjection word list (Um, Uh, Eh, Ah, Oh, Hmm,
Nah, ...) compiled into a bare ``\\b(?:...)\\b`` substitution and applied to
subtitles of EVERY language. In German that destroyed dialogue outright:

    "darf ich dich um eine Sache bitten?"  ->  "darf ich dich  eine Sache bitten?"

"um" is one of the most common German words (a preposition/conjunction), and so
are "eh" ("das ist eh klar") and "nah" ("nah am Fluss"). On the production
library 1874 of 5009 German sidecars were damaged before the bug was found.

The feature is removed, not patched. Bazarr — via Subzero, the reference
implementation for HI removal — has no interjection list at all: HI removal
targets *structural* markers (brackets, music symbols, speaker labels), never
linguistic ones. A word list can never be safe across languages, so no regex is
a fix; the correct amount of interjection stripping is none.

These tests pin that: HI removal leaves prose alone.
"""

import pysubs2
import pytest


@pytest.fixture
def process_srt(tmp_path):
    def _run(lines):
        from subtitle_processor import ModConfig, ModName, apply_mods

        subs = pysubs2.SSAFile()
        for i, line in enumerate(lines):
            subs.events.append(
                pysubs2.SSAEvent(start=(i * 3 + 1) * 1000, end=(i * 3 + 3) * 1000, text=line)
            )
        path = tmp_path / "t.de.srt"
        subs.save(str(path), format_="srt", encoding="utf-8")
        apply_mods(str(path), [ModConfig(mod=ModName.HI_REMOVAL)], dry_run=False)
        out = pysubs2.load(str(path), format_="srt", encoding="utf-8")
        return [e.plaintext.strip() for e in out.events]

    return _run


@pytest.mark.parametrize(
    "line",
    [
        # Real cues from the production library that came back mutilated.
        "darf ich dich um eine Sache bitten?",
        "Ehm... bist du hier, um mich zu pflegen?",
        "Das übersteigt Universal-Drag-Rides um ein Vielfaches.",
        "Aber ich mache mir Sorgen um Ai.",
        "Ich bin hier, um zu helfen.",
        "Um Himmels willen!",
        # The other two English list entries that collide with German.
        "Das ist eh klar.",
        "Eh, das ist doch klar.",
        "Er wohnt nah am Fluss.",
    ],
)
def test_german_prose_is_never_touched(process_srt, line):
    assert process_srt([line]) == [line]


@pytest.mark.parametrize(
    "line",
    [
        # English filler is prose too now — HI removal is structural only.
        "Um, I think so.",
        "Well, um, I think so.",
        "Uh... maybe.",
    ],
)
def test_english_filler_is_left_alone_too(process_srt, line):
    """No word list means no word is special. Structural markers still go."""
    assert process_srt([line]) == [line]


def test_structural_markers_still_removed(process_srt):
    """What HI removal is actually for: brackets, music, speaker labels."""
    assert process_srt(["[DOOR SLAMS] Guten Morgen.", "MANN: Hallo."]) == [
        "Guten Morgen.",
        "Hallo.",
    ]


def test_no_double_space_artifacts(process_srt):
    for text in process_srt(["darf ich dich um eine Sache bitten?"]):
        assert "  " not in text


def test_interjection_machinery_is_gone():
    """The word list and its pattern builder must not come back."""
    import os

    import subtitle_processor

    assert not hasattr(subtitle_processor, "_build_interjection_pattern")
    word_list = os.path.join(
        os.path.dirname(subtitle_processor.__file__), "data", "hi_interjections.txt"
    )
    assert not os.path.exists(word_list)
