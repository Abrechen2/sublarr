"""Restoring a damaged subtitle must bring the words back without losing the sync.

The damage was purely textual: words cut out of cues, some cues deleted whole.
But the file on disk has since been *synced* to the video — its timings are
better than the provider's. Verified on the real library: replaying the buggy
pipeline over the pristine original reproduces the on-disk TEXT exactly, while
the bytes differ only because every timestamp moved (a ~950 ms sync shift).

So restore transplants the pristine text onto the synced timings, and rebuilds
the cues the old pipeline deleted using the time model fitted from the cues that
survived. Nothing is re-synced, nothing is lost.

If the replay does not reproduce the on-disk text, a human edited the file and
restore refuses — that is the whole point of the proof.
"""

import io

import pysubs2
import pytest

from services.repair.legacy_transform import replay_legacy_pipeline
from services.repair.restore import RestoreRefusedError, restore_subtitle


def _build(cues, shift_ms=0):
    subs = pysubs2.SSAFile()
    for start, end, text in cues:
        subs.events.append(pysubs2.SSAEvent(start=start + shift_ms, end=end + shift_ms, text=text))
    buf = io.StringIO()
    subs.to_file(buf, format_="srt")
    return buf.getvalue().encode("utf-8")


def _read(raw):
    subs = pysubs2.SSAFile.from_string(raw.decode("utf-8"), format_="srt")
    return [(e.start, e.end, e.plaintext.strip()) for e in subs.events]


ORIGINAL_CUES = [
    (1000, 3000, "darf ich dich um eine Sache bitten?"),
    (4000, 6000, "PHONE RINGING"),  # the old pipeline deleted this one outright
    (7000, 9000, "Ich bin hier, um zu helfen."),
    (10000, 12000, "Das ist eh klar."),
]
SYNC_SHIFT = -950


@pytest.fixture
def original():
    return _build(ORIGINAL_CUES)


@pytest.fixture
def damaged_on_disk(original):
    """What 1.6.5 left behind, then synced: words gone, one cue gone, times shifted."""
    damaged = replay_legacy_pipeline(original, fmt="srt")
    subs = pysubs2.SSAFile.from_string(damaged.decode("utf-8"), format_="srt")
    for e in subs.events:
        e.start += SYNC_SHIFT
        e.end += SYNC_SHIFT
    buf = io.StringIO()
    subs.to_file(buf, format_="srt")
    return buf.getvalue().encode("utf-8")


def test_words_come_back(original, damaged_on_disk):
    restored = _read(restore_subtitle(original=original, on_disk=damaged_on_disk, fmt="srt"))
    texts = [t for _s, _e, t in restored]
    assert "darf ich dich um eine Sache bitten?" in texts
    assert "Ich bin hier, um zu helfen." in texts
    assert "Das ist eh klar." in texts


def test_the_sync_is_preserved(original, damaged_on_disk):
    """Surviving cues keep the timings they had on disk — the synced ones."""
    restored = _read(restore_subtitle(original=original, on_disk=damaged_on_disk, fmt="srt"))
    by_text = {t: (s, e) for s, e, t in restored}
    assert by_text["darf ich dich um eine Sache bitten?"] == (1000 + SYNC_SHIFT, 3000 + SYNC_SHIFT)
    assert by_text["Ich bin hier, um zu helfen."] == (7000 + SYNC_SHIFT, 9000 + SYNC_SHIFT)


def test_a_deleted_cue_is_rebuilt_on_the_synced_timeline(original, damaged_on_disk):
    """The cue the old pipeline dropped comes back, shifted onto the synced timeline."""
    restored = _read(restore_subtitle(original=original, on_disk=damaged_on_disk, fmt="srt"))
    by_text = {t: (s, e) for s, e, t in restored}
    assert "PHONE RINGING" in by_text, "the deleted cue was not restored"
    assert by_text["PHONE RINGING"] == (4000 + SYNC_SHIFT, 6000 + SYNC_SHIFT)


def test_cue_order_is_preserved(original, damaged_on_disk):
    restored = _read(restore_subtitle(original=original, on_disk=damaged_on_disk, fmt="srt"))
    starts = [s for s, _e, _t in restored]
    assert starts == sorted(starts)
    assert len(restored) == len(ORIGINAL_CUES)


def test_a_hand_edited_file_is_refused(original, damaged_on_disk):
    """If the replay cannot reproduce the on-disk text, a human touched it."""
    subs = pysubs2.SSAFile.from_string(damaged_on_disk.decode("utf-8"), format_="srt")
    subs.events[0].text = "Von Hand geändert."
    buf = io.StringIO()
    subs.to_file(buf, format_="srt")
    edited = buf.getvalue().encode("utf-8")

    with pytest.raises(RestoreRefusedError):
        restore_subtitle(original=original, on_disk=edited, fmt="srt")


def test_an_undamaged_file_is_refused(original):
    """Nothing to restore — do not rewrite a file that was never damaged."""
    with pytest.raises(RestoreRefusedError):
        restore_subtitle(original=original, on_disk=original, fmt="srt")
