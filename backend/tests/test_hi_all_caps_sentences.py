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


def test_capitalised_sentence_wrapped_across_two_lines_survives(process_srt):
    """Judged line by line, the first line carries no punctuation and looked like

    a marker — so half the sentence was deleted. The cue must be judged whole.
    """
    cue = "UM DIE DREHBUCHSCHREIBERIN\nZU BESCHÜTZEN, ODER?"
    assert process_srt([cue]) == [cue]


def test_two_line_caps_marker_is_still_removed(process_srt):
    """A genuine marker wrapped over two lines is still a marker."""
    assert process_srt(["PHONE\nRINGING", "Hallo."]) == ["Hallo."]


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


# ---------------------------------------------------------------------------
# The all-caps heuristic belongs to SRT only
# ---------------------------------------------------------------------------


def test_all_caps_rule_does_not_run_on_ass(tmp_path):
    r"""In ASS, a capitalised line is typesetting — a sign — not an HI marker.

    Signs are positioned and styled (\an8, \pos, their own style); the caps
    heuristic exists because SRT has no way to express that. Applying it to ASS
    deletes the very content the typesetter placed there.
    """
    import pysubs2

    from subtitle_processor import ModConfig, ModName, apply_mods

    # Normal dialogue is present, so the only_uppercase guard does NOT fire —
    # without an ASS exemption the caps rule would run and eat the signs.
    cues = [
        r"{\an8\pos(960,120)}CAFÉ HILFUMI",
        r"{\an8}ZUTRITT FÜR UNBEFUGTE VERBOTEN",
        "STRECKEN WIR UNSERE HÄNDE AUS",
        "Guten Morgen, wie geht es dir?",
        "Mir geht es gut, danke.",
    ]
    subs = pysubs2.SSAFile()
    for i, text in enumerate(cues):
        subs.events.append(
            pysubs2.SSAEvent(start=(i * 3 + 1) * 1000, end=(i * 3 + 3) * 1000, text=text)
        )
    path = tmp_path / "t.ass"
    subs.save(str(path), format_="ass")

    apply_mods(str(path), [ModConfig(mod=ModName.HI_REMOVAL)], dry_run=False)

    out = [e.text for e in pysubs2.load(str(path), format_="ass").events]
    assert out == cues, "signs and lyrics must survive HI removal on ASS"


def test_structural_markers_still_removed_on_ass(tmp_path):
    """Brackets and speaker labels are HI markers in every format."""
    import pysubs2

    from subtitle_processor import ModConfig, ModName, apply_mods

    subs = pysubs2.SSAFile()
    subs.events.append(pysubs2.SSAEvent(start=1000, end=3000, text=r"{\an8}[DOOR SLAMS]"))
    subs.events.append(pysubs2.SSAEvent(start=4000, end=6000, text="Guten Morgen."))
    path = tmp_path / "t2.ass"
    subs.save(str(path), format_="ass")

    apply_mods(str(path), [ModConfig(mod=ModName.HI_REMOVAL)], dry_run=False)

    out = [e.plaintext for e in pysubs2.load(str(path), format_="ass").events]
    assert out == ["Guten Morgen."]
