"""Atomic file-write helpers.

A crash (OOM, SIGKILL, power loss) between ``open(path, "w")`` and the final
flush leaves a truncated/half-written file on disk. For subtitle sidecars that
means a corrupt ``.srt``/``.ass`` silently replacing a previously-good one.

These helpers write to a temporary file in the *same directory* as the target
and then ``os.replace`` it into place. ``os.replace`` is atomic on POSIX and on
Windows when source and destination are on the same volume, so a reader either
sees the complete old file or the complete new one — never a partial write.

This mirrors the proven pattern already used by the remux pipeline
(tmp → verify → ``os.replace``).
"""

import contextlib
import logging
import os
import re
import shutil
import tempfile
import time
from collections.abc import Callable

__all__ = [
    "atomic_copyfile",
    "atomic_write_bytes",
    "atomic_write_via",
    "atomic_save_subs",
    "sweep_orphaned_temps",
]

logger = logging.getLogger(__name__)

# Hidden, and unmistakably ours — which is what lets sweep_orphaned_temps
# delete by pattern. The remux pipeline uses a longer prefix and sweeps its own
# (multi-gigabyte) temps; this sweep leaves those alone.
_TEMP_PREFIX = ".sublarr-"
_REMUX_TEMP_PREFIX = ".sublarr-remux-"

# A subtitle write finishes in seconds; anything this old belongs to a process
# that is gone. The margin protects a second worker writing into the same
# directory right now.
_ORPHAN_MAX_AGE_SECONDS = 6 * 60 * 60

# Before the prefix existed, extraction used a bare mkstemp: "tmp" + 8 random
# characters. Those are only reclaimed when empty — ffmpeg killed before its
# first write — because a non-empty one is not provably ours.
_LEGACY_MKSTEMP_RE = re.compile(r"^tmp[a-z0-9_]{8}\.(srt|ass|ssa|vtt|sub)$", re.IGNORECASE)


def _current_umask() -> int:
    """Read the process umask without permanently changing it."""
    cur = os.umask(0o022)
    os.umask(cur)
    return cur


def _make_world_readable(path: str) -> None:
    """Relax a ``mkstemp`` file (created 0600) to 0644 minus the current umask.

    ``tempfile.mkstemp`` always creates the temp file 0600 regardless of umask,
    so a sidecar moved into place from it is unreadable by the media server
    (Emby/Jellyfin) and any other user. Match what a plain ``open()`` would have
    produced instead. Mirrors ``services.subtitle_health.fixers.common``.
    """
    with contextlib.suppress(OSError):
        os.chmod(path, 0o644 & ~_current_umask())


def _same_dir_tempfile(target_path: str) -> tuple[int, str]:
    """Create a temp file next to ``target_path`` and return (fd, tmp_path).

    The temp file keeps the target's extension (e.g. ``.ass``/``.srt``) so
    libraries that infer a format from the file suffix — pysubs2's
    ``SSAFile.save`` does exactly this when no ``format_`` is passed — behave
    the same when writing the temp file as they would the final path.
    """
    target_dir = os.path.dirname(os.path.abspath(target_path)) or "."
    ext = os.path.splitext(target_path)[1] or ".tmp"
    # Every writer passes through here, so a temp orphaned by a killed process
    # is reclaimed the next time anything is written into that directory.
    sweep_orphaned_temps(target_dir)
    return tempfile.mkstemp(suffix=ext, prefix=_TEMP_PREFIX, dir=target_dir)


def _is_orphan_candidate(name: str, size: int) -> bool:
    if name.startswith(_TEMP_PREFIX):
        return not name.startswith(_REMUX_TEMP_PREFIX)
    return size == 0 and bool(_LEGACY_MKSTEMP_RE.match(name))


def sweep_orphaned_temps(directory: str) -> int:
    """Delete stale write temps left in ``directory``; return how many went.

    The cleanup around every atomic write unlinks its temp, but a process that
    is killed outright (container stop, host shutdown) never reaches it, and the
    temp stays next to the episode for good. Call this before writing into a
    library directory: no library-wide walk, and only files carrying our own
    prefix — or empty legacy ``mkstemp`` names — older than six hours are
    considered. Failures are logged and ignored.
    """
    try:
        entries = list(os.scandir(directory))
    except OSError:
        return 0

    cutoff = time.time() - _ORPHAN_MAX_AGE_SECONDS
    removed = 0
    for entry in entries:
        try:
            if not entry.is_file(follow_symlinks=False):
                continue
            st = entry.stat(follow_symlinks=False)
            if st.st_mtime > cutoff or not _is_orphan_candidate(entry.name, st.st_size):
                continue
            os.unlink(entry.path)
        except OSError as exc:
            logger.warning("Could not remove orphaned temp %s: %s", entry.path, exc)
            continue
        removed += 1
        logger.info("Removed orphaned temp %s", entry.path)
    return removed


def atomic_write_bytes(path: str, data: bytes) -> None:
    """Write ``data`` to ``path`` atomically (tmp file + ``os.replace``)."""
    fd, tmp_path = _same_dir_tempfile(path)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        _make_world_readable(tmp_path)
        os.replace(tmp_path, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


def atomic_copyfile(src: str, dst: str) -> None:
    """Copy ``src``'s contents onto ``dst`` atomically, ignoring ``dst``'s metadata.

    ``shutil.copy2`` onto an *existing* dst owned by another uid (the PUID
    changed over the years: 1000 in 2026-06, 99 today) writes the content and
    then dies in ``copystat``/``utime`` with ``[Errno 1] Operation not
    permitted`` — the caller sees a failure while dst is already half
    overwritten. The temp-file + ``os.replace`` route never opens dst at all;
    the rename needs only write permission on the directory.

    Deliberately copies no metadata: a backup's mtime should say when the
    backup was made, not when the source was.
    """
    fd, tmp_path = _same_dir_tempfile(dst)
    try:
        with os.fdopen(fd, "wb") as out, open(src, "rb") as inp:
            shutil.copyfileobj(inp, out)
            out.flush()
            os.fsync(out.fileno())
        _make_world_readable(tmp_path)
        os.replace(tmp_path, dst)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


def atomic_write_via(path: str, writer: Callable[[str], None]) -> None:
    """Atomically produce ``path`` by letting ``writer`` write a temp path.

    ``writer`` receives the temp path to write to; on success the temp file is
    atomically moved onto ``path``. Use for libraries whose save API takes a
    path string (e.g. pysubs2's ``SSAFile.save``).
    """
    fd, tmp_path = _same_dir_tempfile(path)
    os.close(fd)
    try:
        writer(tmp_path)
        _make_world_readable(tmp_path)
        os.replace(tmp_path, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


def atomic_save_subs(subs, path: str, **save_kwargs) -> None:
    """Atomically save a pysubs2 ``SSAFile`` to ``path``.

    Forwards ``save_kwargs`` (e.g. ``format_``, ``encoding``) to ``subs.save``.
    """
    atomic_write_via(path, lambda tmp: subs.save(tmp, **save_kwargs))
