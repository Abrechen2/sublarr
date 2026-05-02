"""Subtitle-backup (`.bak.srt`/`.bak.ass`/...) management service.

These files are produced by ``subtitle_processor.apply_mods`` whenever a
user runs HI-removal, common-fixes, or credit-removal on a subtitle.
The processor copies the original to ``<dir>/.sublarr/backups/<base>.<lang>.bak.<ext>``
so the change is reversible via ``POST /api/v1/tools/process/undo`` —
see the sister module ``routes.subtitle_processor``.

This module owns the *bulk* lifecycle:

  * :func:`iter_subtitle_baks` — walk media roots and yield bak paths.
  * :func:`is_orphan` — true when neither the parent video nor the
    active sub still exist (the bak no longer protects anything).
  * :func:`list_subtitle_baks` — the listing endpoint payload.
  * :func:`cleanup_subtitle_baks` — TTL- and/or orphan-driven purge.

Backup location (since 2026-05-02)
----------------------------------
Backups live in a hidden ``.sublarr/backups/`` subdir of the active
sub's directory. Pre-2026-05-02 deployments wrote them as siblings of
the active sub; the walker below understands both layouts so existing
files keep working until ``backend/scripts/migrate_subtitle_baks.py``
moves them. The hidden location keeps Plex/Emby/Jellyfin from picking
backups up as subtitle tracks (they parse ``bak`` as Bashkir/ISO-639).

Why a separate module from the existing ``remux.backup_cleanup``?
Container backups (``<file>.mkv.<ts>.bak``) live in
``<media>/.sublarr/trash/`` and follow the ``remux_backup_retention_days``
TTL. Subtitle backups live in ``<media>/.sublarr/backups/`` and follow
``subtitle_bak_retention_days``. They share the ``.sublarr`` parent but
have different retention contracts — keeping the two concerns separate
avoids the temptation to lump them together with one TTL knob.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

from subtitle_filename import (
    BAK_HIDDEN_DIR,
    BAK_SUBDIR,
    active_path_for_bak,
    parse_subtitle_filename,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Filesystem walk
# ---------------------------------------------------------------------------


def _is_bak_filename(fname: str) -> bool:
    return fname.lower().endswith((".bak.srt", ".bak.ass", ".bak.ssa", ".bak.vtt"))


def iter_subtitle_baks(media_roots: list[str]) -> Iterator[str]:
    """Yield absolute paths of every subtitle backup under ``media_roots``.

    A path qualifies when :func:`parse_subtitle_filename` recognises it
    as a sidecar **and** ``parsed.is_backup`` is ``True``.

    Two layouts are honoured:

      * **Canonical** — ``<series>/.sublarr/backups/<base>.<lang>.bak.<ext>``.
        ``.sublarr`` is descended into for the ``backups`` subdir only;
        sibling ``.sublarr/trash/`` (container backups) is skipped.

      * **Legacy** — ``<series>/<base>.<lang>.bak.<ext>`` (pre-2026-05-02).
        Found via the normal visible-folder walk. Once the migration
        script has run, no legacy files remain on disk.

    All other hidden dirs (``.git``, ``.sublarr_trash``, ``.DS_Store``)
    are pruned to keep the walk fast and avoid yielding files the remux
    pipeline is keeping deliberately.
    """
    for root in media_roots:
        if not root or not os.path.isdir(root):
            continue
        for dirpath, dirnames, files in os.walk(root):
            base = os.path.basename(dirpath)
            if base == BAK_HIDDEN_DIR:
                # Inside .sublarr — only descend into the backups subdir.
                dirnames[:] = [d for d in dirnames if d == BAK_SUBDIR]
            elif (
                base == BAK_SUBDIR and os.path.basename(os.path.dirname(dirpath)) == BAK_HIDDEN_DIR
            ):
                # Inside .sublarr/backups — flat directory, no descent.
                dirnames[:] = []
            else:
                # Visible territory: prune all hidden dirs except .sublarr
                # so we have the chance to step into backups one level down.
                dirnames[:] = [d for d in dirnames if not d.startswith(".") or d == BAK_HIDDEN_DIR]

            for fname in files:
                if not _is_bak_filename(fname):
                    continue
                fpath = os.path.join(dirpath, fname)
                parsed = parse_subtitle_filename(fpath)
                if parsed is not None and parsed.is_backup:
                    yield fpath


# ---------------------------------------------------------------------------
# Path derivation + orphan detection
# ---------------------------------------------------------------------------


def derive_active_sub_path(bak_path: str) -> str | None:
    """Return the path the bak would restore to, or ``None`` if unparseable.

    Thin wrapper around :func:`subtitle_filename.active_path_for_bak`,
    which understands both the canonical hidden layout and the legacy
    sibling layout so pre-migration files keep working.
    """
    return active_path_for_bak(bak_path)


def derive_video_path(bak_path: str) -> str | None:
    """Return the candidate video path for the bak's series episode.

    Sublarr does not record which container the sub belongs to, so we
    test every supported container extension (.mkv, .mp4, .m4v) and
    return the first match — or ``None`` if none exist on disk. Used
    only for orphan detection; a missing video is one of two signals
    that the bak no longer serves a purpose.

    Resolves the video against the *active sub's* directory so it works
    for both layouts: a bak inside ``.sublarr/backups/`` correctly maps
    back to its series folder before the lookup.
    """
    parsed = parse_subtitle_filename(bak_path)
    if parsed is None:
        return None
    active_path = active_path_for_bak(bak_path)
    series_dir = os.path.dirname(active_path) if active_path else os.path.dirname(bak_path)
    base_path = os.path.join(series_dir, parsed.base)
    for ext in (".mkv", ".mp4", ".m4v", ".avi", ".webm", ".ts"):
        candidate = base_path + ext
        if os.path.exists(candidate):
            return candidate
    return None


def is_orphan(bak_path: str) -> bool:
    """Return True when the bak has lost both anchors.

    A bak is an orphan when *neither* the active sub it would restore
    nor the parent video still exist. In that state the bak protects
    nothing — no content can use it and the user cannot meaningfully
    interact with it via the UI. Auto-purge fires immediately on
    orphans regardless of the retention TTL.
    """
    active = derive_active_sub_path(bak_path)
    if active and os.path.exists(active):
        return False
    return not derive_video_path(bak_path)


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


def list_subtitle_baks(
    media_roots: list[str],
    retention_days: int = 0,
    series_path_filter: str | None = None,
) -> list[dict]:
    """Return metadata for every subtitle bak under ``media_roots``.

    Args:
        media_roots: Directories to scan recursively.
        retention_days: When > 0, populates ``expires_at`` per entry so
            the UI can display "deletes in N days" badges.
        series_path_filter: When given, only return baks whose path
            starts with this directory. Used by the series-scoped
            listing endpoint.
    """
    result: list[dict] = []
    for bak_path in iter_subtitle_baks(media_roots):
        if series_path_filter and not bak_path.startswith(series_path_filter):
            continue
        try:
            stat = os.stat(bak_path)
        except OSError:
            continue
        active = derive_active_sub_path(bak_path)
        video = derive_video_path(bak_path)
        parsed = parse_subtitle_filename(bak_path)

        expires_at: str | None = None
        if retention_days > 0:
            expires_dt = datetime.fromtimestamp(stat.st_mtime, tz=UTC) + timedelta(
                days=retention_days
            )
            expires_at = expires_dt.isoformat()

        entry = {
            "path": bak_path,
            "restore_path": active,  # where /tools/process/undo would put it
            "video_path": video,
            "language": parsed.language if parsed else None,
            "modifiers": list(parsed.modifiers) if parsed else [],
            "size_bytes": stat.st_size,
            "modified_at": stat.st_mtime,
            "expires_at": expires_at,
            "is_orphan": (active is None or not os.path.exists(active)) and video is None,
        }
        result.append(entry)
    return result


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------


def cleanup_subtitle_baks(
    media_roots: list[str],
    *,
    older_than_days: int = 0,
    orphans_only: bool = False,
    dry_run: bool = False,
) -> dict:
    """Bulk-delete subtitle backup files.

    Args:
        media_roots: Directories to scan.
        older_than_days: Delete baks older than this many days. ``0``
            disables the age filter (only orphan-mode then makes sense).
        orphans_only: When True, ignore ``older_than_days`` and only
            delete orphans.
        dry_run: When True, return the files that *would* be deleted
            without touching disk.

    Returns:
        Dict with keys ``deleted`` (list of paths), ``orphans_purged``
        (count of orphan deletions, subset of ``deleted``), ``skipped``
        (still within retention, not orphan), ``errors`` (list of
        ``{path, error}``), ``dry_run`` flag.
    """
    deleted: list[str] = []
    orphans_purged = 0
    skipped = 0
    errors: list[dict] = []

    if older_than_days <= 0 and not orphans_only:
        return {
            "deleted": [],
            "orphans_purged": 0,
            "skipped": 0,
            "errors": [],
            "dry_run": dry_run,
            "note": "no cleanup criteria — set older_than_days or orphans_only",
        }

    cutoff = time.time() - older_than_days * 86400 if older_than_days > 0 else 0.0

    for bak_path in iter_subtitle_baks(media_roots):
        try:
            mtime = os.path.getmtime(bak_path)
            orphan = is_orphan(bak_path)

            should_delete = False
            if orphan:
                # Orphans always go, regardless of age.
                should_delete = True
            elif orphans_only:
                # Orphans-only mode skips everything else.
                pass
            elif older_than_days > 0 and mtime < cutoff:
                should_delete = True

            if not should_delete:
                skipped += 1
                continue

            if not dry_run:
                os.unlink(bak_path)
                logger.info(
                    "Subtitle bak deleted (orphan=%s, age=%.1fd): %s",
                    orphan,
                    (time.time() - mtime) / 86400,
                    bak_path,
                )
            deleted.append(bak_path)
            if orphan:
                orphans_purged += 1
        except OSError as exc:
            errors.append({"path": bak_path, "error": str(exc)})
            logger.warning("Could not process subtitle bak %s: %s", bak_path, exc)

    return {
        "deleted": deleted,
        "orphans_purged": orphans_purged,
        "skipped": skipped,
        "errors": errors,
        "dry_run": dry_run,
    }
