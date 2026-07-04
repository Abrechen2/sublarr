"""Resolved media roots + remux trash directories.

Moved from ``routes/remux.py`` (``_media_paths`` / ``_trash_paths``) on
2026-07-02 so services (e.g. ``services.cleanup_rule_runner``) no longer
import from the routes layer. ``routes/remux.py`` keeps thin delegating
shims under the old names — tests patch ``routes.remux._trash_paths``.
"""

from __future__ import annotations

import os

from config import get_settings


def media_paths() -> list[str]:
    """Return the configured media roots (primary + extra_media_paths)."""
    settings = get_settings()
    paths = []
    media = getattr(settings, "media_path", "")
    if media:
        paths.append(media)
    extra = getattr(settings, "extra_media_paths", "")
    if extra:
        paths.extend(p.strip() for p in extra.split(",") if p.strip())
    return paths


def remux_trash_paths() -> list[str]:
    """Return the resolved trash directory paths (one per media root)."""
    settings = get_settings()
    trash_dir = getattr(settings, "remux_trash_dir", ".sublarr")
    result = []
    if os.path.isabs(trash_dir):
        return [os.path.join(trash_dir, "trash")]
    for media_path in media_paths():
        result.append(os.path.join(media_path, trash_dir, "trash"))
    return result
