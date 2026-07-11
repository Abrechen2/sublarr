"""HI removal must not strip ASS override tags off the cues it edits.

``_apply_hi_removal`` read ``event.plaintext`` (which drops every ``{...}``
override block) and wrote the result back into ``event.text``. So any ASS cue
the pipeline touched came back stripped of its formatting::

    {\\an8}{\\i1}Um,{\\i0} I think so.   ->   I think so.

Positioning (``\\an8``, ``\\pos``), italics, karaoke — all gone. ASS is the
dominant format for anime, which is exactly Sublarr's audience.

Cues the pipeline does not modify were never affected (their ``text`` is not
written back), so the bug only ever showed up on edited cues.
"""

import pysubs2
import pytest


@pytest.fixture
def process_ass(tmp_path):
    def _run(texts):
        from subtitle_processor import ModConfig, ModName, apply_mods

        subs = pysubs2.SSAFile()
        for i, t in enumerate(texts):
            subs.events.append(
                pysubs2.SSAEvent(start=(i * 3 + 1) * 1000, end=(i * 3 + 3) * 1000, text=t)
            )
        path = tmp_path / "t.ass"
        subs.save(str(path), format_="ass")
        apply_mods(str(path), [ModConfig(mod=ModName.HI_REMOVAL)], dry_run=False)
        return [e.text for e in pysubs2.load(str(path), format_="ass").events]

    return _run


def test_override_tags_survive_an_edit(process_ass):
    """The HI marker goes; \\an8 and the italics tags stay."""
    out = process_ass([r"{\an8}[SEUFZT]{\i1} Ich komme gleich.{\i0}"])
    assert len(out) == 1
    assert r"\an8" in out[0], f"positioning tag lost: {out[0]!r}"
    assert r"\i1" in out[0] and r"\i0" in out[0], f"italics lost: {out[0]!r}"
    assert "SEUFZT" not in out[0]
    assert "Ich komme gleich." in out[0]


def test_positioned_sign_is_untouched(process_ass):
    """A cue the pipeline does not edit keeps its text and tags verbatim."""
    sign = r"{\an8\pos(960,120)}Ein Schild am Tor"
    assert process_ass([sign]) == [sign]


def test_bracketed_sdh_removal_keeps_tags(process_ass):
    """Structural HI markers are still removed — without taking the tags along."""
    out = process_ass([r"{\an8}[DOOR SLAMS] Guten Morgen."])
    assert r"\an8" in out[0], f"positioning tag lost: {out[0]!r}"
    assert "DOOR SLAMS" not in out[0]
    assert "Guten Morgen." in out[0]


def test_cue_that_becomes_empty_is_still_dropped(process_ass):
    """A cue whose entire content was an HI marker still disappears."""
    out = process_ass([r"{\an8}[DOOR SLAMS]", "Echte Zeile."])
    assert out == ["Echte Zeile."]
