# backend/subtitle_processor.py
"""Central subtitle processing orchestrator."""

from __future__ import annotations

import logging
import os
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
    base, ext = os.path.splitext(path)
    return f"{base}.bak{ext}"


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
            changes = _apply_hi_removal(subs, mod_config.options)
        elif mod_config.mod == ModName.CREDIT_REMOVAL:
            changes = _apply_credit_removal(subs, mod_config.options)
        else:
            changes = []
        all_changes.extend(changes)

    backed_up = False
    if not dry_run and all_changes:
        bak_path = _make_bak_path(path)
        if not os.path.exists(bak_path):
            shutil.copy2(path, bak_path)
            backed_up = True
        subs.save(path, format_=fmt, encoding="utf-8")

    return ProcessingResult(
        changes=all_changes,
        backed_up=backed_up,
        output_path=path,
        dry_run=dry_run,
    )


def _apply_hi_removal(subs: pysubs2.SSAFile, options: dict) -> list[Change]:
    import re

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

    interjection_pattern = _build_interjection_pattern()

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

        cleaned = remove_hi_markers(original)

        for pat in extra_patterns:
            cleaned = pat.sub("", cleaned).strip()

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


def _build_interjection_pattern():
    import re

    try:
        from config import get_settings

        settings = get_settings()
        raw = getattr(settings, "hi_interjections_list", "").strip()
    except Exception as exc:
        logger.warning("_build_interjection_pattern: failed to load settings: %s", exc)
        raw = ""

    if raw:
        items = [l.strip() for l in raw.splitlines() if l.strip()]
    else:
        data_file = os.path.join(os.path.dirname(__file__), "data", "hi_interjections.txt")
        if not os.path.exists(data_file):
            return None
        with open(data_file, encoding="utf-8") as f:
            items = [l.strip() for l in f if l.strip()]

    if not items:
        return None

    escaped = sorted([re.escape(w) for w in items], key=len, reverse=True)
    return re.compile(r"\b(?:" + "|".join(escaped) + r")\b", re.IGNORECASE)


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
