"""Wanted -> "Cleanup sidecars": trash subtitle files in languages nobody wants.

The route used to decide per wanted item. A file with two items (de and en)
was cleaned twice, each pass keeping only its own language — the de item
deleted the English sidecar, the en item the German one — and both went
through ``os.remove``. VM test of 1.14.4-rc.2: the UI's plain request left only
the video.

The decision is now made once per video file, against every language wanted
for it: the targets of all its wanted rows (whatever their status or the
selection) plus its language profile. Anything else goes to the trash, never
hard-deleted. A token that is not a recognised language code is kept.
"""

from __future__ import annotations

import glob
import logging
import os

from services.cleanup_executors import _trash_path

logger = logging.getLogger(__name__)

_SIDECAR_FORMATS = ("ass", "srt")


def _wanted_languages(file_path: str, items_for_file: list[dict], settings) -> set[str]:
    """Canonical codes of every language wanted for ``file_path``."""
    from config_language_data import normalize_language_code
    from db.wanted import get_wanted_items_by_path
    from services.embedded_extractor import compute_keep_langs, resolve_profile_for_item

    rows = get_wanted_items_by_path(file_path) or items_for_file
    keep = {
        normalize_language_code(row.get("target_language", ""))
        for row in [*rows, *items_for_file]
        if row.get("target_language")
    }
    keep |= compute_keep_langs(resolve_profile_for_item(items_for_file[0], settings), settings)
    keep.discard("")
    return keep


def _sidecar_language(sidecar: str, base: str, fmt: str) -> str | None:
    """Canonical language of a sidecar's first name token, or None if it is not one."""
    from config_language_data import _REVERSE_LANGUAGE_TAGS

    token = sidecar[len(base) + 1 : -len(fmt) - 1].split(".")[0].lower()
    return _REVERSE_LANGUAGE_TAGS.get(token)


def cleanup_wanted_sidecars(items: list[dict], *, dry_run: bool, media_path: str) -> dict:
    """Trash unwanted-language sidecars next to the files of ``items``.

    Returns ``{"deleted": [...], "kept": [...], "errors": [...], "dry_run": bool}``;
    in a dry run ``deleted`` lists what would be trashed.
    """
    from config import get_settings
    from security_utils import is_safe_path

    settings = get_settings()
    by_file: dict[str, list[dict]] = {}
    for item in items:
        file_path = item.get("file_path", "")
        if file_path and os.path.exists(file_path):
            by_file.setdefault(file_path, []).append(item)

    deleted: list[str] = []
    kept: list[str] = []
    errors: list[str] = []

    for file_path, file_items in by_file.items():
        keep = _wanted_languages(file_path, file_items, settings)
        if not keep:
            # Without a known wanted language every sidecar would qualify.
            errors.append(f"Skipped (no wanted language known): {file_path}")
            continue

        base = os.path.splitext(file_path)[0]
        for fmt in _SIDECAR_FORMATS:
            # Escaped: "[Group] Show.S01E03" is a character class to glob.
            for sidecar in sorted(glob.glob(f"{glob.escape(base)}.*.{fmt}")):
                if not is_safe_path(sidecar, media_path):
                    errors.append(f"Skipped (path traversal): {sidecar}")
                    continue
                language = _sidecar_language(sidecar, base, fmt)
                if language is None or language in keep:
                    kept.append(sidecar)
                    continue
                if dry_run or _trash_path(sidecar):
                    deleted.append(sidecar)
                else:
                    errors.append(f"{sidecar}: could not be moved to the trash")

    logger.info(
        "Wanted sidecar cleanup (dry_run=%s): %d trashed, %d kept, %d errors",
        dry_run,
        len(deleted),
        len(kept),
        len(errors),
    )
    return {"deleted": deleted, "kept": kept, "errors": errors, "dry_run": dry_run}
