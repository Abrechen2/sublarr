"""A missing path counts as deleted only when the disk can vouch for it."""

import errno
import os
from unittest.mock import patch

from utils.path_presence import PathPresence


def test_an_existing_file_is_not_gone(tmp_path):
    f = tmp_path / "a.mkv"
    f.write_bytes(b"x")
    assert PathPresence().is_gone(str(f)) is False


def test_a_deleted_episode_beside_others_is_gone(tmp_path):
    (tmp_path / "S01").mkdir()
    (tmp_path / "S01" / "e02.mkv").write_bytes(b"x")
    assert PathPresence().is_gone(str(tmp_path / "S01" / "e01.mkv")) is True


def test_a_deleted_series_folder_is_gone(tmp_path):
    (tmp_path / "Other Show").mkdir()
    assert PathPresence().is_gone(str(tmp_path / "Show" / "S01" / "e01.mkv")) is True


def test_the_last_episode_of_an_empty_folder_is_gone(tmp_path):
    (tmp_path / "S01").mkdir()
    assert PathPresence().is_gone(str(tmp_path / "S01" / "e01.mkv")) is True


def test_an_io_error_is_not_proof(tmp_path):
    def stat(path, *a, **k):
        raise OSError(errno.EIO, "Input/output error", path)

    with patch("utils.path_presence.os.stat", side_effect=stat):
        assert PathPresence().is_gone(str(tmp_path / "a.mkv")) is False


def test_an_empty_mount_point_is_an_offline_share(tmp_path):
    mount = tmp_path / "nas"
    mount.mkdir()
    real_ismount = os.path.ismount
    with patch(
        "utils.path_presence.os.path.ismount",
        side_effect=lambda p: p == str(mount) or real_ismount(p),
    ):
        assert PathPresence().is_gone(str(mount / "Show" / "e01.mkv")) is False


def test_an_unreadable_ancestor_is_not_proof(tmp_path):
    def scandir(path):
        raise PermissionError(errno.EACCES, "denied", path)

    with patch("utils.path_presence.os.scandir", side_effect=scandir):
        assert PathPresence().is_gone(str(tmp_path / "S01" / "e01.mkv")) is False


def test_an_empty_leftover_folder_further_up_is_not_proof(tmp_path):
    """A share unmounted below a bind mount leaves an empty plain folder."""
    (tmp_path / "tv").mkdir()
    assert PathPresence().is_gone(str(tmp_path / "tv" / "Show" / "S01" / "e01.mkv")) is False
