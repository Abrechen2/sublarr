"""Cleanup rule executors — one function per rule_type.

Each executor takes (media_path, config, dry_run) and returns a result dict.
NFO files (.nfo) are never deleted by any executor.

Rule types:
  language_filter  — trash sidecars in non-allowed languages
  format_upgrade   — trash SRT when ASS exists for same episode+language
  orphan_files     — trash subtitle sidecars with no matching video on disk
  orphan_db        — remove DB entries whose file no longer exists

Audit 2026-05-09 (extract+cleanup audit):
  * C0-1 — every destructive path now goes through ``_trash_path`` so
    deletions are recoverable via the same trash dir as the rest of the
    system. Per-rule ``permanent_delete=true`` is honoured for the rare
    case where a user explicitly wants ``os.remove`` semantics.
  * C0-2 — ``execute_language_filter`` refuses an empty
    ``keep_languages`` set (would otherwise nuke every recognised
    sidecar).
  * C0-3 — every executor probes ``media_path`` with ``os.stat`` first
    and aborts on OSError to prevent NFS-blip mass deletes.
  * C1-1 / C1-2 — language detection delegates to
    ``remux._parse_sidecar_language`` (modifier-aware, base-anchored)
    instead of the previous naive rsplit.
  * C1-3 — orphan detection delegates to
    ``dedup_engine.scan_orphaned_subtitles`` so the rule path matches
    the manual UI scan exactly.
  * C2-1 — directory walks track visited inodes and refuse to descend
    into already-seen subtrees (symlink-cycle defence, mirrors the
    standalone S0-3 fix).
  * C2-2 — ``execute_orphan_db`` does a single batched delete instead
    of one round-trip per missing path.
"""

import logging
import os

from config_language_data import _get_language_tags

logger = logging.getLogger(__name__)

# Module-level import seam so tests can monkeypatch SubtitleRepository.
# Wrapped in try/except to allow importing this module outside a Flask app context.
try:
    from db.repositories.subtitles import SubtitleRepository  # noqa: F401
except ImportError:  # pragma: no cover
    SubtitleRepository = None  # type: ignore[assignment,misc]

SUBTITLE_EXTENSIONS = {".ass", ".ssa", ".srt", ".vtt", ".sub"}
VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov", ".m4v", ".ts", ".wmv"}

# Trash/backup subtree name (matches the default ``remux_trash_dir``). Cleanup
# walks must never descend into it: it holds already-removed sidecars and
# video ``.bak`` backups, so re-walking it makes language_filter try to
# re-trash trashed files and makes orphan scans count every trashed sidecar
# as an orphan (prod: 5922 Permission-denied WARNINGs, 27k phantom orphans).
_TRASH_DIR_NAME = ".sublarr"


# ---------------------------------------------------------------------------
# Pre-flight guards (audit C0-3)
# ---------------------------------------------------------------------------


def _media_path_reachable(media_path: str) -> bool:
    """Return True if ``media_path`` responds to ``os.stat``.

    Cleanup walks deduce "missing" from the absence of files, so a brief
    NFS hiccup or share reload makes every path look gone and would
    trigger a mass delete. Probing the root once up front converts that
    failure mode into a logged abort.
    """
    if not media_path:
        return False
    try:
        os.stat(media_path)
        return True
    except OSError as exc:
        logger.warning(
            "Cleanup probe: media_path %s unreachable (%s); aborting to prevent mass-delete",
            media_path,
            exc,
        )
        return False


def _foreign_track_settings():
    """Return the settings object, or None when it cannot be loaded.

    Cleanup must degrade to "rule config only" rather than crash when settings
    are unavailable (e.g. a run outside an app context).
    """
    try:
        from config import get_settings

        return get_settings()
    except Exception:  # noqa: BLE001 — inheritance is best-effort, never fatal
        logger.debug("execute_foreign_tracks: settings unavailable", exc_info=True)
        return None


def _safe_walk(root: str):
    """Yield ``(dirpath, filenames)`` from ``root`` without descending into
    symlink cycles.

    Mirrors the standalone S0-3 inode-tracker so cleanup paths inherit
    the same defence: ``followlinks=True`` is preserved (homelab media
    libraries lean on it heavily) but an already-visited
    ``(st_dev, st_ino)`` short-circuits descent.
    """
    seen: set[tuple[int, int]] = set()
    for dirpath, dirs, files in os.walk(root, followlinks=True):
        try:
            st = os.stat(dirpath)
        except OSError:
            dirs[:] = []
            continue
        key = (st.st_dev, st.st_ino)
        if key in seen:
            logger.warning("Symlink cycle detected at %s during cleanup walk; pruning", dirpath)
            dirs[:] = []
            continue
        seen.add(key)
        pruned = []
        for d in dirs:
            if d == _TRASH_DIR_NAME:
                continue  # never descend into the trash/backup subtree
            try:
                child = os.stat(os.path.join(dirpath, d))
            except OSError:
                continue
            if (child.st_dev, child.st_ino) in seen:
                continue
            pruned.append(d)
        dirs[:] = pruned
        yield dirpath, files


def _subtitle_files(root: str) -> list[str]:
    """Walk root recursively, return paths of all subtitle files (never NFO)."""
    found = []
    for dirpath, filenames in _safe_walk(root):
        for fname in filenames:
            ext = os.path.splitext(fname)[1].lower()
            if ext in SUBTITLE_EXTENSIONS:
                found.append(os.path.join(dirpath, fname))
    return found


def _video_files(root: str) -> list[str]:
    """Walk root recursively, return paths of all video files.

    The ``.sublarr`` trash/backup tree is pruned centrally by
    :func:`_safe_walk`, so our own ``.bak`` backups are never probed or
    rewritten.
    """
    found = []
    for dirpath, filenames in _safe_walk(root):
        for fname in filenames:
            if os.path.splitext(fname)[1].lower() in VIDEO_EXTENSIONS:
                found.append(os.path.join(dirpath, fname))
    return found


# ---------------------------------------------------------------------------
# Language helpers (audit C1-1 / C1-2)
# ---------------------------------------------------------------------------


def _detect_sidecar_language(path: str) -> str | None:
    """Return the language tag of a sidecar, or None if not classifiable.

    Audit C1-1: ``Movie.S01E01.ass`` (no language tag) used to be parsed
    as ``lang="s01e01"`` and treated as a foreign language by
    ``execute_language_filter`` — silently deleting legitimate sidecars.
    The detector now both (a) delegates the structural parse to
    ``remux._parse_sidecar_language`` (modifier-aware, base-anchored)
    AND (b) validates the result against ``config_language_data``'s
    recognised tag set. Anything that doesn't resolve to a real
    language code returns None and is treated as "do not classify".
    """
    from config_language_data import _REVERSE_LANGUAGE_TAGS
    from remux import _parse_sidecar_language

    base = os.path.splitext(path)[0]
    parts = os.path.basename(base).rsplit(".", 1)
    if len(parts) < 2:
        return None
    video_base = base.rsplit(".", 1)[0]
    raw = _parse_sidecar_language(path, video_base)
    if not raw:
        return None
    # ``_REVERSE_LANGUAGE_TAGS`` keys are every known tag (canonical
    # ISO-639-1, ISO-639-2, full names, common variants). Anything not
    # in that set is NOT a language — return None so callers treat it
    # as "do not classify" instead of mis-deleting.
    if raw.lower() not in _REVERSE_LANGUAGE_TAGS:
        return None
    return raw.lower()


def _classify_sidecar(path: str) -> tuple[str, str, str] | None:
    """Decompose a sidecar path into (video_base, canonical_lang, modifier).

    Used by ``execute_format_upgrade`` to pair sidecars across format
    boundaries. Two files belong to the same logical track only if all
    three components match.

    Returns:
      ``(video_base, canonical_lang, modifier)`` where:
        * ``video_base`` is the absolute path stem without the lang /
          modifier / format suffix (e.g. ``/dir/Show.S01E06``).
        * ``canonical_lang`` is the ISO-639-1 code from
          :func:`config_language_data.normalize_language_code`, so
          ``de`` / ``ger`` / ``deu`` / ``german`` all collapse to ``de``.
        * ``modifier`` is one of :data:`remux._SIDECAR_MODIFIERS`
          (``forced``, ``sdh``, ``hi``, ``cc``, ``sign``, ``signs``)
          or ``""`` for the unmodified main track.

    Returns ``None`` for paths that aren't classifiable as a structured
    ``<video_base>.<lang>[.<modifier>].<ext>`` sidecar (untagged files,
    extensions outside :data:`remux._SIDECAR_EXTS`, lang tokens not in
    :data:`_REVERSE_LANGUAGE_TAGS`). Unclassifiable files are never
    paired by the format-upgrade rule.

    Modifier-awareness (Gemini-2026-05-09 review): grouping ONLY by
    ``(video_base, canonical_lang)`` would let ``de.forced.srt`` land
    in the same bucket as ``de.ass`` and get trashed as inferior — but
    a ``forced`` sub is a separate track from the main, not a
    lower-quality version of it.
    """
    from config_language_data import _REVERSE_LANGUAGE_TAGS, normalize_language_code
    from remux import _SIDECAR_EXTS, _SIDECAR_MODIFIERS

    base_no_ext, ext = os.path.splitext(path)
    if ext.lower() not in _SIDECAR_EXTS:
        return None

    parts = os.path.basename(base_no_ext).split(".")
    if len(parts) < 2:
        return None  # untagged sidecar — leave alone

    # Reverse-walk: tail token may be a modifier or a lang.
    tail = parts[-1].lower()
    if tail in _SIDECAR_MODIFIERS:
        if len(parts) < 3:
            return None  # ``show.forced.srt`` — modifier without lang
        modifier = tail
        lang_token = parts[-2].lower()
        video_base_parts = parts[:-2]
    else:
        modifier = ""
        lang_token = tail
        video_base_parts = parts[:-1]

    if lang_token not in _REVERSE_LANGUAGE_TAGS:
        return None  # last token isn't a recognised language

    canonical_lang = normalize_language_code(lang_token)
    dirpath = os.path.dirname(path)
    video_base = os.path.join(dirpath, ".".join(video_base_parts))
    return (video_base, canonical_lang, modifier)


# ---------------------------------------------------------------------------
# Trash plumbing (audit C0-1)
# ---------------------------------------------------------------------------


def _trash_path(path: str) -> bool:
    """Move ``path`` into the configured trash dir for its media root.

    Returns True on success, False on any failure (which is also logged
    at WARNING level — the caller decides whether to still count this as
    "deleted"). Mirrors the recovery semantics used by
    ``embedded_extractor.trash_unwanted_sidecars`` and
    ``cleanup_non_target_subs``.
    """
    import datetime
    import shutil
    import time as _time

    try:
        from config import get_settings
        from remux import _resolve_trash_dir

        settings = get_settings()
        trash_setting = getattr(settings, "remux_trash_dir", ".sublarr") or ".sublarr"
        resolved = _resolve_trash_dir(path, trash_setting)
        date_str = datetime.date.today().isoformat()
        dest_dir = os.path.join(resolved, "trash", date_str)
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, os.path.basename(path))
        if os.path.exists(dest):
            stem, ext = os.path.splitext(dest)
            dest = f"{stem}.{int(_time.time())}{ext}"
        shutil.move(path, dest)
        return True
    except OSError as exc:
        logger.warning("Cleanup: could not trash %s: %s", path, exc)
        return False


def _delete_or_trash(path: str, *, permanent: bool) -> bool:
    """Trash by default; honour ``permanent_delete=true`` opt-in for
    rule callers that explicitly want hard deletion."""
    if permanent:
        try:
            os.remove(path)
            return True
        except OSError as exc:
            logger.warning("Cleanup: hard-delete failed for %s: %s", path, exc)
            return False
    return _trash_path(path)


# ---------------------------------------------------------------------------
# Executors
# ---------------------------------------------------------------------------


def execute_language_filter(media_path: str, config: dict, dry_run: bool = False) -> dict:
    """Move subtitle sidecars in non-allowed languages to the trash.

    Args:
        media_path: Root directory to scan recursively.
        config: {"keep_languages": ["de", "en"], "permanent_delete": false}
        dry_run: If True, return counts without touching the filesystem.

    Returns:
        {"deleted": int, "kept": int, "bytes_freed": int} or
        {"would_delete": int, "would_keep": int, "examples": [...]} in
        dry_run mode. Adds ``"aborted": "..."`` when guards fired.
    """
    if not _media_path_reachable(media_path):
        return {
            "deleted": 0,
            "kept": 0,
            "bytes_freed": 0,
            "aborted": "media_path unreachable",
        }

    keep_languages: set[str] = set()
    for lang in config.get("keep_languages", []) or []:
        keep_languages.update(_get_language_tags(lang.lower()))
    if not keep_languages:
        # Audit C0-2: empty keep set would otherwise delete every
        # recognised sidecar in the library.
        logger.warning(
            "execute_language_filter: empty keep_languages — aborting to prevent "
            "library-wide deletion"
        )
        return {
            "deleted": 0,
            "kept": 0,
            "bytes_freed": 0,
            "aborted": "empty keep_languages",
        }

    permanent = bool(config.get("permanent_delete", False))
    deleted = 0
    kept = 0
    bytes_freed = 0
    would_delete = 0
    would_keep = 0
    examples: list[dict] = []

    for path in _subtitle_files(media_path):
        lang = _detect_sidecar_language(path)
        if lang is None:
            # Audit C1-1: untagged sidecars are NOT classifiable; we
            # never delete them — the user might rely on a custom
            # naming scheme we don't recognise.
            kept += 1
            would_keep += 1
            continue
        if lang.lower() in keep_languages:
            kept += 1
            would_keep += 1
            continue

        try:
            file_size = os.path.getsize(path)
        except OSError:
            continue
        if dry_run:
            would_delete += 1
            if len(examples) < 20:
                examples.append({"path": path, "size_bytes": file_size, "reason": f"lang:{lang}"})
            logger.debug("Would delete (language_filter): %s", path)
        else:
            if _delete_or_trash(path, permanent=permanent):
                deleted += 1
                bytes_freed += file_size
                logger.info(
                    "%s (language_filter): %s",
                    "Deleted" if permanent else "Trashed",
                    path,
                )

    if dry_run:
        return {"would_delete": would_delete, "would_keep": would_keep, "examples": examples}
    return {"deleted": deleted, "kept": kept, "bytes_freed": bytes_freed}


def execute_foreign_tracks(media_path: str, config: dict, dry_run: bool = False) -> dict:
    """Strip embedded subtitle tracks whose language is not in keep_languages.

    Closes the gap where provider-downloaded episodes never had their
    embedded foreign subtitle tracks removed (foreign-track cleanup only
    fired on the *extract* path). Reuses
    ``remux.remove_foreign_subtitle_streams`` so every rewritten video
    leaves its original behind as a ``.bak`` in the media root's trash
    dir — fully restorable, nothing hard-deleted.

    Args:
        media_path: Root directory to scan recursively.
        config: ``{"keep_languages": ["de", "en"], "keep_und": true}``.
            ``keep_languages`` is expanded to every known tag (so ``de``
            also matches ``ger``/``deu`` as reported by ffprobe).
        dry_run: If True, only probe and report; never rewrite a file.

    Returns:
        dry_run mode:
            ``{"would_strip_files": int, "would_strip_tracks": int, "examples": [...]}``
        execute mode:
            ``{"stripped_files": int, "tracks_removed": int, "bytes_freed": int}``
        Adds ``"aborted": "..."`` when a guard fires.
    """
    if not _media_path_reachable(media_path):
        return {
            "stripped_files": 0,
            "tracks_removed": 0,
            "bytes_freed": 0,
            "aborted": "media_path unreachable",
        }

    # An ABSENT key inherits the global cleanup_foreign_tracks_* setting; rules
    # are created with config_json="{}", so without this the seeded sweep would
    # abort on every run. An EXPLICITLY empty keep_languages still aborts below
    # — inheriting there would strip every subtitle track in the library.
    settings = _foreign_track_settings()
    raw_keep = config.get("keep_languages")
    if raw_keep is None:
        raw_keep = getattr(settings, "cleanup_foreign_tracks_keep_languages", None) or []
    raw_keep_und = config.get("keep_und")
    if raw_keep_und is None:
        raw_keep_und = getattr(settings, "cleanup_foreign_tracks_keep_und", False)

    keep_languages: set[str] = set()
    for lang in raw_keep:
        keep_languages.update(_get_language_tags(lang.lower()))
    if not keep_languages:
        # Mirror the language_filter C0-2 guard: an empty keep set would
        # strip every subtitle track in the library.
        logger.warning(
            "execute_foreign_tracks: empty keep_languages — aborting to prevent "
            "stripping every embedded subtitle track"
        )
        return {
            "stripped_files": 0,
            "tracks_removed": 0,
            "bytes_freed": 0,
            "aborted": "empty keep_languages",
        }

    keep_und = bool(raw_keep_und)

    from remux import RemuxError, get_media_streams, remove_foreign_subtitle_streams

    stripped_files = 0
    tracks_removed = 0
    bytes_freed = 0
    would_strip_files = 0
    would_strip_tracks = 0
    examples: list[dict] = []

    for video in _video_files(media_path):
        try:
            probe = get_media_streams(video)
        except Exception as exc:  # noqa: BLE001 — one bad probe must not abort the batch
            logger.debug("execute_foreign_tracks: probe failed for %s: %s", video, exc)
            continue

        foreign_langs: list[str] = []
        for stream in probe.get("streams", []):
            if stream.get("codec_type") != "subtitle":
                continue
            lang = (stream.get("tags", {}).get("language", "und") or "und").lower()
            if lang in keep_languages:
                continue
            if keep_und and lang == "und":
                continue
            foreign_langs.append(lang)

        if not foreign_langs:
            continue

        if dry_run:
            would_strip_files += 1
            would_strip_tracks += len(foreign_langs)
            if len(examples) < 20:
                examples.append(
                    {
                        "path": video,
                        "tracks": len(foreign_langs),
                        "langs": sorted(set(foreign_langs)),
                    }
                )
            logger.debug("Would strip (foreign_tracks): %s (%s)", video, foreign_langs)
            continue

        try:
            size_before = os.path.getsize(video)
        except OSError:
            size_before = 0
        try:
            backup = remove_foreign_subtitle_streams(
                video_path=video,
                target_languages=keep_languages,
                keep_und=keep_und,
            )
        except (RemuxError, OSError) as exc:
            logger.warning("execute_foreign_tracks: strip failed for %s: %s", video, exc)
            continue
        except Exception as exc:  # noqa: BLE001 — record + continue, never abort the batch
            logger.error(
                "execute_foreign_tracks: unexpected %s on %s: %s",
                type(exc).__name__,
                video,
                exc,
            )
            continue

        if backup:
            stripped_files += 1
            tracks_removed += len(foreign_langs)
            try:
                bytes_freed += max(0, size_before - os.path.getsize(video))
            except OSError:
                pass
            logger.info(
                "Stripped %d foreign track(s) from %s (backup at %s)",
                len(foreign_langs),
                video,
                backup,
            )
            # The container changed on disk — refresh the configured media
            # servers so their cached track list reflects the strip.
            try:
                from services.media_server_notify import notify_media_servers

                notify_media_servers(video)
            except Exception:  # noqa: BLE001 — best-effort, never abort the batch
                logger.debug("foreign_tracks: media-server refresh skipped", exc_info=True)

    if dry_run:
        return {
            "would_strip_files": would_strip_files,
            "would_strip_tracks": would_strip_tracks,
            "examples": examples,
        }
    return {
        "stripped_files": stripped_files,
        "tracks_removed": tracks_removed,
        "bytes_freed": bytes_freed,
    }


def execute_format_upgrade(media_path: str, config: dict, dry_run: bool = False) -> dict:
    """Trash lower-quality format when higher-quality exists for same logical track.

    A "logical track" is keyed by ``(video_base, canonical_lang, modifier)``.
    Sidecars in the same dir for the same media file with the same
    canonical language (``de`` collapses ``de`` / ``ger`` / ``deu`` /
    ``german``) and the same modifier (``forced`` / ``sdh`` / ``hi`` /
    ``cc`` / ``sign``/``signs`` or no modifier) are considered the
    same track in different formats. Modifier-awareness prevents
    ``Show.de.forced.srt`` from being trashed when ``Show.de.ass``
    exists — they're different tracks, not different qualities.

    Multiple inferior files for the same logical track are ALL trashed
    when at least one preferred-format peer exists. Single sidecars
    (no peer in the preferred format) are kept regardless of format.

    Args:
        media_path: Root directory to scan recursively.
        config: {"keep_format": "ass", "permanent_delete": false} —
                "ass" trashes SRT when ASS exists; "srt" vice versa;
                "any" is a no-op.
        dry_run: If True, return counts without touching the filesystem.

    Returns:
        {"deleted": int, "bytes_freed": int} or {"would_delete": int} in dry_run mode.
    """
    if not _media_path_reachable(media_path):
        return {"deleted": 0, "bytes_freed": 0, "aborted": "media_path unreachable"}

    keep_format = (config.get("keep_format") or "any").lower()
    if keep_format == "any":
        return {"deleted": 0, "bytes_freed": 0}

    permanent = bool(config.get("permanent_delete", False))

    if keep_format == "ass":
        preferred_ext, inferior_ext = ".ass", ".srt"
    else:
        preferred_ext, inferior_ext = ".srt", ".ass"

    from collections import defaultdict

    # index: (video_base, canonical_lang, modifier) -> {ext: [paths]}
    # Multiple files with the same key + same ext are stored together
    # so we don't lose any candidate for the trash sweep.
    index: dict[tuple[str, str, str], dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))

    for path in _subtitle_files(media_path):
        classification = _classify_sidecar(path)
        if classification is None:
            # Untagged or unrecognised — never paired (audit C1-1 policy).
            continue
        ext = os.path.splitext(path)[1].lower()
        index[classification][ext].append(path)

    deleted = 0
    bytes_freed = 0
    would_delete = 0
    examples: list[dict] = []

    for key, ext_map in index.items():
        preferred_paths = ext_map.get(preferred_ext) or []
        inferior_paths = ext_map.get(inferior_ext) or []
        if not preferred_paths or not inferior_paths:
            continue
        # Trash every inferior peer of this logical track. ``preferred_paths[0]``
        # is the witness we surface in the dry-run example for context.
        kept_witness = preferred_paths[0]
        for inferior_path in inferior_paths:
            try:
                file_size = os.path.getsize(inferior_path)
            except OSError:
                continue
            if dry_run:
                would_delete += 1
                if len(examples) < 20:
                    examples.append(
                        {
                            "path": inferior_path,
                            "size_bytes": file_size,
                            "reason": f"replaced by {os.path.basename(kept_witness)}",
                        }
                    )
                logger.debug("Would delete (format_upgrade): %s", inferior_path)
            else:
                if _delete_or_trash(inferior_path, permanent=permanent):
                    deleted += 1
                    bytes_freed += file_size
                    logger.info(
                        "%s (format_upgrade): %s",
                        "Deleted" if permanent else "Trashed",
                        inferior_path,
                    )

    if dry_run:
        return {"would_delete": would_delete, "examples": examples}
    return {"deleted": deleted, "bytes_freed": bytes_freed}


def execute_orphan_files(media_path: str, config: dict, dry_run: bool = False) -> dict:
    """Trash subtitle sidecars with no matching video file (basename match).

    Audit C1-3: previously this used a "directory has no video" heuristic
    that missed the typical orphan case (sidecar whose specific video
    was deleted while siblings remain). The implementation now delegates
    to ``dedup_engine.scan_orphaned_subtitles`` which matches by
    basename — the same definition the manual UI scan uses, so the rule
    path and the UI path always agree on what counts as an orphan.

    Args:
        media_path: Root directory to scan recursively.
        config: {"permanent_delete": false}
        dry_run: If True, return counts without touching the filesystem.

    Returns:
        {"deleted": int, "bytes_freed": int} or {"would_delete": int} in dry_run mode.
    """
    if not _media_path_reachable(media_path):
        return {"deleted": 0, "bytes_freed": 0, "aborted": "media_path unreachable"}

    from dedup_engine import scan_orphaned_subtitles

    permanent = bool(config.get("permanent_delete", False))
    orphans = scan_orphaned_subtitles(media_path) or []

    deleted = 0
    bytes_freed = 0
    would_delete = 0
    examples: list[dict] = []

    for entry in orphans:
        path = entry.get("path") if isinstance(entry, dict) else entry
        if not path:
            continue
        try:
            file_size = entry.get("size") if isinstance(entry, dict) else os.path.getsize(path)
        except OSError:
            continue
        if dry_run:
            would_delete += 1
            if len(examples) < 20:
                examples.append(
                    {"path": path, "size_bytes": file_size or 0, "reason": "no matching video"}
                )
            logger.debug("Would delete (orphan_files): %s", path)
        else:
            if _delete_or_trash(path, permanent=permanent):
                deleted += 1
                bytes_freed += file_size or 0
                logger.info(
                    "%s (orphan_files): %s",
                    "Deleted" if permanent else "Trashed",
                    path,
                )

    if dry_run:
        return {"would_delete": would_delete, "examples": examples}
    return {"deleted": deleted, "bytes_freed": bytes_freed}


def execute_orphan_db(config: dict, dry_run: bool = False) -> dict:
    """Remove DB subtitle entries whose file no longer exists on disk.

    Audit C0-3 + C2-2:
      * Probes the configured ``media_path`` first; aborts on OSError
        so a brief mount blip never wipes the DB.
      * Performs a single batched ``delete_by_paths`` call instead of
        the previous N+1 per-row loop.

    Args:
        config: {} (no configuration needed)
        dry_run: If True, return counts without deleting.

    Returns:
        {"deleted": int} or {"would_delete": int, "examples": [...]}.
    """
    import services.cleanup_executors as _self

    try:
        from config import get_settings

        media_path = getattr(get_settings(), "media_path", "")
    except Exception:
        media_path = ""
    if media_path and not _media_path_reachable(media_path):
        return {"deleted": 0, "aborted": "media_path unreachable"}

    repo = _self.SubtitleRepository()
    paths = repo.get_all_subtitle_paths() or []
    missing: list[str] = []
    examples: list[dict] = []

    for path in paths:
        try:
            exists = os.path.exists(path)
        except OSError:
            continue
        if not exists:
            missing.append(path)
            if len(examples) < 20:
                examples.append({"path": path, "size_bytes": 0, "reason": "file missing on disk"})

    if dry_run:
        return {"would_delete": len(missing), "examples": examples}

    deleted = 0
    if missing:
        try:
            # Prefer batch helper when the repo exposes one.
            if hasattr(repo, "delete_by_paths"):
                deleted = int(repo.delete_by_paths(missing) or 0)
            else:
                for p in missing:
                    repo.delete_by_path(p)
                    deleted += 1
        except Exception as exc:
            logger.error("execute_orphan_db: batch delete failed: %s", exc)
            return {"deleted": 0, "error": str(exc)}
    if deleted:
        logger.info("Removed %d DB orphan subtitle entries", deleted)
    return {"deleted": deleted}
