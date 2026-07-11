"""all_caps_lines must not delete whole sentences.

HI removal dropped EVERY line where ``text == text.upper()``. Punctuation is
immune to ``.upper()``, so a fully capitalised *sentence* — commas, question
marks and all — counted as an all-caps line and was deleted outright. On the
production library this silently removed anime song lyrics (OP/ED karaoke is
conventionally typeset in caps) and capitalised dialogue:

    "UM DIE DREHBUCHSCHREIBERIN ZU BESCHÜTZEN, ODER?"   -> whole cue gone

Bazarr (via Subzero's ``HI_all_caps``) uses::

    (?u)(^(?=.*[A-ZÀ-Ž&+]{4,})[A-ZÀ-Ž-_\\s&+]+$)     # guard: not only_uppercase

The character class admits only capitals, spaces and ``-_&+`` — no sentence
punctuation, no digits, no lowercase. A capitalised line carrying punctuation is
therefore not an HI marker and survives. Subzero additionally skips the rule
entirely when the whole subtitle is uppercase. We follow both.

Every line below is real data taken from the production library.
"""

import pysubs2
import pytest


@pytest.fixture
def process_srt(tmp_path):
    def _run(lines, options=None):
        from subtitle_processor import ModConfig, ModName, apply_mods

        subs = pysubs2.SSAFile()
        for i, line in enumerate(lines):
            subs.events.append(
                pysubs2.SSAEvent(start=(i * 3 + 1) * 1000, end=(i * 3 + 3) * 1000, text=line)
            )
        path = tmp_path / "t.de.srt"
        subs.save(str(path), format_="srt", encoding="utf-8")
        apply_mods(
            str(path), [ModConfig(mod=ModName.HI_REMOVAL, options=options or {})], dry_run=False
        )
        out = pysubs2.load(str(path), format_="srt", encoding="utf-8")
        return [e.plaintext.strip() for e in out.events]

    return _run


# ---------------------------------------------------------------------------
# Capitalised SENTENCES are content, not HI markers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "UM DIE DREHBUCHSCHREIBERIN ZU BESCHÜTZEN, ODER?",
        "DER WIND, DER ZU MEINEM LANGWEILIGEN FENSTERPLATZ HEREINWEHTE",
        "SOWOHL LICHT ALS AUCH SCHATTEN, IMMER NOCH WEIT ENTFERNT.",
    ],
)
def test_capitalised_sentence_with_punctuation_survives(process_srt, line):
    """Punctuation means it is a sentence — Subzero's class excludes , . ? !"""
    assert process_srt([line]) == [line]


def test_speaker_label_stripped_but_sentence_kept(process_srt):
    """ "ICH:" is the HI marker; the capitalised sentence behind it is dialogue."""
    out = process_srt(["ICH: DU HAST MICH DOCH WOHL NICHT UM HILFE GEBETEN,"])
    assert out == ["DU HAST MICH DOCH WOHL NICHT UM HILFE GEBETEN,"]


def test_uppercase_only_subtitle_is_left_alone(process_srt):
    """Subzero's only_uppercase guard: a fully capitalised subtitle is a style,

    not a stream of HI markers. Removing every line would empty the file.
    """
    lines = ["PHONE RINGING", "HELLO THERE", "GOODBYE NOW"]
    assert process_srt(lines) == lines


# ---------------------------------------------------------------------------
# Genuine all-caps HI markers must still go
# ---------------------------------------------------------------------------


def test_unpunctuated_caps_marker_still_removed(process_srt):
    """ "PHONE RINGING" among normal dialogue is a sound effect — still dropped."""
    assert process_srt(["PHONE RINGING", "Hello there", "How are you"]) == [
        "Hello there",
        "How are you",
    ]


def test_short_caps_word_still_kept(process_srt):
    """Below all_caps_min_length (4 consecutive capitals) nothing is removed."""
    assert process_srt(["OK!", "Hello"]) == ["OK!", "Hello"]
