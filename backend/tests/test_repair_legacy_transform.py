"""The frozen copy of the buggy pipeline must reproduce the damage exactly.

Repair overwrites files on disk. Before it does, it has to prove that the file
it is about to replace is *pipeline damage* and not the user's own edit. The
proof: take the pristine original from the provider, replay the OLD (buggy)
pipeline over it, and require the result to equal the file on disk byte for byte.
If it does not match, a human touched the file — leave it alone.

That makes this frozen replay load-bearing: if it drifts from what 1.6.5 actually
did, repair would either refuse valid repairs or, worse, overwrite hand edits.
These tests pin it against real, observed before/after pairs from the production
library.
"""

import pysubs2

from services.repair.legacy_transform import replay_legacy_pipeline


def _srt(tmp_path, lines, name="x.de.srt"):
    subs = pysubs2.SSAFile()
    for i, line in enumerate(lines):
        subs.events.append(
            pysubs2.SSAEvent(start=(i * 3 + 1) * 1000, end=(i * 3 + 3) * 1000, text=line)
        )
    p = tmp_path / name
    subs.save(str(p), format_="srt", encoding="utf-8")
    return p.read_bytes()


def _texts(raw: bytes, tmp_path):
    p = tmp_path / "out.de.srt"
    p.write_bytes(raw)
    return [
        e.plaintext.strip() for e in pysubs2.load(str(p), format_="srt", encoding="utf-8").events
    ]


def test_replays_the_um_deletion(tmp_path):
    """The reported bug: "um" cut out, leaving a double space behind."""
    original = _srt(tmp_path, ["darf ich dich um eine Sache bitten?"])

    damaged = replay_legacy_pipeline(original, fmt="srt")

    assert _texts(damaged, tmp_path) == ["darf ich dich  eine Sache bitten?"]


def test_replays_all_the_interjection_words(tmp_path):
    """ "eh" and "nah" were eaten too — they are on the same English list."""
    original = _srt(tmp_path, ["Das ist eh klar.", "Er wohnt nah am Fluss."])

    damaged = replay_legacy_pipeline(original, fmt="srt")

    assert _texts(damaged, tmp_path) == ["Das ist  klar.", "Er wohnt  am Fluss."]


def test_replays_the_capitalised_sentence_deletion(tmp_path):
    """A fully capitalised sentence was dropped outright — punctuation and all."""
    original = _srt(
        tmp_path,
        ["UM DIE DREHBUCHSCHREIBERIN ZU BESCHÜTZEN, ODER?", "Normale Zeile."],
    )

    damaged = replay_legacy_pipeline(original, fmt="srt")

    assert _texts(damaged, tmp_path) == ["Normale Zeile."]


def test_untouched_text_replays_to_itself(tmp_path):
    """A cue the old pipeline had no opinion about must come back unchanged.

    If the replay mutated innocent text, every such file would look hand-edited
    and repair would skip it.
    """
    lines = ["Guten Morgen.", "Wie geht es dir?"]
    original = _srt(tmp_path, lines)

    replayed = replay_legacy_pipeline(original, fmt="srt")

    assert _texts(replayed, tmp_path) == lines


def test_the_frozen_word_list_is_the_one_that_shipped(tmp_path):
    """Pinned verbatim from backend/data/hi_interjections.txt at 1.6.5."""
    from services.repair.legacy_transform import LEGACY_INTERJECTIONS

    assert LEGACY_INTERJECTIONS[:10] == [
        "Hmm",
        "Hm",
        "Ugh",
        "Ahem",
        "Ahh",
        "Ah",
        "Oh",
        "Eh",
        "Um",
        "Uh",
    ]
    assert len(LEGACY_INTERJECTIONS) == 30
