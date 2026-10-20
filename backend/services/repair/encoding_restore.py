"""Restore the letters the old UTF-8-with-replacement decode destroyed.

Until the encoding fix, a subtitle the provider delivered in a legacy codepage
(cp1250/1251/1252/1253, GBK, ...) was decoded as UTF-8 with ``errors="replace"``
before it was saved: every umlaut, accent or Cyrillic letter on disk is "�".
Those letters are gone from the file, so the provider's original is the only
way back — re-downloaded and now decoded correctly.

The proof is per cue. A cue on disk is a mask: each run of k "�" stood for one
to 3k letters that were not ASCII, everything else must match the original's
cue exactly. A cue matches the original cue at the same position when both
files still have the same cues, or else the one cue of the whole original that
fits; a mask several cues fit is not guessed. Cues edited since (HI removal,
a manual fix) do not match and keep their "�". Timings and everything else
about the file on disk stay as they are — a sync after download is kept.
"""

from __future__ import annotations

import io
import re

import pysubs2

from services.repair.restore import RestoreRefusedError

MANGLED = "�"
NOTHING_TO_RESTORE = "no replacement characters in the file on disk"

_MANGLED_RUN = re.compile(f"({MANGLED}+)")


def has_mangled_letters(raw: bytes) -> bool:
    """Whether a sidecar carries the replacement characters of the old decode."""
    return MANGLED.encode("utf-8") in raw


def damaged_cues(raw: bytes, fmt: str = "srt") -> int:
    """How many cues of a sidecar still carry replacement characters."""
    return sum(MANGLED in event.text for event in _load(raw, fmt).events)


def _load(raw: bytes, fmt: str) -> pysubs2.SSAFile:
    from subtitle_encoding import decode_subtitle_bytes

    return pysubs2.SSAFile.from_string(decode_subtitle_bytes(raw), format_=fmt)


def _dump(subs: pysubs2.SSAFile, fmt: str) -> bytes:
    buf = io.StringIO()
    subs.to_file(buf, format_=fmt)
    return buf.getvalue().encode("utf-8")


def _mask(text: str) -> re.Pattern:
    parts = []
    for part in _MANGLED_RUN.split(text):
        if part.startswith(MANGLED):
            # One "�" replaced the longest invalid run of up to three bytes,
            # so a run of k stood for 1..3k letters of a single-byte codepage.
            parts.append(f"[^\\x00-\\x7f]{{1,{3 * len(part)}}}")
        elif part:
            parts.append(re.escape(part))
    return re.compile("".join(parts), re.DOTALL)


def _restored_text(index: int, mask: re.Pattern, originals: list[str], aligned: bool) -> str | None:
    if aligned and mask.fullmatch(originals[index]):
        return originals[index]
    fits = {text for text in originals if mask.fullmatch(text)}
    return fits.pop() if len(fits) == 1 else None


def restore_encoding(
    *, original: bytes, on_disk: bytes, fmt: str = "srt", language: str | None = None
) -> bytes:
    """Return ``on_disk`` with every provable cue's letters taken from ``original``.

    Cues that cannot be proven keep their "�"; :func:`damaged_cues` on the
    result says how many.

    Args:
        original: The provider's file, as the download path normalises it now.
        on_disk: The sidecar the old decode wrote.
        fmt: "srt", "ass", ...
        language: The subtitle's language, used if ``original`` is not UTF-8 yet.

    Raises:
        RestoreRefusedError: Nothing to restore, an original that is no better,
            or no cue of the original matches the file on disk.
    """
    from subtitle_encoding import ensure_utf8

    disk = _load(on_disk, fmt)
    if not any(MANGLED in event.text for event in disk.events):
        raise RestoreRefusedError(NOTHING_TO_RESTORE)

    source = _load(ensure_utf8(original, language=language), fmt)
    originals = [event.text for event in source.events]
    if any(MANGLED in text for text in originals):
        raise RestoreRefusedError("the original has replacement characters itself")

    aligned = len(originals) == len(disk.events)
    restored = 0
    for index, event in enumerate(disk.events):
        if MANGLED not in event.text:
            continue
        text = _restored_text(index, _mask(event.text), originals, aligned)
        if text is not None:
            event.text = text
            restored += 1

    if not restored:
        raise RestoreRefusedError("no cue of the original matches the file on disk")
    return _dump(disk, fmt)
