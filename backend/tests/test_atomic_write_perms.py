"""Regression: atomically-written sidecars must be group/other-readable.

``tempfile.mkstemp`` always creates its file 0600, so before the chmod fix every
subtitle written through ``utils.atomic_write`` (download, manual upload, combine)
landed ``-rw-------`` — unreadable by the media server (Emby/Jellyfin) and any
other user. The helpers now relax the temp file to ``0o644 & ~umask`` before the
atomic rename. See the ``feedback_media_file_perms_emby`` note.
"""

from __future__ import annotations

import os
import stat
import sys

import pytest

from utils.atomic_write import atomic_save_subs, atomic_write_bytes, atomic_write_via

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX file-mode semantics do not apply on Windows"
)


def _mode(path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


def test_atomic_write_bytes_is_readable(tmp_path):
    old = os.umask(0o022)
    try:
        p = tmp_path / "sub.srt"
        atomic_write_bytes(str(p), b"1\n00:00:01,000 --> 00:00:02,000\nHi\n")
        mode = _mode(p)
        assert mode == 0o644, f"expected 0644, got {oct(mode)} (must not be 0600)"
        assert mode & stat.S_IRGRP and mode & stat.S_IROTH
    finally:
        os.umask(old)


def test_atomic_write_via_is_readable(tmp_path):
    old = os.umask(0o022)
    try:
        p = tmp_path / "sub2.ass"
        atomic_write_via(str(p), lambda tmp: open(tmp, "w", encoding="utf-8").close())
        assert _mode(p) == 0o644
    finally:
        os.umask(old)


def test_atomic_save_subs_is_readable(tmp_path):
    import pysubs2

    old = os.umask(0o022)
    try:
        subs = pysubs2.SSAFile()
        ev = pysubs2.SSAEvent(start=1000, end=3000)
        ev.plaintext = "Hallo"
        subs.events.append(ev)
        p = tmp_path / "sub3.srt"
        atomic_save_subs(subs, str(p), format_="srt")
        assert _mode(p) == 0o644
    finally:
        os.umask(old)


def test_respects_restrictive_umask(tmp_path):
    """A restrictive umask still wins — 0644 minus the umask, never wider."""
    old = os.umask(0o077)
    try:
        p = tmp_path / "sub4.srt"
        atomic_write_bytes(str(p), b"x")
        assert _mode(p) == 0o600  # 0o644 & ~0o077
    finally:
        os.umask(old)
