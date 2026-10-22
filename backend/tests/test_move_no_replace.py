"""``move_no_replace`` never overwrites, with or without hard links.

Codex review of 1.17.0-rc.11: an exists-check before ``shutil.move`` leaves a
window in which a subtitle saved meanwhile is replaced for good.
"""

import contextlib
import errno
import os
from unittest.mock import patch

import pytest

from utils.atomic_write import move_no_replace


@pytest.fixture(params=["link", "no-link"])
def share(request):
    if request.param == "link":
        yield
        return
    with patch("utils.atomic_write.os.link", side_effect=OSError(errno.EPERM, "no links")):
        yield


def test_moves_to_a_free_name(tmp_path, share):
    src, dst = tmp_path / "a.srt", tmp_path / "b.srt"
    src.write_bytes(b"alt")

    move_no_replace(str(src), str(dst))

    assert not src.exists()
    assert dst.read_bytes() == b"alt"


def test_refuses_an_occupied_name_and_keeps_both(tmp_path, share):
    src, dst = tmp_path / "a.srt", tmp_path / "b.srt"
    src.write_bytes(b"alt")
    dst.write_bytes(b"neu")

    with pytest.raises(FileExistsError):
        move_no_replace(str(src), str(dst))

    assert src.read_bytes() == b"alt"
    assert dst.read_bytes() == b"neu"


def test_a_failed_copy_leaves_no_partial_file(tmp_path):
    src, dst = tmp_path / "a.srt", tmp_path / "b.srt"
    src.write_bytes(b"alt")
    with (
        patch("utils.atomic_write.os.link", side_effect=OSError(errno.EXDEV, "cross-device")),
        patch("utils.atomic_write.shutil.copyfileobj", side_effect=OSError(errno.ENOSPC, "full")),
        pytest.raises(OSError),
    ):
        move_no_replace(str(src), str(dst))

    assert src.read_bytes() == b"alt"
    assert not dst.exists()


def test_other_link_errors_are_not_masked(tmp_path):
    src, dst = tmp_path / "a.srt", tmp_path / "b.srt"
    src.write_bytes(b"alt")
    with (
        patch("utils.atomic_write.os.link", side_effect=OSError(errno.EIO, "io")),
        pytest.raises(OSError, match="io"),
    ):
        move_no_replace(str(src), str(dst))
    assert src.exists()


def test_a_failed_copy_spares_a_file_that_replaced_the_half_copy(tmp_path):
    """Codex review: a download that lands mid-copy wins; cleanup must not delete it."""
    src, dst = tmp_path / "a.srt", tmp_path / "b.srt"
    src.write_bytes(b"alt")

    def download_lands_then_disk_fails(_reader, _writer):
        replacement = tmp_path / "download.tmp"
        replacement.write_bytes(b"neu")
        os.replace(replacement, dst)
        raise OSError(errno.EIO, "io")

    with (
        patch("utils.atomic_write.os.link", side_effect=OSError(errno.EPERM, "no links")),
        patch("utils.atomic_write.shutil.copyfileobj", side_effect=download_lands_then_disk_fails),
        pytest.raises(OSError),
    ):
        move_no_replace(str(src), str(dst))

    assert dst.read_bytes() == b"neu"
    assert src.read_bytes() == b"alt"


def test_an_unreadable_source_touches_nothing(tmp_path):
    dst = tmp_path / "b.srt"
    dst.write_bytes(b"neu")
    with (
        patch("utils.atomic_write.os.link", side_effect=OSError(errno.EPERM, "no links")),
        pytest.raises(FileNotFoundError),
    ):
        move_no_replace(str(tmp_path / "missing.srt"), str(dst))
    assert dst.read_bytes() == b"neu"


def test_a_failed_close_leaves_no_partial_file(tmp_path):
    """Codex review: closing flushes the last bytes and can fail too."""
    import builtins

    src, dst = tmp_path / "a.srt", tmp_path / "b.srt"
    src.write_bytes(b"alt")
    real_open = builtins.open

    class FailingClose:
        def __init__(self, fh):
            self._fh = fh

        def __getattr__(self, name):
            return getattr(self._fh, name)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self._fh.close()
            raise OSError(errno.ENOSPC, "No space left")

    def fake_open(path, mode="r", *args, **kwargs):
        fh = real_open(path, mode, *args, **kwargs)
        return FailingClose(fh) if mode == "xb" else fh

    with (
        patch("utils.atomic_write.os.link", side_effect=OSError(errno.EPERM, "no links")),
        patch("utils.atomic_write.open", side_effect=fake_open, create=True),
        pytest.raises(OSError, match="No space"),
    ):
        move_no_replace(str(src), str(dst))

    assert not dst.exists()
    assert src.read_bytes() == b"alt"


@pytest.mark.parametrize("links", [True, False])
def test_a_symlink_source_is_refused(tmp_path, links):
    """Security review: copying through a planted link would read its target."""
    secret = tmp_path / "secret"
    secret.write_bytes(b"geheim")
    src, dst = tmp_path / "a.srt.quality.json", tmp_path / "media" / "a.srt.quality.json"
    dst.parent.mkdir()
    src.symlink_to(secret)
    share = (
        contextlib.nullcontext()
        if links
        else patch("utils.atomic_write.os.link", side_effect=OSError(errno.EXDEV, "x"))
    )
    with share, pytest.raises(OSError):
        move_no_replace(str(src), str(dst))

    assert not dst.exists()
    assert src.is_symlink()
