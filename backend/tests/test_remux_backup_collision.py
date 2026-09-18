"""Two videos of the same name must not share one backup in the trash.

Sandbox VM, 1.14.4-rc.7: ``_make_backup`` names the file after the basename and
whole seconds, so two different ``Show.mkv`` files backed up inside the same
second produced the same path — the second copy overwrote the first, and one
original had no backup left. Older than 1.14.4; the file is byte-identical to
rc.6.
"""

from __future__ import annotations

import os


def test_two_videos_of_the_same_name_keep_both_backups(tmp_path, app_ctx):
    from remux import _make_backup

    first_dir = tmp_path / "Season 1"
    second_dir = tmp_path / "Season 2"
    first_dir.mkdir()
    second_dir.mkdir()
    (first_dir / "Show.mkv").write_bytes(b"AAAA")
    (second_dir / "Show.mkv").write_bytes(b"BBBB")

    first = _make_backup(str(first_dir / "Show.mkv"), False, str(tmp_path / ".sublarr"))
    second = _make_backup(str(second_dir / "Show.mkv"), False, str(tmp_path / ".sublarr"))

    assert first != second, "the second backup overwrote the first"
    assert os.path.exists(first) and os.path.exists(second)
    assert open(first, "rb").read() == b"AAAA"
    assert open(second, "rb").read() == b"BBBB"
