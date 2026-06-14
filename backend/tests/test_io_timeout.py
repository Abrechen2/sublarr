"""Tests for size-aware subprocess timeout computation.

File sizes are injected via monkeypatch rather than real files — creating
multi-GB files on a non-sparse filesystem (Windows NTFS) would physically
allocate the space, so we never touch the disk here.
"""

from __future__ import annotations

import pytest

from utils import io_timeout
from utils.io_timeout import compute_io_timeout

_GB = 1024**3


@pytest.fixture
def fake_size(monkeypatch):
    """Return a setter that makes os.path.getsize report a fixed size."""

    def _set(size_bytes):
        monkeypatch.setattr(io_timeout.os.path, "getsize", lambda _p: size_bytes)

    return _set


def test_small_file_returns_floor(fake_size):
    fake_size(50 * 1024 * 1024)  # 50 MB → ~303 s, clamped up to floor 600
    assert compute_io_timeout("any.mkv") == 600


def test_25gb_file_scales(fake_size):
    fake_size(25 * _GB)  # 300 + 25*60 = 1800
    assert compute_io_timeout("big.mkv") == 1800


def test_huge_file_capped(fake_size):
    fake_size(200 * _GB)  # 300 + 200*60 = 12300 → clamped to cap 3600
    assert compute_io_timeout("huge.mkv") == 3600


def test_boundary_just_under_cap(fake_size):
    fake_size(54 * _GB)  # 300 + 54*60 = 3540 (just under cap 3600)
    assert compute_io_timeout("edge.mkv") == 3540


def test_missing_path_returns_floor(monkeypatch):
    def _raise(_p):
        raise OSError("no such file")

    monkeypatch.setattr(io_timeout.os.path, "getsize", _raise)
    assert compute_io_timeout("does-not-exist.mkv") == 600


def test_custom_floor_respected(fake_size):
    # ffsubsync passes its class default as the floor; a tiny file must
    # never drop below it.
    fake_size(10 * 1024 * 1024)
    assert compute_io_timeout("tiny.mkv", floor=600) == 600


def test_result_always_within_bounds(fake_size):
    for size_gb in (0, 1, 8, 25, 60, 100):
        fake_size(size_gb * _GB)
        result = compute_io_timeout("f.mkv")
        assert 600 <= result <= 3600
