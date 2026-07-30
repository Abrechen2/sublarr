"""Restore a subtitle sidecar from its single-slot ``.bak`` backup.

Extracted from ``routes.subtitle_processor.undo_process`` so the History
rollback endpoint (``POST /api/v1/history/<id>/rollback``) can share the
exact same swap semantics instead of growing a second, subtly different
implementation.

The contract is the one the undo route has always had: when the active
sidecar still exists, a 3-rename atomic swap flips active and bak so a
second invocation flips them back (no data loss either way). When the
active is gone, the bak is simply renamed into place.
"""

from __future__ import annotations

import logging
import os

from subtitle_filename import bak_path_for, find_existing_bak

logger = logging.getLogger(__name__)


class RestoreError(Exception):
    """Restore failed. ``http_status`` maps the failure onto the API response."""

    def __init__(self, message: str, http_status: int = 409):
        super().__init__(message)
        self.http_status = http_status


def restore_from_bak(abs_path: str) -> dict:
    """Swap ``abs_path`` with its ``.bak`` backup.

    Args:
        abs_path: Absolute path of the active subtitle sidecar to restore.
            Path-safety validation is the caller's job — this function only
            performs filesystem renames.

    Returns:
        ``{"status": "restored", "path": ..., "swapped": bool}`` plus an
        optional ``"warning"`` key when the restore succeeded but the new
        bak could not be written back.

    Raises:
        RestoreError: No backup exists (404) or a rename failed (409).
    """
    # Resolve where the bak actually lives. find_existing_bak checks the
    # canonical hidden location first, then the legacy sibling location
    # so pre-migration backups still restore correctly.
    bak_path = find_existing_bak(abs_path)
    if bak_path is None:
        raise RestoreError("No backup found for this file", http_status=404)

    # Where new baks must land going forward — different from bak_path
    # when we're restoring a legacy sibling-located backup.
    canonical_bak_path = bak_path_for(abs_path)

    if not os.path.exists(abs_path):
        # Active sub gone — simple rename, nothing to swap.
        try:
            os.replace(bak_path, abs_path)
        except OSError as e:
            raise RestoreError(f"Could not restore backup: {e}") from e
        return {"status": "restored", "path": abs_path, "swapped": False}

    # Atomic swap via temp path. If step 2 or 3 fails we roll back step 1.
    # Step 3 always lands the new bak in the canonical hidden location,
    # even when the source bak was a legacy sibling — every restore
    # opportunistically migrates the layout.
    os.makedirs(os.path.dirname(canonical_bak_path), exist_ok=True)
    tmp_path = f"{bak_path}.swap-tmp"
    try:
        os.replace(abs_path, tmp_path)  # step 1: active -> tmp
    except OSError as e:
        raise RestoreError(f"Could not stage active file: {e}") from e
    try:
        os.replace(bak_path, abs_path)  # step 2: bak -> active
    except OSError as e:
        try:
            os.replace(tmp_path, abs_path)  # rollback step 1
        except OSError:
            logger.error(
                "restore: rollback failed; left tmp at %s, active gone", tmp_path, exc_info=True
            )
        raise RestoreError(f"Could not restore backup: {e}") from e
    try:
        os.replace(tmp_path, canonical_bak_path)  # step 3: tmp -> canonical bak
    except OSError as e:
        # Active is restored but new bak failed to land. Active state is
        # correct; surface the partial outcome so the caller can decide.
        logger.warning("restore: swap completed but new bak rename failed: %s", e)
        return {"status": "restored", "path": abs_path, "swapped": False, "warning": str(e)}

    return {"status": "restored", "path": abs_path, "swapped": True}


def backup_before_replace(active_path: str) -> str | None:
    """Preserve ``active_path`` into the single-slot bak before it is replaced.

    Only writes when NO backup exists yet (canonical or legacy) — the bak is
    a single-slot undo and an existing one must never be overwritten (see
    tests/test_processing_bak_is_never_overwritten.py for the incident that
    rule comes from).

    Returns the bak path when a backup was created, else ``None``. Never
    raises: a failed backup must not abort the download/upgrade that
    triggered it.
    """
    try:
        if not os.path.isfile(active_path):
            return None
        if find_existing_bak(active_path) is not None:
            return None
        bak_path = bak_path_for(active_path)
        os.makedirs(os.path.dirname(bak_path), exist_ok=True)
        import shutil

        shutil.copy2(active_path, bak_path)
        logger.info("Backed up %s -> %s before replacement", active_path, bak_path)
        return bak_path
    except OSError as e:
        logger.warning("Could not back up %s before replacement: %s", active_path, e)
        return None
