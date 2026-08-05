"""Tests for streaming enumeration of sweep candidates."""

import os

from services.foreign_tracks.enumerate import (
    is_remux_temp,
    iter_video_files,
    sweep_stale_temp_files,
)

NOW = 1_000_000.0


def _touch(path, size=10, mtime=NOW - 10_000):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(b"x" * size)
    os.utime(path, (mtime, mtime))


def test_yields_video_files_with_size_and_mtime(tmp_path):
    _touch(str(tmp_path / "Show" / "ep.mkv"), size=42)
    found = list(iter_video_files(str(tmp_path), [], [], min_age_s=0, now=NOW))
    assert len(found) == 1
    path, size, _mtime = found[0]
    assert path.endswith("ep.mkv")
    assert size == 42


def test_non_video_files_are_ignored(tmp_path):
    _touch(str(tmp_path / "Show" / "ep.srt"))
    assert list(iter_video_files(str(tmp_path), [], [], min_age_s=0, now=NOW)) == []


def test_exclude_prunes_the_directory_during_traversal(tmp_path):
    _touch(str(tmp_path / "_SAbnzbd" / "incoming.mkv"))
    _touch(str(tmp_path / "Show" / "ep.mkv"))
    found = list(iter_video_files(str(tmp_path), [], ["_SAbnzbd"], min_age_s=0, now=NOW))
    assert [os.path.basename(p) for p, _, _ in found] == ["ep.mkv"]


def test_include_limits_traversal_to_the_named_subtrees(tmp_path):
    _touch(str(tmp_path / "_Filme" / "movie.mkv"))
    _touch(str(tmp_path / "_Anime" / "ep.mkv"))
    found = list(iter_video_files(str(tmp_path), ["_Filme"], [], min_age_s=0, now=NOW))
    assert [os.path.basename(p) for p, _, _ in found] == ["movie.mkv"]


def test_exclude_beats_include(tmp_path):
    _touch(str(tmp_path / "_Filme" / "staging" / "x.mkv"))
    found = list(
        iter_video_files(str(tmp_path), ["_Filme"], ["_Filme/staging"], min_age_s=0, now=NOW)
    )
    assert found == []


def test_remux_temp_leftovers_are_never_enumerated(tmp_path):
    """A SIGKILL leaves mkstemp's temp file behind carrying the real video
    suffix. Enumerating it would probe and possibly remux a corpse."""
    _touch(str(tmp_path / "Show" / "tmpab12cd.mkv"))
    _touch(str(tmp_path / "Show" / "ep.mkv"))
    found = list(iter_video_files(str(tmp_path), [], [], min_age_s=0, now=NOW))
    assert [os.path.basename(p) for p, _, _ in found] == ["ep.mkv"]


def test_is_remux_temp_recognises_the_mkstemp_pattern():
    assert is_remux_temp("tmpab12cd.mkv") is True
    assert is_remux_temp("tmp.mkv") is True
    assert is_remux_temp("episode.mkv") is False
    assert is_remux_temp("attempting.mkv") is False


def test_files_younger_than_the_minimum_age_are_skipped(tmp_path):
    """An import still being written must not be probed mid-write."""
    _touch(str(tmp_path / "Show" / "fresh.mkv"), mtime=NOW - 60)
    _touch(str(tmp_path / "Show" / "settled.mkv"), mtime=NOW - 10_000)
    found = list(iter_video_files(str(tmp_path), [], [], min_age_s=600, now=NOW))
    assert [os.path.basename(p) for p, _, _ in found] == ["settled.mkv"]


def test_sweep_stale_temp_files_removes_only_old_corpses(tmp_path):
    _touch(str(tmp_path / "Show" / "tmpold.mkv"), mtime=NOW - 200_000)
    _touch(str(tmp_path / "Show" / "tmpfresh.mkv"), mtime=NOW - 60)
    assert sweep_stale_temp_files(str(tmp_path), max_age_s=86_400, now=NOW) == 1
    assert os.path.exists(str(tmp_path / "Show" / "tmpfresh.mkv"))
    assert not os.path.exists(str(tmp_path / "Show" / "tmpold.mkv"))
