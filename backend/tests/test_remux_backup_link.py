"""The remux backup must not copy a video it can simply keep.

Prod 2026-10-02: a subtitle_automation tick was abandoned while
``_make_backup`` was copying a two-hour film into the trash — 26 minutes of
``shutil.copy2`` after a 15-minute mkvmerge, and 120 s before that wasted on
``cp --reflink=auto``, which on Unraid's shfs silently does a full copy too
and was killed by its timeout. Every remux backup there was a full copy (and
was logged as "reflink backup"), ~300 GB a day while the foreign-track sweep
runs.

A remux swaps the new file in by rename, so the original inode is never
written again. A hardlink in the trash therefore *is* a full backup, made
instantly and without I/O.
"""

from __future__ import annotations

import errno
import os
from unittest.mock import patch

import pytest

from remux import _make_backup, _try_reflink


def _video(tmp_path, content: bytes = b"original" * 64) -> str:
    path = tmp_path / "Show" / "Season 1" / "show - S01E01.mkv"
    path.parent.mkdir(parents=True)
    path.write_bytes(content)
    return str(path)


def _no_copy(*_args, **_kwargs):
    raise AssertionError("the backup copied the video instead of linking it")


def test_backup_is_a_hardlink_and_copies_nothing(tmp_path):
    video = _video(tmp_path)

    with (
        patch("remux.shutil.copy2", side_effect=_no_copy),
        patch("remux._try_reflink", side_effect=_no_copy),
    ):
        bak = _make_backup(video, use_reflink=True, trash_dir=str(tmp_path / ".sublarr"))

    assert os.path.samefile(video, bak)
    assert bak.endswith(".bak")
    assert os.path.dirname(os.path.dirname(bak)).endswith(os.path.join(".sublarr", "trash"))


def test_hardlinked_backup_keeps_the_original_across_the_swap(tmp_path):
    """The contract the hardlink relies on: the new file replaces the old by
    rename, so the backup still holds the original bytes afterwards."""
    original = b"original" * 64
    video = _video(tmp_path, original)
    bak = _make_backup(video, use_reflink=False, trash_dir=str(tmp_path / ".sublarr"))

    tmp = os.path.join(os.path.dirname(video), ".sublarr-remux-x.mkv")
    with open(tmp, "wb") as fh:
        fh.write(b"remuxed")
    os.replace(tmp, video)

    with open(bak, "rb") as fh:
        assert fh.read() == original
    with open(video, "rb") as fh:
        assert fh.read() == b"remuxed"


def test_backup_with_a_taken_name_gets_a_fresh_one(tmp_path):
    video = _video(tmp_path)
    trash = str(tmp_path / ".sublarr")

    with patch("time.time", return_value=1_790_000_000):
        first = _make_backup(video, use_reflink=False, trash_dir=trash)
        second = _make_backup(video, use_reflink=False, trash_dir=trash)

    assert first != second
    assert os.path.samefile(first, video)
    assert os.path.samefile(second, video)


@pytest.mark.parametrize("err", [errno.EXDEV, errno.EPERM, errno.EMLINK])
def test_backup_falls_back_to_a_copy_when_the_link_is_refused(tmp_path, err):
    video = _video(tmp_path)

    with (
        patch("remux.os.link", side_effect=OSError(err, os.strerror(err))),
        patch("remux._try_reflink", return_value=False),
    ):
        bak = _make_backup(video, use_reflink=True, trash_dir=str(tmp_path / ".sublarr"))

    assert not os.path.samefile(video, bak)
    with open(video, "rb") as a, open(bak, "rb") as b:
        assert a.read() == b.read()


def test_copy_fallback_does_not_leave_a_link_attempt_behind(tmp_path):
    video = _video(tmp_path)
    trash = str(tmp_path / ".sublarr")

    with patch("remux.os.link", side_effect=OSError(errno.EXDEV, "cross-device")):
        bak = _make_backup(video, use_reflink=False, trash_dir=trash)

    day_dir = os.path.dirname(bak)
    assert os.listdir(day_dir) == [os.path.basename(bak)]


def test_reflink_is_requested_strictly_not_auto():
    """``--reflink=auto`` falls back to a full copy inside cp, so on a
    filesystem without CoW the "reflink" branch was a copy under a 120 s
    timeout, logged as a reflink. ``always`` fails fast instead."""
    captured = {}

    def fake_run(cmd, **_kwargs):
        captured["cmd"] = cmd

        class _Done:
            returncode = 1

        return _Done()

    with patch("remux.subprocess.run", side_effect=fake_run):
        assert _try_reflink("/a.mkv", "/b.bak") is False

    assert "--reflink=always" in captured["cmd"]
    assert "--reflink=auto" not in captured["cmd"]
