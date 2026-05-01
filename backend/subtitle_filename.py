"""Single source of truth for subtitle filename parsing.

Sidecar subtitles in this project follow the pattern

    <base>.<lang>(.<modifier>)*.<ext>

where:
  * ``base``     is the video filename without its container extension
                 (e.g. ``"Show - S01E02 - Episode Title"``)
  * ``lang``     is an ISO-639-1/2 language code (2-3 lowercase letters)
  * ``modifier`` is an optional descriptor from MODIFIERS — multiple
                 modifiers can stack (``en.hi.bak.srt`` = the HI variant
                 of an English sub that the user later modified, with a
                 backup of the original HI version)
  * ``ext``      is one of SUBTITLE_EXTS

Modifier semantics:
  * ``bak``      = backup created by ``subtitle_processor.apply_mods``
                   before HI-removal / common-fixes / credit-removal.
                   These files MUST be hidden from the active subtitle
                   list — they are restore artefacts, not playable subs.
  * ``hi``       = Hearing Impaired (extra annotations like *[door slams]*)
  * ``sdh``      = Subtitles for the Deaf and Hard-of-hearing
  * ``forced``   = forced subs (foreign-language passages only)
  * ``cc``       = Closed Captions (US convention; treated like SDH)

The parser uses a right-to-left "suffix stripper" so that arbitrary
modifier stacks are accepted without growing the regex. This was the
explicit design choice over a single regex (per Gemini Pro review on
2026-05-01) — single regex needs an exponential alternation list to
cover modifier orderings, the stripper handles N modifiers in O(N).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

# Subtitle file extensions recognised by Sublarr. Keep aligned with
# routes.subtitles.helpers._SUBTITLE_EXTS and dedup_engine.SUBTITLE_EXTENSIONS.
SUBTITLE_EXTS: frozenset[str] = frozenset({"srt", "ass", "ssa", "vtt"})

# Modifier tokens that may appear between the language and the extension.
# Order does not matter; the parser collects them all into a sorted list.
# Keep aligned with the regex in dedup_engine.py.
MODIFIERS: frozenset[str] = frozenset({"hi", "bak", "forced", "sdh", "cc"})

# Lowercase ISO-639-1 (2 letters) and ISO-639-2 (3 letters). The lookup
# table in config_language_data is the authoritative list, but for
# filename parsing we just need a syntactic check — anything outside
# this shape is rejected so accidental "Mr. Saturday.srt"-like names
# never produce ``language="rd"``.
_LANG_RE = re.compile(r"^[a-z]{2,3}$")


@dataclass(frozen=True)
class ParsedFilename:
    """Result of :func:`parse_subtitle_filename`.

    ``modifiers`` is a tuple of zero or more modifier tokens in the order
    they appear in the filename (rightmost first as the parser pops
    them). ``is_backup`` is a convenience for the most common consumer
    check — equivalent to ``"bak" in modifiers``.
    """

    base: str
    language: str
    modifiers: tuple[str, ...]
    extension: str

    @property
    def is_backup(self) -> bool:
        return "bak" in self.modifiers

    @property
    def primary_modifier(self) -> str | None:
        """The non-bak modifier if any (UI badge candidate).

        ``bak`` is excluded because callers that surface it never display
        it as a sidecar in the first place. ``None`` when the file has
        no display-relevant modifier.
        """
        for m in self.modifiers:
            if m != "bak":
                return m
        return None


def parse_subtitle_filename(path: str) -> ParsedFilename | None:
    """Parse a subtitle sidecar path into its components.

    Returns ``None`` when the filename does not match the
    ``<base>.<lang>(.<modifier>)*.<ext>`` shape. Callers that just want
    to know "is this a subtitle sidecar" can rely on a non-``None``
    return value.

    Examples
    --------
    >>> r = parse_subtitle_filename("/m/Show.S01E01.de.srt")
    >>> r.language, r.modifiers, r.is_backup
    ('de', (), False)
    >>> r = parse_subtitle_filename("/m/Show.S01E01.en.bak.srt")
    >>> r.language, r.modifiers, r.is_backup
    ('en', ('bak',), True)
    >>> r = parse_subtitle_filename("/m/Show.S01E01.en.hi.bak.srt")
    >>> r.language, r.modifiers, r.is_backup, r.primary_modifier
    ('en', ('bak', 'hi'), True, 'hi')
    >>> parse_subtitle_filename("/m/Show.S01E01.mkv") is None
    True
    >>> parse_subtitle_filename("/m/Show.S01E01.srt") is None  # no language
    True
    """
    filename = os.path.basename(path)
    parts = filename.split(".")
    if len(parts) < 3:
        # Need at least <base>.<lang>.<ext> — no modifier-less, no-lang
        # files like "subs.srt" qualify as sidecars.
        return None

    # 1. Pop extension
    ext = parts[-1].lower()
    if ext not in SUBTITLE_EXTS:
        return None
    parts = parts[:-1]

    # 2. Peel modifiers right-to-left (stack like ``.hi.bak``)
    modifiers: list[str] = []
    while parts and parts[-1].lower() in MODIFIERS:
        modifiers.append(parts.pop().lower())

    # 3. The next-rightmost token must be a language code
    if not parts:
        return None
    lang_candidate = parts[-1].lower()
    if not _LANG_RE.match(lang_candidate):
        return None

    parts.pop()
    base = ".".join(parts) if parts else ""
    if not base:
        # Reject ``.de.srt`` (no base) — almost certainly not a real
        # sidecar, more likely a malformed filename.
        return None

    return ParsedFilename(
        base=base,
        language=lang_candidate,
        modifiers=tuple(modifiers),
        extension=ext,
    )


def is_subtitle_sidecar(path: str) -> bool:
    """Return True when ``path`` looks like a real subtitle sidecar.

    Convenience wrapper for callers that don't need the parsed parts.
    """
    return parse_subtitle_filename(path) is not None


def is_backup_subtitle(path: str) -> bool:
    """Return True when ``path`` is a ``.bak`` backup of another sidecar.

    Used by the scanner and list endpoints to decide whether the file
    should be hidden from the active-subtitle UI.
    """
    parsed = parse_subtitle_filename(path)
    return parsed is not None and parsed.is_backup
