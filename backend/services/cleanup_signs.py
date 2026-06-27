"""Executor for the signs_cleanup rule — removes signs/forced/songs subs.

The level comes from the global ``cleanup_signs_removal_level`` setting (one
source of truth); the rule's config dict carries operational options.  Trash
by default; a sidecar is never removed if it would leave the episode+lang
with no subtitle at all (last-sub guard).

Embedded stripping (Task 6)
---------------------------
When ``config["strip_embedded"]`` is True, ``execute_signs_cleanup`` also
probes every video file under *media_path* and remuxes out embedded subtitle
streams that classify as signs/forced/songs.  Classification is
**metadata-only** (disposition flags + title tag) — extracting and parsing
cue timings for every embedded stream library-wide would be prohibitively
expensive and is not implemented here.  Density classification therefore
remains a sidecar-only feature.

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


def _embedded_pass(
    media_path: str,
    config: dict,
    level: SignsRemovalLevel,
    dry_run: bool,
    out: dict,
) -> None:
    """Strip removable embedded subtitle streams (signs/forced/songs) from all videos.

    Embedded classification is metadata-only (disposition/title); density is not
    applied to embedded streams by design (cost).

    Last-sub guard is language-agnostic — it mirrors the sidecar sweep and the
    spec's binding rule ("never leave an (episode, language) with zero
    subtitles").  The last remaining subtitle stream of ANY language (including
    ``und``/untagged) is kept, not just keep-language tracks; a lone foreign
    signs/forced track is therefore preserved.

    ``drop_indices`` are 0-based subtitle-relative positions (the same ``sub_index``
    assigned while enumerating subtitle streams).  ``remove_subtitle_streams_by_index``
    translates them to global mkvmerge track IDs internally.
    """
    import remux
    from config_language_data import normalize_language_code
    from services.cleanup_executors import _video_files
    from services.subtitle_signs import classify_stream
    from services.subtitle_signs import is_removable as _is_removable

    for video in _video_files(media_path):
        try:
            probe = remux.get_media_streams(video)
        except Exception:
            continue

        # Build indexed list of subtitle streams (0-based subtitle-relative index).
        subs: list[tuple[int, dict]] = []
        sub_index = 0
        for st in probe.get("streams", []):
            if st.get("codec_type") != "subtitle":
                continue
            subs.append((sub_index, st))
            sub_index += 1

        if not subs:
            continue

        # Count subtitle streams per language (ALL languages, incl. und/untagged)
        # before deciding drops — the last sub of any language is protected.
        lang_count: dict[str, int] = {}
        for _idx, st in subs:
            lang = normalize_language_code((st.get("tags") or {}).get("language") or "")
            lang_count[lang] = lang_count.get(lang, 0) + 1

        drop: list[int] = []
        for idx, st in subs:
            subtype = classify_stream(st)  # metadata-only: no cues arg
            if not _is_removable(subtype, level):
                continue
            lang = normalize_language_code((st.get("tags") or {}).get("language") or "")
            if lang_count.get(lang, 0) <= 1:
                # Last sub for this language — must not be dropped (any language).
                continue
            drop.append(idx)
            lang_count[lang] -= 1

        if not drop:
            continue

        if dry_run:
            out["would_strip_files"] = out.get("would_strip_files", 0) + 1
            out["would_strip_tracks"] = out.get("would_strip_tracks", 0) + len(drop)
        else:
            try:
                backup = remux.remove_subtitle_streams_by_index(video, drop)
            except Exception:
                logger.exception("signs_cleanup: embedded strip failed for %s", video)
                continue
            if backup:
                out["stripped_files"] += 1
                out["stripped_tracks"] += len(drop)


def execute_signs_cleanup(media_path: str, config: dict, dry_run: bool = False) -> dict:
    """Remove signs/forced/songs subtitle sidecars and embedded streams from *media_path*.

    Args:
        media_path: Root directory to scan recursively.
        config: Operational options dict — keys recognised:
            * ``permanent_delete`` (bool, default False) — hard-delete instead
              of moving to the trash dir.
            * ``strip_embedded`` (bool, default False) — when True, also probe
              video files and remux out embedded streams that classify as
              signs/forced/songs.
            * ``keep_languages`` (list[str], default ["de","en"]) — ISO-639-1
              codes; the last keep-language embedded track per language is
              never dropped.
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

    # Accumulate result before (optionally) adding embedded counters.
    if dry_run:
        result: dict = {
            "would_remove_sidecars": would_remove,
            "would_strip_files": 0,
            "would_strip_tracks": 0,
            "examples": examples,
        }
    else:
        result = {**base_result, "trashed_sidecars": trashed, "bytes_freed": bytes_freed}

    if config.get("strip_embedded"):
        _embedded_pass(media_path, config, level, dry_run, result)

    return result
