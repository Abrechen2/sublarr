"""Sync-subprocess throttling primitives.

ffsubsync and alass both spawn long-running CPU+IO-heavy subprocesses. Without
throttling they can fan out across multiple Flask threads — uncontrolled bulk
operations from the UI plus inline auto-sync from wanted-search produced load
spikes >9 on the host (Cardinal, 2026-05-14 incident).

A module-level BoundedSemaphore(1) lets at most one sync subprocess run at a
time across all callers in this Gunicorn process. Gunicorn runs single-worker
(``--workers 1 --threads 4``), so a thread primitive is sufficient — no need
for a cross-process file lock.

``nice_prefix`` lowers scheduling priority on Linux so the subprocess yields
to whatever else needs the CPU (Plex, HA VM, qBittorrent).
"""

from __future__ import annotations

import platform
import shutil
import threading

sync_subprocess_lock = threading.BoundedSemaphore(1)


def nice_prefix() -> list[str]:
    """Return ``["nice", "-n", "19"]`` when nice is available on Linux, else ``[]``.

    Returning a list (not a string) keeps it safe to splice into a subprocess
    argv without shell interpolation. On Windows / when nice is missing the
    prefix is empty and the caller's command runs unchanged.
    """
    if platform.system() != "Linux":
        return []
    if not shutil.which("nice"):
        return []
    return ["nice", "-n", "19"]
