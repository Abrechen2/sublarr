"""Streaming enumeration of foreign-track sweep candidates.

The old path called ``_video_files(root)``, which returned a complete list of
every video in the library — 754 s on the production library before the first
file was touched, and include/exclude scoping applied only afterwards. This
streams instead: candidates are yielded one at a time, and scoping is applied
per file as the walk goes, so the caller starts probing before the walk
finishes.

This does *not* prune the directory walk itself. ``_safe_walk`` (shared with
other cleanup rules) only yields ``(dirpath, filenames)`` — it does not expose
the ``dirs`` list a caller would need to mutate to stop ``os.walk`` from
descending into scoped-out subdirectories. So a scoped run still visits every
directory in the tree; what scoping skips is the per-file work — the
``os.stat`` here and the ffprobe call downstream — which is where the real
cost lives (754 s of walk vs. 2825 s of probing on the production library).
A scoped run is therefore cheaper than an unscoped one, but it does not avoid
paying the walk's own traversal cost.
"""

import logging
import os
import re
from collections.abc import Iterator

logger = logging.getLogger(__name__)

# tempfile.mkstemp() names its files "tmp" + 8 random chars. remux writes its
# output there, in the media directory, with the real video suffix — so a
# SIGKILL mid-remux leaves something that looks exactly like a video file.
_MKSTEMP_RE = re.compile(r"^tmp[a-z0-9_]*$", re.IGNORECASE)


def is_remux_temp(basename: str) -> bool:
    """True when ``basename`` looks like an abandoned remux temp file."""
    stem = os.path.splitext(basename)[0]
    return bool(_MKSTEMP_RE.match(stem))


def _scope_root(root: str, sub: str) -> str:
    return os.path.normpath(os.path.join(root, sub))


def _in_scope(path: str, root: str, include_paths: list[str], exclude_paths: list[str]) -> bool:
    norm = os.path.normpath(path)
    for sub in exclude_paths:
        scoped = _scope_root(root, sub)
        if norm == scoped or norm.startswith(scoped + os.sep):
            return False
    if not include_paths:
        return True
    for sub in include_paths:
        scoped = _scope_root(root, sub)
        if norm == scoped or norm.startswith(scoped + os.sep):
            return True
    return False


def _may_descend(
    dirpath: str, root: str, include_paths: list[str], exclude_paths: list[str]
) -> bool:
    """Whether files under ``dirpath`` should be processed.

    This does not stop the walk from entering ``dirpath`` — ``_safe_walk``
    gives no way to do that — it only decides whether this generator does the
    per-file work (stat, remux-temp check, yield) for files found there. An
    included subtree's ancestors must still return ``True`` here, or the
    generator would refuse to process the subtree itself once the walk (which
    always descends regardless) reaches it — so a directory that is a prefix
    of an include path is kept.
    """
    norm = os.path.normpath(dirpath)
    for sub in exclude_paths:
        scoped = _scope_root(root, sub)
        if norm == scoped or norm.startswith(scoped + os.sep):
            return False
    if not include_paths:
        return True
    for sub in include_paths:
        scoped = _scope_root(root, sub)
        if norm.startswith(scoped + os.sep) or norm == scoped or scoped.startswith(norm + os.sep):
            return True
    return False


def iter_video_files(
    root: str,
    include_paths: list[str],
    exclude_paths: list[str],
    min_age_s: int,
    now: float,
) -> Iterator[tuple[str, int, float]]:
    """Yield ``(path, size_bytes, mtime)`` for every sweep candidate.

    Skips abandoned remux temp files and anything modified within the last
    ``min_age_s`` seconds, so an in-flight import is never probed mid-write.
    """
    from services.cleanup_executors import VIDEO_EXTENSIONS, _safe_walk

    include_paths = [p for p in (include_paths or []) if p]
    exclude_paths = [p for p in (exclude_paths or []) if p]

    for dirpath, filenames in _safe_walk(root):
        if not _may_descend(dirpath, root, include_paths, exclude_paths):
            continue
        for fname in filenames:
            if os.path.splitext(fname)[1].lower() not in VIDEO_EXTENSIONS:
                continue
            if is_remux_temp(fname):
                continue
            full = os.path.join(dirpath, fname)
            if not _in_scope(full, root, include_paths, exclude_paths):
                continue
            try:
                st = os.stat(full)
            except OSError:
                continue
            if min_age_s and (now - st.st_mtime) < min_age_s:
                continue
            yield full, st.st_size, st.st_mtime


def sweep_stale_temp_files(root: str, max_age_s: int, now: float) -> int:
    """Delete abandoned remux temp files older than ``max_age_s``.

    A remux in flight writes into one of these, so only clearly-dead ones are
    removed. A file is deleted only when it BOTH carries a video extension
    (the same ``VIDEO_EXTENSIONS`` check ``iter_video_files`` applies) AND
    matches the mkstemp name pattern — ``is_remux_temp`` alone only inspects
    the stem, so without the extension check any old ``tmp*`` file anywhere
    under the media root (a stray ``.jpg``, a ``.log``, or a bare ``tmp``)
    would be unlinked. Returns the number deleted.
    """
    from services.cleanup_executors import VIDEO_EXTENSIONS, _safe_walk

    removed = 0
    for dirpath, filenames in _safe_walk(root):
        for fname in filenames:
            if os.path.splitext(fname)[1].lower() not in VIDEO_EXTENSIONS:
                continue
            if not is_remux_temp(fname):
                continue
            full = os.path.join(dirpath, fname)
            try:
                if (now - os.stat(full).st_mtime) < max_age_s:
                    continue
                os.unlink(full)
                removed += 1
                logger.info("Removed abandoned remux temp file %s", full)
            except OSError as exc:
                logger.debug("Could not remove temp file %s: %s", full, exc)
    return removed
