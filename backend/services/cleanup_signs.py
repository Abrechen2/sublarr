"""Executor for the signs_cleanup rule — removes signs/forced/songs subs.

The level comes from the global ``cleanup_signs_removal_level`` setting (one
source of truth); the rule's config dict carries operational options.  Trash
by default; a sidecar is never removed if it would leave the episode+lang
with no subtitle at all (last-sub guard).  Embedded stripping is added in
Task 6; the counters ``stripped_files`` / ``stripped_tracks`` stay 0 here.

Guard keying note
-----------------
The guard groups files by ``(video_base, canonical_lang)`` — *ignoring* the
modifier — so ``Show.en.signs.ass`` and ``Show.en.ass`` share the same bucket
and the guard correctly counts them as two subs for (Show, en), permitting the
signs sidecar to be removed.  Keying on the full ``(video_base, lang,
modifier)`` triplet would give each a different bucket, making the signs
sidecar look like the only sub and blocking removal incorrectly.

For paths that ``_classify_sidecar`` cannot decompose (untagged filenames,
unrecognised language, etc.) the guard key falls back to the path itself so
these files are treated as singletons.  They can never be removed anyway —
``classify_sidecar`` will not return a removable subtype for an unstructured
filename — but the fallback prevents them from accidentally inflating a
real episode+lang bucket.
"""

from __future__ import annotations

import logging
import os

from services.cleanup_executors import (
    _classify_sidecar,
    _delete_or_trash,
    _media_path_reachable,
    _subtitle_files,
)
from services.subtitle_signs import SignsRemovalLevel, classify_sidecar, is_removable

logger = logging.getLogger(__name__)


def _guard_key(path: str) -> tuple:
    """Return the last-sub guard key for *path*.

    Key is ``(video_base, canonical_lang)`` when the path is a classifiable
    structured sidecar, or ``(path,)`` (singleton) otherwise.
    """
    classification = _classify_sidecar(path)
    if classification is None:
        return (path,)
    video_base, canonical_lang, _modifier = classification
    return (video_base, canonical_lang)


def execute_signs_cleanup(media_path: str, config: dict, dry_run: bool = False) -> dict:
    """Remove signs/forced/songs subtitle sidecars from *media_path*.

    Args:
        media_path: Root directory to scan recursively.
        config: Operational options dict — keys recognised:
            * ``permanent_delete`` (bool, default False) — hard-delete instead
              of moving to the trash dir.
            * ``strip_embedded`` (bool, default False) — reserved for Task 6;
              ignored here.
        dry_run: When True nothing is deleted; returns counts + examples only.

    Returns:
        Execute mode: ``{"trashed_sidecars": int, "stripped_files": int,
        "stripped_tracks": int, "bytes_freed": int}``.
        Dry-run mode: ``{"would_remove_sidecars": int, "would_strip_files": int,
        "would_strip_tracks": int, "examples": list}``.
        Either mode adds ``"aborted": str`` when a pre-flight guard fires.
    """
    from config import get_settings

    settings = get_settings()
    level = SignsRemovalLevel.from_str(getattr(settings, "cleanup_signs_removal_level", "off"))

    base_result: dict = {
        "trashed_sidecars": 0,
        "stripped_files": 0,
        "stripped_tracks": 0,
        "bytes_freed": 0,
    }

    if level is SignsRemovalLevel.OFF:
        return base_result

    if not _media_path_reachable(media_path):
        return {**base_result, "aborted": "media_path unreachable"}

    permanent = bool(config.get("permanent_delete", False))
    use_density = level is SignsRemovalLevel.SIGNS_FORCED_SONGS

    sidecars = _subtitle_files(media_path)

    # Build per-key sidecar counts for the last-sub guard.
    # Key = (video_base, canonical_lang) so a .signs. file and its full-
    # dialogue peer share a bucket (modifier intentionally excluded).
    per_key: dict[tuple, int] = {}
    for p in sidecars:
        key = _guard_key(p)
        per_key[key] = per_key.get(key, 0) + 1

    trashed = 0
    bytes_freed = 0
    would_remove = 0
    examples: list[dict] = []

    for path in sidecars:
        subtype = classify_sidecar(path, use_density=use_density)
        if not is_removable(subtype, level):
            continue

        key = _guard_key(path)
        if per_key.get(key, 0) <= 1:
            # Only sub for this episode+lang — keep it.
            logger.info("signs_cleanup: last-sub guard kept %s", path)
            continue

        try:
            size = os.path.getsize(path)
        except OSError:
            continue

        if dry_run:
            would_remove += 1
            # Mirror the execute branch so the preview faithfully simulates a
            # real run: decrement the bucket so the last-sub guard's ``<= 1``
            # check fires for the next removable file in the same group.
            per_key[key] -= 1
            if len(examples) < 20:
                examples.append({"path": path, "size_bytes": size, "reason": subtype})
        else:
            if _delete_or_trash(path, permanent=permanent):
                trashed += 1
                bytes_freed += size
                per_key[key] -= 1
                logger.info("signs_cleanup: removed %s (%s)", path, subtype)

    if dry_run:
        return {
            "would_remove_sidecars": would_remove,
            "would_strip_files": 0,
            "would_strip_tracks": 0,
            "examples": examples,
        }
    return {**base_result, "trashed_sidecars": trashed, "bytes_freed": bytes_freed}
