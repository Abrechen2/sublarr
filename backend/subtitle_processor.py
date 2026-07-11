# backend/subtitle_processor.py
"""Central subtitle processing orchestrator."""

from __future__ import annotations

import logging
import os
import re
import shutil
from dataclasses import dataclass, field
from enum import StrEnum

import pysubs2

from subtitle_types import Change, _ms_to_str

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".srt", ".ass", ".ssa", ".vtt"}


class ModName(StrEnum):
    COMMON_FIXES = "common_fixes"
    HI_REMOVAL = "hi_removal"
    CREDIT_REMOVAL = "credit_removal"


_MOD_ORDER = [ModName.COMMON_FIXES, ModName.HI_REMOVAL, ModName.CREDIT_REMOVAL]


@dataclass
class ModConfig:
    mod: ModName
    options: dict = field(default_factory=dict)


@dataclass
class ProcessingResult:
    changes: list[Change]
    backed_up: bool
    output_path: str
    dry_run: bool


def _make_bak_path(path: str) -> str:
    """Return the canonical backup path for ``path``.

    Thin wrapper around :func:`subtitle_filename.bak_path_for` so callers
    inside this module keep their familiar import. The bak target lives
    under ``<dir>/.sublarr/backups/`` to stay invisible to media servers
    that would otherwise misparse ``bak`` as the Bashkir ISO-639 code.
    """
    from subtitle_filename import bak_path_for

    return bak_path_for(path)


def apply_mods(path: str, mods: list[ModConfig], dry_run: bool = False) -> ProcessingResult:
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")
    ext = os.path.splitext(path)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported format: {ext!r}. Supported: {SUPPORTED_EXTENSIONS}")

    mods_by_name = {m.mod: m for m in mods}
    ordered_mods = [mods_by_name[n] for n in _MOD_ORDER if n in mods_by_name]

    fmt = ext.lstrip(".")  # ".srt" → "srt", ".ass" → "ass", etc.
    subs = pysubs2.load(path, format_=fmt, encoding="utf-8")
    all_changes: list[Change] = []

    for mod_config in ordered_mods:
        if mod_config.mod == ModName.COMMON_FIXES:
            from common_fixes import apply_common_fixes

            changes = apply_common_fixes(subs, mod_config.options)
        elif mod_config.mod == ModName.HI_REMOVAL:
            changes = _apply_hi_removal(subs, mod_config.options, fmt=fmt)
        elif mod_config.mod == ModName.CREDIT_REMOVAL:
            changes = _apply_credit_removal(subs, mod_config.options)
        else:
            changes = []
        all_changes.extend(changes)

    backed_up = False
    if not dry_run and all_changes:
        from subtitle_filename import find_existing_bak

        # find_existing_bak checks the canonical hidden location AND the legacy
        # sibling one. Checking only the canonical path (as this did) meant that
        # after the backups moved to .sublarr/backups/ every pre-migration file
        # looked un-backed-up — so the "pristine" copy was silently re-created
        # from an ALREADY-processed file, destroying the only record of the
        # original. The bak is a single-slot undo; it must never be rewritten
        # once one exists anywhere.
        if find_existing_bak(path) is None:
            bak_path = _make_bak_path(path)
            os.makedirs(os.path.dirname(bak_path), exist_ok=True)
            shutil.copy2(path, bak_path)
            backed_up = True
        from utils.atomic_write import atomic_save_subs

        atomic_save_subs(subs, path, format_=fmt, encoding="utf-8")

    return ProcessingResult(
        changes=all_changes,
        backed_up=backed_up,
        output_path=path,
        dry_run=dry_run,
    )


_ASS_OVERRIDE_RE = re.compile(r"\{[^}]*\}")

# Private-use sentinels around the tag index. They are neither word characters
# nor capitals nor punctuation, so no HI pattern can match through a masked tag
# or mistake one for content.
_MASK_OPEN = ""
_MASK_CLOSE = ""
_TAG_MASK_RE = re.compile(_MASK_OPEN + r"(\d+)" + _MASK_CLOSE)


def _mask_ass_tags(text: str) -> tuple[str, list[str]]:
    """Replace ASS override blocks with placeholders so text edits cannot eat them."""
    tags: list[str] = []

    def _stash(match: re.Match) -> str:
        tags.append(match.group(0))
        return f"{_MASK_OPEN}{len(tags) - 1}{_MASK_CLOSE}"

    return _ASS_OVERRIDE_RE.sub(_stash, text), tags


def _unmask_ass_tags(text: str, tags: list[str]) -> str:
    """Put the override blocks back where their placeholders ended up."""
    return _TAG_MASK_RE.sub(lambda m: tags[int(m.group(1))], text)


def _apply_hi_removal(subs: pysubs2.SSAFile, options: dict, fmt: str = "srt") -> list[Change]:
    from hi_remover import remove_hi_markers

    is_ass = fmt in ("ass", "ssa")

    opts = {
        "square_brackets": True,
        "round_brackets": True,
        "curly_brackets": True,
        "japanese_parens": True,
        "music_symbols": True,
        "speaker_labels": True,
        "all_caps_lines": True,
        "all_caps_min_length": 4,
        "music_hash_lines": True,
        **options,
    }

    caps_pattern = _build_all_caps_pattern(subs, opts, is_ass=is_ass)

    extra_patterns = []
    if opts["curly_brackets"]:
        extra_patterns.append(re.compile(r"\{[^}]{3,}\}", re.IGNORECASE))
    if opts["japanese_parens"]:
        extra_patterns.append(re.compile(r"[\uFF08][^\uFF09]{1,}[\uFF09]"))
    if opts["music_hash_lines"]:
        extra_patterns.append(re.compile(r"^[#♪♫\s]+$", re.MULTILINE))

    changes: list[Change] = []
    indices_to_remove: list[int] = []

    _mark_multiline_bracket_events(subs, indices_to_remove)

    for i, event in enumerate(subs.events):
        if event.is_comment or i in indices_to_remove:
            continue

        original = event.plaintext.strip()
        if not original:
            continue

        # On ASS/SSA the override blocks ({\an8}, {\i1}, karaoke) are masked out
        # before the HI patterns run and restored afterwards. Reading plaintext
        # and writing the result back into event.text used to drop every tag on
        # any cue the pipeline touched — positioning and italics simply vanished.
        #
        # SRT keeps working on plaintext exactly as before. Feeding it raw
        # event.text instead would rewrite every cue containing an escape such as
        # \h (a hard space, which some SRTs use to align text): the comparison
        # against plaintext would always differ, and the rewrite turned the
        # escapes into literal runs of spaces. Only ASS needs the tag treatment,
        # and on SRT a literal {...} is not formatting — curly_brackets is meant
        # to remove it.
        if is_ass:
            work, tags = _mask_ass_tags(event.text)
            work = work.replace("\\N", "\n").replace("\\h", " ")
        else:
            work, tags = original, []

        cleaned = remove_hi_markers(work)

        for pat in extra_patterns:
            cleaned = pat.sub("", cleaned).strip()

        # The caps rule judges the WHOLE cue, not each line on its own. A
        # capitalised sentence wrapped across two subtitle lines has a first line
        # that carries no punctuation of its own — judged line by line it looks
        # like a marker, and half the sentence was deleted:
        #   "UM DIE DREHBUCHSCHREIBERIN\nZU BESCHÜTZEN, ODER?" -> "ZU BESCHÜTZEN, ODER?"
        # Joined, the comma and the question mark identify it as prose. The
        # class admits \s, so a genuine two-line marker still matches as a whole.
        if caps_pattern is not None and caps_pattern.match(cleaned.strip()):
            cleaned = ""

        cleaned = cleaned.strip()
        if is_ass:
            cleaned = _unmask_ass_tags(cleaned, tags).replace("\n", "\\N")
            cleaned_plain = _ASS_OVERRIDE_RE.sub("", cleaned).replace("\\N", "\n").strip()
        else:
            cleaned_plain = cleaned

        if cleaned_plain != original:
            ts = f"{_ms_to_str(event.start)} --> {_ms_to_str(event.end)}"
            changes.append(Change(i, ts, original, cleaned_plain, "hi_removal"))
            if cleaned_plain:
                event.text = cleaned
            else:
                indices_to_remove.append(i)

    for i in sorted(set(indices_to_remove), reverse=True):
        del subs.events[i]
        for c in changes:
            if c.event_index > i:
                c.event_index -= 1

    return changes


def _mark_multiline_bracket_events(subs: pysubs2.SSAFile, to_remove: list[int]) -> None:
    import re

    open_pattern = re.compile(r"\[[\w\s]+$")
    close_pattern = re.compile(r"^[\w\s]+\]")

    for i in range(len(subs.events) - 1):
        a = subs.events[i].plaintext.strip()
        b = subs.events[i + 1].plaintext.strip()
        if open_pattern.search(a) and close_pattern.match(b):
            if i not in to_remove:
                to_remove.append(i)
            if (i + 1) not in to_remove:
                to_remove.append(i + 1)


def _build_all_caps_pattern(subs: pysubs2.SSAFile, opts: dict, is_ass: bool = False):
    """Return the all-caps HI-marker pattern, or None when the rule must not run.

    Mirrors Subzero's ``HI_all_caps`` (the mod Bazarr uses)::

        (?u)(^(?=.*[A-ZÀ-Ž&+]{4,})[A-ZÀ-Ž-_\\s&+]+$)   # guard: not only_uppercase

    The character class admits only capitals, spaces and ``-_&+``. Sentence
    punctuation is deliberately absent: a capitalised line carrying a comma or a
    question mark is a *sentence*, not a sound cue. The previous check was
    ``text == text.upper()``, and punctuation is immune to ``.upper()`` — so
    fully capitalised dialogue and anime song lyrics (OP/ED karaoke is
    conventionally typeset in caps) were deleted outright.

    Subzero's ``only_uppercase`` guard is honoured too: when the whole subtitle
    is capitalised that is a typesetting style, not a stream of HI markers, and
    applying the rule would empty the file.

    The rule is SRT-only. ASS has real typesetting: a capitalised line there is a
    *sign* — positioned and styled (``\\an8``, ``\\pos``, its own style) — or song
    karaoke. Capitalisation carries no HI meaning in a format that can express
    intent directly, and applying the heuristic would delete exactly the content
    the typesetter put there.
    """
    import re

    if is_ass or not opts.get("all_caps_lines"):
        return None

    texts = [e.plaintext.strip() for e in subs.events if not e.is_comment and e.plaintext.strip()]
    if not texts:
        return None
    if all(t == t.upper() for t in texts):
        logger.debug("all_caps_lines: subtitle is entirely uppercase — rule skipped")
        return None

    min_caps = max(int(opts.get("all_caps_min_length", 4)), 1)
    return re.compile(rf"^(?=.*[A-ZÀ-Ž&+]{{{min_caps},}})[A-ZÀ-Ž\-_\s&+]+$", re.UNICODE)


def _apply_credit_removal(subs: pysubs2.SSAFile, options: dict) -> list[Change]:
    from credit_remover import _is_credit_line

    if not subs.events:
        return []

    total_end_ms = max(e.end for e in subs.events)
    changes: list[Change] = []
    to_remove: list[int] = []

    for i, event in enumerate(subs.events):
        if event.is_comment:
            continue
        text = event.plaintext.strip()
        if _is_credit_line(text, total_end_ms=total_end_ms, event_start_ms=event.start):
            ts = f"{_ms_to_str(event.start)} --> {_ms_to_str(event.end)}"
            changes.append(Change(i, ts, text, "", "credit_removal"))
            to_remove.append(i)

    for i in sorted(to_remove, reverse=True):
        del subs.events[i]

    return changes


def resolve_config(global_cfg: dict, series_cfg: dict | None) -> dict:
    """Merge series-level override on top of global config.

    series_cfg values:
        None or missing key → use global value
        True / False        → override global value
    """
    result = dict(global_cfg)
    for key, value in (series_cfg or {}).items():
        if value is not None:
            result[key] = value
    return result
