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
import os
import tempfile
from collections.abc import Callable

__all__ = ["atomic_write_bytes", "atomic_write_via", "atomic_save_subs"]


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
    return tempfile.mkstemp(suffix=ext, prefix=".sublarr-", dir=target_dir)


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
