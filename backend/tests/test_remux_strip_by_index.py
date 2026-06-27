"""Tests for remove_subtitle_streams_by_index.

Real helper names discovered in remux/__init__.py:
- _make_backup(video_path, use_reflink, trash_dir) -> str
- _remux_mkvmerge(video_path, stream_indices, output_path) -> None  (raises RemuxError on fail)
- _verify(original_path, remuxed_path, n_removed) -> None
"""

from __future__ import annotations

from unittest.mock import patch


def test_empty_indices_is_noop():
    from remux import remove_subtitle_streams_by_index

    assert remove_subtitle_streams_by_index("/x/y.mkv", []) is None


def test_builds_mkvmerge_negative_track_selector(tmp_path):
    """Dropping subtitle indices 1,3 must call _remux_mkvmerge with [1, 3] stream_indices."""
    from remux import remove_subtitle_streams_by_index

    video = tmp_path / "ep.mkv"
    video.write_bytes(b"fake")

    with (
        patch("remux._make_backup", return_value=str(tmp_path / "ep.mkv.bak")) as mk,
        patch("remux._remux_mkvmerge") as run,
        patch("remux._verify"),
    ):
        backup = remove_subtitle_streams_by_index(str(video), [1, 3])

    assert backup == str(tmp_path / "ep.mkv.bak")
    mk.assert_called_once()
    run.assert_called_once()

    # Second positional arg to _remux_mkvmerge is stream_indices — must be sorted [1, 3].
    # _remux_mkvmerge internally builds "!1,3" for --subtitle-tracks.
    stream_indices = run.call_args[0][1]
    assert sorted(stream_indices) == [1, 3]
