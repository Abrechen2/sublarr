"""Sync engines install a pinned version, and alass only with its known hash.

Code check 2026-11-05 (Forgejo #75): alass came from ``releases/latest``
without a hash and was made executable; ffsubsync was pip-installed unpinned.
A replaced upstream release ran as code in the container.
"""

import hashlib
import os
import stat
from unittest.mock import MagicMock, patch

import pytest

from services import video_sync

GOOD = b"\x7fELF fake alass"


def _fake_get(body: bytes):
    resp = MagicMock()
    resp.content = body
    resp.raise_for_status = MagicMock()
    return MagicMock(return_value=resp)


@pytest.fixture
def linux(monkeypatch, tmp_path):
    monkeypatch.setattr(video_sync.platform, "system", lambda: "Linux")
    monkeypatch.setattr(video_sync.platform, "machine", lambda: "x86_64")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setitem(
        video_sync._ALASS_ASSETS,
        ("linux", "x86_64"),
        ("alass-linux64", hashlib.sha256(GOOD).hexdigest()),
    )
    return tmp_path


def test_alass_with_the_pinned_hash_is_installed(linux):
    get = _fake_get(GOOD)
    with patch("security_utils.get_with_checked_redirects", get):
        video_sync._install_alass_binary()
    url = get.call_args.args[0]
    assert f"/download/{video_sync.ALASS_VERSION}/alass-linux64" in url
    assert "latest" not in url
    path = linux / ".local" / "bin" / "alass"
    assert path.read_bytes() == GOOD
    assert os.stat(path).st_mode & stat.S_IXUSR


def test_alass_with_another_hash_is_not_written(linux):
    with (
        patch("security_utils.get_with_checked_redirects", _fake_get(b"tampered")),
        pytest.raises(RuntimeError, match="SHA-256"),
    ):
        video_sync._install_alass_binary()
    assert not (linux / ".local" / "bin" / "alass").exists()


def test_alass_without_a_pinned_build_is_refused(monkeypatch):
    monkeypatch.setattr(video_sync.platform, "system", lambda: "Linux")
    monkeypatch.setattr(video_sync.platform, "machine", lambda: "aarch64")
    with pytest.raises(RuntimeError, match="install alass yourself"):
        video_sync._install_alass_binary()


def test_ffsubsync_is_installed_at_the_pinned_version():
    done = MagicMock(returncode=0, stderr="")
    with patch.object(video_sync.subprocess, "run", return_value=done) as run:
        video_sync.install_engine("ffsubsync")
    assert f"ffsubsync=={video_sync.FFSUBSYNC_VERSION}" in run.call_args.args[0]
