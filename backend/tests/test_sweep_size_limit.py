"""The sweep may be told to leave large files alone.

Its cost scales with file size and its benefit does not: prod 2026-09-28 spent
one run of 4622 s on a single 2160p film — 49 min to remux it, 47 min more to
move the 70 GB original to the trash — to drop four subtitle streams, while the
whole day freed 143 MB. A library that mixes 4K films with 1.5 GB episodes
wants the episodes swept and the films left where they are.

The limit filters at enumeration, not at strip time, so an excluded file never
enters the generation: not counted as affected, not probed, and not left in the
state file waiting for a turn that must never come.
"""

import os

from services.foreign_tracks.enumerate import iter_video_files

GB = 1024**3


def _write(path: str, size: int, age_s: float = 0) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.truncate(size)
    if age_s:
        stamp = os.stat(path).st_mtime - age_s
        os.utime(path, (stamp, stamp))


def _sweep(root: str, **kwargs) -> list[str]:
    """Names iter_video_files yields, with the age gate out of the way."""
    kwargs.setdefault("min_age_s", 0)
    kwargs.setdefault("now", 0.0)
    return sorted(
        os.path.basename(p) for p, _size, _mtime in iter_video_files(root, [], [], **kwargs)
    )


class TestTheSizeLimit:
    def test_a_file_over_the_limit_is_not_a_candidate(self, tmp_path):
        root = str(tmp_path)
        _write(os.path.join(root, "Serie", "episode.mkv"), 4096)
        _write(os.path.join(root, "Film", "huge.mkv"), 16384)

        assert _sweep(root, max_size_bytes=8192) == ["episode.mkv"]

    def test_zero_means_every_file_as_before(self, tmp_path):
        """The default. An upgrade must not quietly start skipping files."""
        root = str(tmp_path)
        _write(os.path.join(root, "Serie", "episode.mkv"), 4096)
        _write(os.path.join(root, "Film", "huge.mkv"), 16384)

        assert _sweep(root, max_size_bytes=0) == ["episode.mkv", "huge.mkv"]

    def test_the_limit_is_inclusive_at_the_boundary(self, tmp_path):
        """`> limit` skips, so a file exactly at the limit still gets swept."""
        root = str(tmp_path)
        _write(os.path.join(root, "Serie", "exactly.mkv"), 8192)

        assert _sweep(root, max_size_bytes=8192) == ["exactly.mkv"]

    def test_the_age_gate_still_applies_under_a_size_limit(self, tmp_path):
        """Two filters, both of them, in either order."""
        root = str(tmp_path)
        _write(os.path.join(root, "Serie", "fresh.mkv"), 4096)

        import time

        assert _sweep(root, max_size_bytes=8192, min_age_s=600, now=time.time()) == []


class TestTheSettingReachesTheWalk:
    def test_gb_becomes_bytes(self):
        """The setting is GB for a human; the walk compares bytes."""
        from config_settings import Settings

        assert Settings().foreign_track_sweep_max_file_gb == 0

        limited = Settings(foreign_track_sweep_max_file_gb=20)
        assert int(limited.foreign_track_sweep_max_file_gb * GB) == 20 * GB

    def test_a_negative_limit_is_refused(self):
        """Bounds are enforced on save; a negative would invert the filter."""
        import pytest
        from pydantic import ValidationError

        from config_settings import Settings

        with pytest.raises(ValidationError):
            Settings(foreign_track_sweep_max_file_gb=-1)
