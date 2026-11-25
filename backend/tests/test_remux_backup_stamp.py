"""Backups with a collision suffix keep their creation stamp (#46).

``_make_backup`` names a second backup in the same second
``<video>.<epoch>.<uuid8>.bak``. The retention sweep only recognised
``<video>.<epoch>.bak``, fell back to the mtime (which copy2 takes from the
months-old source video) and deleted the fresh backup on its next run.
"""

from __future__ import annotations

import os
import time

from remux.backup_cleanup import _derive_video_path, backup_created_at, cleanup_old_backups


def _old_copy(path, stamp: int) -> str:
    path.write_bytes(b"x")
    months_ago = time.time() - 200 * 86400
    os.utime(path, (months_ago, months_ago))
    return str(path)


def test_collision_suffix_keeps_the_stamp(tmp_path):
    now = int(time.time())
    bak = _old_copy(tmp_path / f"Episode.mkv.{now}.1a2b3c4d.bak", now)

    assert backup_created_at(bak) == now


def test_fresh_collision_backup_survives_retention(tmp_path):
    trash = tmp_path / "Show" / ".sublarr" / "trash" / "2026-11-25"
    trash.mkdir(parents=True)
    now = int(time.time())
    bak = _old_copy(trash / f"Episode.mkv.{now}.1a2b3c4d.bak", now)

    cleanup_old_backups([str(tmp_path)], retention_days=7)

    assert os.path.exists(bak)


def test_collision_suffix_is_stripped_from_the_video_name(tmp_path):
    bak = "/media/Show/.sublarr/trash/2026-11-25/Episode.mkv.1775388610.1a2b3c4d.bak"

    assert _derive_video_path(bak) == "/media/Show/Episode.mkv"
