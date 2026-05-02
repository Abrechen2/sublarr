"""One-shot migration: move legacy sibling-located ``.bak`` sidecars
into ``<series>/.sublarr/backups/``.

Pre-2026-05-02 deployments wrote subtitle backups as siblings of the
active sub (``<base>.<lang>.bak.<ext>``). Plex/Emby/Jellyfin parse
``bak`` as the ISO-639 code for Bashkir and surface every backup as a
phantom subtitle track in their player UI. The new layout puts backups
in a hidden ``.sublarr/backups/`` subdir which media servers ignore.

This script is **idempotent** and **safe to interrupt**: it walks the
configured media roots, derives each legacy bak's canonical destination,
and only moves files that don't already exist at the destination. A
crash mid-walk simply means the next run picks up where it left off.

Usage::

    # From the backend/ directory:
    python -m scripts.migrate_subtitle_baks --dry-run
    python -m scripts.migrate_subtitle_baks

The default media roots come from the running app's settings
(``settings.media_path`` plus comma-separated ``extra_media_paths``).
Override with ``--media-root`` (repeatable) for ad-hoc runs.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass

from subtitle_filename import (
    bak_path_for,
    parse_subtitle_filename,
)

logger = logging.getLogger("migrate_subtitle_baks")


@dataclass
class MigrationResult:
    moved: list[tuple[str, str]]
    skipped_already_migrated: int
    skipped_dest_exists: int
    skipped_unparseable: int
    errors: list[dict]

    @property
    def total_seen(self) -> int:
        return (
            len(self.moved)
            + self.skipped_already_migrated
            + self.skipped_dest_exists
            + self.skipped_unparseable
            + len(self.errors)
        )


def _iter_legacy_baks(media_root: str):
    """Yield legacy sibling-located bak paths under ``media_root``.

    Skips any file already inside a ``.sublarr/backups/`` subdir — those
    are the canonical layout and don't need to move.
    """
    for dirpath, dirnames, files in os.walk(media_root):
        # Don't descend into hidden dirs at all — canonical files we
        # leave alone, and trash dirs hold container backups we mustn't
        # touch from this script.
        if any(part.startswith(".") for part in dirpath[len(media_root) :].split(os.sep) if part):
            dirnames[:] = []
            continue
        # Prune hidden subdirs from further descent for the same reason.
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]

        for fname in files:
            lower = fname.lower()
            if not lower.endswith((".bak.srt", ".bak.ass", ".bak.ssa", ".bak.vtt")):
                continue
            fpath = os.path.join(dirpath, fname)
            parsed = parse_subtitle_filename(fpath)
            if parsed is None or not parsed.is_backup:
                continue
            yield fpath


def _derive_active_path_from_legacy(legacy_bak: str) -> str | None:
    """Return the active sub path that ``legacy_bak`` is a backup of.

    Legacy layout: ``<dir>/<base>.<lang>.bak.<ext>`` -> active is the
    same path with the ``.bak`` modifier stripped.
    """
    parsed = parse_subtitle_filename(legacy_bak)
    if parsed is None or not parsed.is_backup:
        return None
    other_mods = [m for m in parsed.modifiers if m != "bak"]
    parts = [parsed.base, parsed.language, *other_mods, parsed.extension]
    return os.path.join(os.path.dirname(legacy_bak), ".".join(parts))


def migrate(
    media_roots: list[str],
    dry_run: bool = False,
) -> MigrationResult:
    """Move legacy sibling baks into the canonical hidden subdir.

    Idempotent: a second run on the same tree finds nothing left to do.
    """
    moved: list[tuple[str, str]] = []
    skipped_already_migrated = 0
    skipped_dest_exists = 0
    skipped_unparseable = 0
    errors: list[dict] = []

    for media_root in media_roots:
        if not media_root or not os.path.isdir(media_root):
            logger.warning("media_root does not exist, skipping: %s", media_root)
            continue
        for legacy_bak in _iter_legacy_baks(media_root):
            active = _derive_active_path_from_legacy(legacy_bak)
            if active is None:
                skipped_unparseable += 1
                continue
            dest = bak_path_for(active)

            if legacy_bak == dest:
                # Already in canonical location — should not normally
                # happen since _iter_legacy_baks skips hidden dirs, but
                # treat defensively in case media_root itself is a
                # ``.sublarr/backups`` dir.
                skipped_already_migrated += 1
                continue

            if os.path.exists(dest):
                # Conflict: a canonical bak already exists. Don't
                # overwrite — that would silently destroy the user's
                # most recent backup. Leave the legacy file in place
                # and surface the conflict.
                logger.warning(
                    "Conflict: canonical bak already exists, skipping %s -> %s",
                    legacy_bak,
                    dest,
                )
                skipped_dest_exists += 1
                continue

            if dry_run:
                logger.info("[dry-run] would move %s -> %s", legacy_bak, dest)
                moved.append((legacy_bak, dest))
                continue

            try:
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                os.rename(legacy_bak, dest)
                logger.info("moved %s -> %s", legacy_bak, dest)
                moved.append((legacy_bak, dest))
            except OSError as exc:
                logger.error("failed to move %s: %s", legacy_bak, exc)
                errors.append({"path": legacy_bak, "error": str(exc)})

    return MigrationResult(
        moved=moved,
        skipped_already_migrated=skipped_already_migrated,
        skipped_dest_exists=skipped_dest_exists,
        skipped_unparseable=skipped_unparseable,
        errors=errors,
    )


def _resolve_default_media_roots() -> list[str]:
    """Return media roots from the running app's settings.

    Fails loudly if settings can't be loaded — running this script
    against the wrong root would silently corrupt nothing (we never
    overwrite), but it would be a no-op the user has to debug. Better
    to fail fast.
    """
    try:
        from config import get_settings  # type: ignore[import-not-found]
    except ImportError as exc:
        raise SystemExit(
            "Could not import settings. Run from backend/ as `python -m scripts.migrate_subtitle_baks`"
        ) from exc
    settings = get_settings()
    roots = [settings.media_path] if settings.media_path else []
    extra = getattr(settings, "extra_media_paths", "") or ""
    for item in extra.split(","):
        item = item.strip()
        if item:
            roots.append(item)
    return roots


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Move legacy sibling-located subtitle .bak files into "
            "<series>/.sublarr/backups/. Idempotent and safe to re-run."
        )
    )
    p.add_argument(
        "--media-root",
        action="append",
        default=None,
        help=(
            "Media root to scan (repeatable). When omitted the script "
            "uses settings.media_path + extra_media_paths."
        ),
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would happen without moving files.",
    )
    p.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Log every move; default reports only summary + warnings.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_argparser().parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    roots = args.media_root or _resolve_default_media_roots()
    if not roots:
        logger.error("No media roots configured. Pass --media-root or set settings.media_path.")
        return 2

    logger.info("Scanning %d media root(s): %s", len(roots), ", ".join(roots))
    if args.dry_run:
        logger.info("DRY-RUN — no files will be moved.")

    result = migrate(roots, dry_run=args.dry_run)

    print()
    print(f"Total bak files seen:        {result.total_seen}")
    print(f"Moved (or would move):       {len(result.moved)}")
    print(f"Already in canonical layout: {result.skipped_already_migrated}")
    print(f"Skipped (dest already exists): {result.skipped_dest_exists}")
    print(f"Unparseable filenames:       {result.skipped_unparseable}")
    print(f"Errors:                      {len(result.errors)}")

    if result.errors:
        print("\nErrors:")
        for e in result.errors:
            print(f"  {e['path']}: {e['error']}")
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
