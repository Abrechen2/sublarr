"""A frozen copy of the pipeline that damaged the subtitles (Sublarr <= 1.6.5).

This exists for exactly one reason: **to prove a file is safe to overwrite.**

Repair restores a subtitle by re-downloading the pristine original from the
provider. Before it writes, it has to know that the file currently on disk is
pipeline damage and not something the user edited by hand. The proof is a
replay: run this frozen buggy pipeline over the pristine original and require
the result to equal the file on disk, byte for byte. Anything else means a human
touched it — and repair leaves it alone.

Because the proof is only as good as the replay, this code must NOT be "fixed",
tidied, or kept in sync with the live pipeline. It is a historical artefact and
has to stay bug-for-bug identical to what 1.6.5 shipped. ``common_fixes`` was
never part of the bug and is unchanged, so it is imported from the live module
rather than frozen here.

The bug, for the record: the interjection list below is English, it was compiled
into a bare ``\\b(?:...)\\b`` substitution, and it was applied to subtitles of
every language, anywhere in a sentence. In German "um", "eh" and "nah" are
ordinary words.
"""

from __future__ import annotations

import io
import re

import pysubs2

from subtitle_types import Change, _ms_to_str

# Verbatim from backend/data/hi_interjections.txt as it shipped in 1.6.5.
LEGACY_INTERJECTIONS: list[str] = [
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
    "Huh",
    "Ow",
    "Phew",
    "Whoa",
    "Ew",
    "Yeah",
    "Yep",
    "Nope",
    "Nah",
    "Shh",
    "Psst",
    "Yikes",
    "Ouch",
    "Tsk",
    "Pfft",
    "Bah",
    "Meh",
    "Heh",
    "Hmph",
    "Pff",
]


def _legacy_interjection_pattern() -> re.Pattern:
    escaped = sorted([re.escape(w) for w in LEGACY_INTERJECTIONS], key=len, reverse=True)
    return re.compile(r"\b(?:" + "|".join(escaped) + r")\b", re.IGNORECASE)


def _legacy_hi_removal(subs: pysubs2.SSAFile, options: dict) -> list[Change]:
    """The 1.6.5 ``_apply_hi_removal`` — reproduced, bugs included."""
    from hi_remover import remove_hi_markers

    opts = {
        "square_brackets": True,
        "round_brackets": True,
        "curly_brackets": True,
        "japanese_parens": True,
        "music_symbols": True,
        "speaker_labels": True,
        "all_caps_lines": True,
        "all_caps_min_length": 4,
        "interjections": True,
        "music_hash_lines": True,
        **options,
    }

    interjection_pattern = _legacy_interjection_pattern()

    extra_patterns = []
    if opts["curly_brackets"]:
        extra_patterns.append(re.compile(r"\{[^}]{3,}\}", re.IGNORECASE))
    if opts["japanese_parens"]:
        extra_patterns.append(re.compile(r"[（][^）]{1,}[）]"))
    if opts["music_hash_lines"]:
        extra_patterns.append(re.compile(r"^[#♪♫\s]+$", re.MULTILINE))

    changes: list[Change] = []
    indices_to_remove: list[int] = []

    from subtitle_processor import _mark_multiline_bracket_events

    _mark_multiline_bracket_events(subs, indices_to_remove)

    for i, event in enumerate(subs.events):
        if event.is_comment or i in indices_to_remove:
            continue

        original = event.plaintext.strip()
        if not original:
            continue

        cleaned = remove_hi_markers(original)

        for pat in extra_patterns:
            cleaned = pat.sub("", cleaned).strip()

        # The all-caps rule as it was: any line equal to its own upper-casing.
        # Punctuation survives .upper(), so whole sentences qualified.
        if opts["all_caps_lines"]:
            lines_out = []
            for line in cleaned.split("\n"):
                stripped = line.strip()
                if (
                    stripped
                    and len(stripped) >= opts["all_caps_min_length"]
                    and stripped == stripped.upper()
                    and any(c.isalpha() for c in stripped)
                ):
                    pass
                else:
                    lines_out.append(line)
            cleaned = "\n".join(lines_out).strip()

        # The bug: every occurrence, any language, anywhere in the sentence.
        if opts["interjections"] and interjection_pattern:
            cleaned = interjection_pattern.sub("", cleaned).strip()

        if cleaned != original:
            ts = f"{_ms_to_str(event.start)} --> {_ms_to_str(event.end)}"
            changes.append(Change(i, ts, original, cleaned, "hi_removal"))
            if cleaned:
                event.text = cleaned
            else:
                indices_to_remove.append(i)

    for i in sorted(set(indices_to_remove), reverse=True):
        del subs.events[i]
        for c in changes:
            if c.event_index > i:
                c.event_index -= 1

    return changes


_SURVIVOR_KEY = "_sublarr_origin_index"


def replay_legacy_pipeline_with_survivors(
    content: bytes,
    *,
    fmt: str = "srt",
    common_fixes: bool = True,
    hi_removal: bool = True,
    common_fixes_options: dict | None = None,
    hi_removal_options: dict | None = None,
) -> tuple[bytes, list[int]]:
    """Replay the damaged pipeline and report which original cues survived it.

    Returns ``(damaged_bytes, survivors)`` where ``survivors[i]`` is the index of
    the original event that ended up as event ``i`` of the damaged file. Restore
    needs that mapping to put the synced timings back on the right cues.

    Mods run in the order the live pipeline used: common_fixes, then hi_removal.
    """
    subs = pysubs2.SSAFile.from_string(content.decode("utf-8", errors="replace"), format_=fmt)

    # Tag every event so it can be traced through the deletions the mods perform.
    origin: dict[int, int] = {}
    for i, event in enumerate(subs.events):
        origin[id(event)] = i

    if common_fixes:
        from common_fixes import apply_common_fixes

        apply_common_fixes(subs, common_fixes_options or {})

    if hi_removal:
        _legacy_hi_removal(subs, hi_removal_options or {})

    survivors = [origin[id(e)] for e in subs.events if id(e) in origin]

    buf = io.StringIO()
    subs.to_file(buf, format_=fmt)
    return buf.getvalue().encode("utf-8"), survivors


def replay_legacy_pipeline(content: bytes, **kwargs) -> bytes:
    """Return ``content`` as the damaged pipeline would have left it on disk."""
    damaged, _survivors = replay_legacy_pipeline_with_survivors(content, **kwargs)
    return damaged
