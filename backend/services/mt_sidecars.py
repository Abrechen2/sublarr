"""Move machine-translation sidecars aside while an original is installed.

Replacing a machine translation (MT) with a genuine original must never leave
the episode worse off than before. Two ways it used to:

- The MT was trashed before the install ran. An install that then failed left
  the episode with no subtitle at all.
- Only the file at the ORIGINAL's path was trashed. An ``.ass`` original next
  to an ``.srt`` MT left both in place.

The contract here: ``retire`` moves every MT sidecar for the item into the
recoverable trash and reports what it moved; the caller runs the install and,
if nothing was installed, hands the report to ``restore``.
"""

from __future__ import annotations

import logging
import os
import shutil
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

_QUALITY_SUFFIX = ".quality.json"


def mt_sidecar_paths(item: dict, fallback_path: str | None) -> list[str]:
    """Existing sidecar files that hold this item's machine translation.

    Derived from the MT rows in ``subtitle_downloads``, which name the format
    the translation was written in. ``fallback_path`` (the original's target
    path) is used only when no MT row exists — a translation whose row failed
    to record — which matches the behaviour before provenance was consulted.
    """
    from db.providers import get_machine_translation_formats
    from translator.output_paths import get_output_path_for_lang

    video_path = item.get("file_path") or ""
    language = item.get("target_language") or ""
    formats: list[str] = []
    if video_path and language:
        try:
            formats = get_machine_translation_formats(video_path, language)
        except Exception as exc:  # noqa: BLE001 — provenance lookup is best-effort
            logger.warning("mt_sidecars: MT provenance lookup failed for %s: %s", video_path, exc)

    candidates = [get_output_path_for_lang(video_path, fmt, language) for fmt in formats]
    if not formats and fallback_path:
        candidates = [fallback_path]
    return [path for path in candidates if os.path.exists(path)]


def machine_translation_paths(video_path: str) -> set[str]:
    """Normalised sidecar paths that hold a machine translation for this video.

    Used to keep a machine translation from ever being a translation SOURCE
    (owner decision 2026-09-16). A failed lookup yields an empty set and a
    warning: better one avoidable translation than no translation at all.
    """
    from db.providers import get_machine_translation_sidecars
    from translator.output_paths import get_output_path_for_lang

    if not video_path:
        return set()
    try:
        recorded = get_machine_translation_sidecars(video_path)
    except Exception as exc:  # noqa: BLE001 — provenance lookup is best-effort
        logger.warning("mt_sidecars: MT provenance lookup failed for %s: %s", video_path, exc)
        return set()
    return {
        os.path.normcase(os.path.normpath(get_output_path_for_lang(video_path, fmt, lang)))
        for lang, fmt in recorded
    }


def target_sidecars(item: dict) -> set[str]:
    """Every existing subtitle sidecar in the item's target language."""
    from subtitle_filename import SUBTITLE_EXTS
    from translator.output_paths import get_output_path_for_lang

    video_path = item.get("file_path") or ""
    language = item.get("target_language") or ""
    if not video_path or not language:
        return set()
    paths = (get_output_path_for_lang(video_path, ext, language) for ext in SUBTITLE_EXTS)
    return {path for path in paths if os.path.exists(path)}


def original_installed(
    result: dict | None, before: set[str], after: set[str], moved: list[tuple[str, str]]
) -> bool:
    """Whether the episode now has a genuine subtitle in place of the MT.

    The search's status alone is not enough. ``process_wanted_item`` swallows
    an exception raised after ``save_subtitle`` wrote the file and reports
    ``not_found``, and ``duplicate_skipped`` means an equal original was
    already there. What counts is the disk: a target-language sidecar that
    appeared while the MTs were aside, or a duplicate that is not a retired MT.
    """
    status = (result or {}).get("status")
    if status == "found" or after - before:
        return True
    if status == "duplicate_skipped":
        existing = (result or {}).get("output_path")
        retired = {original for original, _ in moved}
        return bool(existing) and os.path.exists(existing) and existing not in retired
    return False


def retire(paths: list[str]) -> list[tuple[str, str]]:
    """Move each path into one trash batch; return ``(original, trashed)`` pairs.

    A path that cannot be trashed is left where it is and logged — it is not in
    the returned pairs, so ``restore`` never touches it.
    """
    from config import get_settings
    from services.sidecar_trash import get_batch_dir, trash_sidecar

    if not paths:
        return []
    media_path = getattr(get_settings(), "media_path", "") or os.path.dirname(paths[0])
    batch_dir = get_batch_dir(media_path, f"mt-reseek-{datetime.now(UTC):%Y%m%d%H%M%S%f}")

    moved: list[tuple[str, str]] = []
    for path in paths:
        trashed_path, err = trash_sidecar(path, media_path, batch_dir)
        if err:
            logger.warning("mt_sidecars: could not trash MT sidecar %s: %s", path, err)
            continue
        logger.info("mt_sidecars: trashed MT sidecar %s -> %s", path, trashed_path)
        moved.append((path, trashed_path))
    return moved


def forget(item: dict, moved: list[tuple[str, str]]) -> None:
    """Drop the machine-translation records of sidecars an original replaced.

    Provenance is the latest record per language and format; a retired MT in
    another format than the original would otherwise keep that path marked
    as a machine translation for whatever lands there next.
    """
    from db.providers import delete_machine_translation_records

    video_path = item.get("file_path") or ""
    language = item.get("target_language") or ""
    if not video_path or not language:
        return
    for original, _trashed in moved:
        fmt = os.path.splitext(original)[1].lstrip(".").lower()
        try:
            delete_machine_translation_records(video_path, language, fmt)
        except Exception as exc:  # noqa: BLE001 — the install already succeeded
            logger.warning("mt_sidecars: could not forget MT record for %s: %s", original, exc)


def restore(moved: list[tuple[str, str]]) -> None:
    """Put retired MT sidecars back where they were.

    Never overwrites: if something now occupies the original path, the MT stays
    in the trash and the conflict is logged.
    """
    for original, trashed in moved:
        if os.path.exists(original):
            logger.warning(
                "mt_sidecars: not restoring %s — the path is occupied; MT stays at %s",
                original,
                trashed,
            )
            continue
        try:
            shutil.move(trashed, original)
            if os.path.exists(trashed + _QUALITY_SUFFIX):
                shutil.move(trashed + _QUALITY_SUFFIX, original + _QUALITY_SUFFIX)
            logger.info("mt_sidecars: restored MT sidecar %s", original)
        except OSError as exc:
            logger.error("mt_sidecars: failed to restore %s from %s: %s", original, trashed, exc)
