"""Rebuild a damaged subtitle from its pristine original — without losing the sync.

The pre-1.6.6 pipeline damaged subtitles *textually*: it cut words out of cues
and deleted some cues outright. Afterwards the file was usually synced to the
video, so the timings on disk are better than the provider's. Overwriting with
the provider file would restore the words and throw the sync away.

So restore does three things:

1. **Prove the file is safe to touch.** Replay the frozen buggy pipeline over the
   original. Its cue texts must equal the cue texts on disk. If they do not, a
   human edited the file — refuse, and leave it alone.
2. **Transplant.** Every cue that survived the old pipeline keeps its on-disk
   (synced) timing and gets its pristine text back.
3. **Rebuild what was deleted.** Cues the old pipeline dropped are reinserted,
   their original timings mapped onto the synced timeline via the linear model
   fitted from the surviving cues.
"""

from __future__ import annotations

import io

import pysubs2

from services.repair.legacy_transform import replay_legacy_pipeline_with_survivors


class RestoreRefusedError(Exception):
    """The file must not be rewritten — with the reason why."""


def _load(raw: bytes, fmt: str) -> pysubs2.SSAFile:
    return pysubs2.SSAFile.from_string(raw.decode("utf-8", errors="replace"), format_=fmt)


def _dump(subs: pysubs2.SSAFile, fmt: str) -> bytes:
    buf = io.StringIO()
    subs.to_file(buf, format_=fmt)
    return buf.getvalue().encode("utf-8")


def _texts(subs: pysubs2.SSAFile) -> list[str]:
    return [e.plaintext.strip() for e in subs.events]


def _fit_time_model(pairs: list[tuple[int, int]]) -> tuple[float, float]:
    """Least-squares fit of on-disk = scale * original + offset.

    ffsubsync/alass apply a shift, sometimes a framerate rescale, so a linear
    model covers both. With a single pair we can only assume a pure shift.
    """
    if not pairs:
        return 1.0, 0.0
    if len(pairs) == 1:
        o, d = pairs[0]
        return 1.0, float(d - o)

    n = len(pairs)
    sum_o = sum(o for o, _ in pairs)
    sum_d = sum(d for _, d in pairs)
    sum_oo = sum(o * o for o, _ in pairs)
    sum_od = sum(o * d for o, d in pairs)
    denom = n * sum_oo - sum_o * sum_o
    if denom == 0:
        return 1.0, (sum_d - sum_o) / n
    scale = (n * sum_od - sum_o * sum_d) / denom
    offset = (sum_d - scale * sum_o) / n
    return scale, offset


def restore_subtitle(*, original: bytes, on_disk: bytes, fmt: str = "srt", **replay_opts) -> bytes:
    """Return the repaired subtitle, or raise :class:`RestoreRefusedError`."""
    orig = _load(original, fmt)
    disk = _load(on_disk, fmt)

    replayed, survivors = replay_legacy_pipeline_with_survivors(original, fmt=fmt, **replay_opts)
    replay_subs = _load(replayed, fmt)

    if _texts(replay_subs) == _texts(orig) and len(orig.events) == len(disk.events):
        raise RestoreRefusedError("the old pipeline changed nothing here — nothing to restore")

    if _texts(replay_subs) != _texts(disk):
        raise RestoreRefusedError(
            "the file on disk is not what the old pipeline would have produced — "
            "it was edited by hand"
        )

    # Surviving cue i on disk corresponds to original event survivors[i].
    pairs = [
        (orig.events[oi].start, disk.events[i].start)
        for i, oi in enumerate(survivors)
        if oi < len(orig.events) and i < len(disk.events)
    ]
    scale, offset = _fit_time_model(pairs)

    disk_by_orig_index = {oi: disk.events[i] for i, oi in enumerate(survivors)}

    out = pysubs2.SSAFile()
    out.info = orig.info
    out.styles = orig.styles

    for oi, event in enumerate(orig.events):
        restored = event.copy()
        synced = disk_by_orig_index.get(oi)
        if synced is not None:
            # Survived the old pipeline: keep the synced timing, restore the text.
            restored.start = synced.start
            restored.end = synced.end
        else:
            # Deleted by the old pipeline: map its original timing onto the
            # synced timeline so it lands where it belongs.
            restored.start = int(round(scale * event.start + offset))
            restored.end = int(round(scale * event.end + offset))
        out.events.append(restored)

    out.sort()
    return _dump(out, fmt)
