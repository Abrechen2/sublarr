"""Remux backups remember where they came from (#47).

Backups go to a central <media>/.sublarr/trash/<date>/ that keeps only the
basename. The listing rebuilt the origin as if the trash sat beside the
video, so a backup from "Show A/episode.mkv" was offered for restore onto an
unrelated "<media>/episode.mkv" — and the restore overwrote it.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from remux import _make_backup
from remux.backup_cleanup import cleanup_old_backups, list_backups, origin_path_for


def _backup(media, video):
    settings = MagicMock(media_path=str(media))
    with patch("config.get_settings", return_value=settings):
        return _make_backup(str(video), use_reflink=False)


def _setup(tmp_path):
    media = tmp_path / "media"
    show = media / "Show A"
    show.mkdir(parents=True)
    video = show / "episode.mkv"
    video.write_bytes(b"original A")
    return media, video


def test_listing_names_the_real_origin(tmp_path):
    media, video = _setup(tmp_path)
    _backup(media, video)

    [entry] = list_backups([str(media)])
    assert entry["video_path"] == str(video)


def test_a_same_named_video_elsewhere_is_never_offered(tmp_path):
    media, video = _setup(tmp_path)
    bak = _backup(media, video)
    (media / "episode.mkv").write_bytes(b"UNRELATED")
    os.remove(origin_path_for(bak))  # a legacy backup without a record

    [entry] = list_backups([str(media)])
    assert entry["video_path"] is None


def test_retention_removes_the_origin_record_too(tmp_path):
    media, video = _setup(tmp_path)
    bak = _backup(media, video)
    old = 1_000_000_000
    os.utime(bak, (old, old))
    with patch("remux.backup_cleanup.backup_created_at", return_value=old):
        cleanup_old_backups([str(media)], retention_days=1)

    assert not os.path.exists(bak)
    assert not os.path.exists(origin_path_for(bak))
