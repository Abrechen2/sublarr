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

Backup file location
--------------------
``.bak`` backup sidecars live in a hidden ``.sublarr/backups/`` subdir of
the active sub's directory — NOT next to the active file. The hidden
location keeps Plex/Emby/Jellyfin from picking them up: those servers
parse the segment immediately preceding ``.srt`` as a language code, and
``bak`` is a valid ISO-639-2/3 code for Bashkir. Storing backups in a
hidden subdir bypasses that misparse entirely.

Use :func:`bak_path_for` and :func:`active_path_for_bak` to translate
between the two — never construct ``f"{base}.bak{ext}"`` strings inline.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

# Hidden subdir layout for backup sidecars. Lives directly inside each
# series/movie folder so a backup stays adjacent to the file it protects
# without being visible to media servers. ``.sublarr/`` is also used by
# the remux pipeline for container backups (``.sublarr/trash/``); the
# walker in ``services.subtitle_backups`` knows to descend into
# ``.sublarr/backups/`` while still skipping the trash subdir.
BAK_HIDDEN_DIR = ".sublarr"
BAK_SUBDIR = "backups"

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


# ---------------------------------------------------------------------------
# Backup path helpers
# ---------------------------------------------------------------------------


def bak_dir_for(active_path: str) -> str:
    """Return the hidden backup directory beside ``active_path``."""
    return os.path.join(os.path.dirname(active_path), BAK_HIDDEN_DIR, BAK_SUBDIR)


def bak_path_for(active_path: str) -> str:
    """Return the canonical ``.bak`` target path for ``active_path``.

    Always points into the hidden ``.sublarr/backups/`` subdir of the
    active sidecar's directory. The basename keeps the historical
    ``<base>.<lang>(.<modifier>)*.bak.<ext>`` shape so existing parsers
    keep working — only the location changes.

    Example::

        bak_path_for("/m/Show/S01E01.en.srt")
        -> "/m/Show/.sublarr/backups/S01E01.en.bak.srt"
    """
    base, ext = os.path.splitext(os.path.basename(active_path))
    bak_name = f"{base}.bak{ext}"
    return os.path.join(bak_dir_for(active_path), bak_name)


def legacy_bak_path_for(active_path: str) -> str:
    """Return the legacy sibling-location bak path for ``active_path``.

    Pre-2026-05-02 backups were written next to the active sub at
    ``<base>.<lang>.bak.<ext>``. The migration script in
    ``backend/scripts/migrate_subtitle_baks.py`` moves these into the
    hidden subdir; readers (undo / bak-exists / restore listings) check
    both locations during the transition window.
    """
    base, ext = os.path.splitext(active_path)
    return f"{base}.bak{ext}"


def find_existing_bak(active_path: str) -> str | None:
    """Return the path of an existing bak for ``active_path``, or None.

    Checks the canonical hidden location first, then falls back to the
    legacy sibling location. Use this in restore / exists endpoints so
    pre-migration files keep working.
    """
    new_path = bak_path_for(active_path)
    if os.path.exists(new_path):
        return new_path
    legacy = legacy_bak_path_for(active_path)
    if os.path.exists(legacy):
        return legacy
    return None


def active_path_for_bak(bak_path: str) -> str | None:
    """Reverse of :func:`bak_path_for`: where would this bak restore to.

    Handles both layouts so pre-migration files keep working:
      * new — ``<dir>/.sublarr/backups/<base>.<lang>.bak.<ext>``
      * legacy — ``<dir>/<base>.<lang>.bak.<ext>`` (sibling)

    Returns ``None`` when the basename is not a valid backup sidecar.
    """
    parsed = parse_subtitle_filename(bak_path)
    if parsed is None or not parsed.is_backup:
        return None
    other_mods = [m for m in parsed.modifiers if m != "bak"]
    parts: list[str] = [parsed.base, parsed.language, *other_mods, parsed.extension]
    new_name = ".".join(parts)

    parent = os.path.dirname(bak_path)
    if (
        os.path.basename(parent) == BAK_SUBDIR
        and os.path.basename(os.path.dirname(parent)) == BAK_HIDDEN_DIR
    ):
        # New layout: strip the .sublarr/backups/ pair to land in the
        # series folder where the active sub lives.
        media_dir = os.path.dirname(os.path.dirname(parent))
    else:
        # Legacy: bak is a sibling of the active sub.
        media_dir = parent
    return os.path.join(media_dir, new_name)
