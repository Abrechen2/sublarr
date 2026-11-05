"""Whether a missing path is gone for good or only out of reach.

``os.path.exists`` answers False for a deleted file, but also for a share
that dropped (EIO, ESTALE), a permission flicker, or a mount that is not
there: an offline NAS left its mount point as an empty folder. Cleanups that
deleted rows on ``not os.path.exists`` threw away wanted items, series and
history of every library on such a share — on any install that is not one
local disk.
"""

from __future__ import annotations

import os

PRESENT = "present"
GONE = "gone"
UNKNOWN = "unknown"


class PathPresence:
    """Answers ``is_gone`` with one cached look per ancestor folder.

    A path is gone only when stat reports it missing AND its nearest existing
    ancestor vouches for it: a readable folder that is not an empty mount
    point. Any other error means "cannot tell" and keeps the row.
    """

    def __init__(self) -> None:
        self._nearest: dict[str, tuple[str, bool, bool] | None] = {}

    def state(self, path: str) -> str:
        """``PRESENT``, ``GONE`` or ``UNKNOWN`` (unreadable, or a share that is off)."""
        if not path:
            return UNKNOWN
        try:
            os.stat(path)
            return PRESENT
        except FileNotFoundError:
            pass
        except (OSError, ValueError):
            return UNKNOWN  # unreadable (EIO, ESTALE, EACCES, bad name): not proof
        if self._ancestor_vouches(os.path.dirname(os.path.abspath(path))):
            return GONE
        return UNKNOWN

    def is_gone(self, path: str) -> bool:
        return self.state(path) == GONE

    def _ancestor_vouches(self, parent: str) -> bool:
        found = self._nearest_existing(parent)
        if found is None:
            return False
        folder, empty, mount = found
        if not empty:
            return True
        # An empty folder proves only its own files gone (the last episode of
        # a season). Further up it is as likely the leftover folder of a share
        # that is not mounted, and an empty mount point is one for certain.
        return folder == parent and not mount

    def _nearest_existing(self, folder: str) -> tuple[str, bool, bool] | None:
        """(nearest existing ancestor, is it empty, is it a mount point), or None."""
        missing = []
        found = None
        while True:
            if folder in self._nearest:
                found = self._nearest[folder]
                break
            try:
                with os.scandir(folder) as entries:
                    empty = next(entries, None) is None
            except FileNotFoundError:
                missing.append(folder)
                parent = os.path.dirname(folder)
                if parent == folder:
                    break  # reached the filesystem root: nothing vouches
                folder = parent
                continue
            except OSError:
                break  # unreadable: cannot tell
            found = (folder, empty, os.path.ismount(folder))
            self._nearest[folder] = found
            break
        for f in missing:
            self._nearest[f] = found
        return found


def is_gone(path: str) -> bool:
    """One-off check; loops should share a :class:`PathPresence`."""
    return PathPresence().is_gone(path)
