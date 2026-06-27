"""Tests for remove_subtitle_streams_by_index.

Real helper names discovered in remux/__init__.py:
- get_media_streams(video_path) -> dict  (probe; monkeypatchable re-export)
- _make_backup(video_path, use_reflink, trash_dir) -> str
- _remux_mkvmerge(video_path, stream_indices, output_path) -> None  (raises RemuxError on fail)
- _verify(original_path, remuxed_path, n_removed) -> None

Public input contract: drop_indices are SUBTITLE-RELATIVE (0-based among subtitle
streams, == sub_index). The function maps them internally to GLOBAL ffprobe track
IDs because _remux_mkvmerge expects global IDs.
"""

from __future__ import annotations

from unittest.mock import patch


def _probe(streams):
    return {"streams": streams}


def test_empty_indices_is_noop():
    from remux import remove_subtitle_streams_by_index

    assert remove_subtitle_streams_by_index("/x/y.mkv", []) is None


def test_maps_subtitle_relative_index_to_global_track_id(tmp_path):
    """Subtitle-relative drop_indices must be mapped to GLOBAL ffprobe track IDs.

    Container layout: video idx0, audio idx1, sub idx2 (sub_rel 0), sub idx3 (sub_rel 1).
    Dropping subtitle-relative [1] must hand mkvmerge global track ID [3], NOT [1].
    """
    from remux import remove_subtitle_streams_by_index

    video = tmp_path / "ep.mkv"
    video.write_bytes(b"fake")

    probe = _probe(
        [
            {"index": 0, "codec_type": "video"},
            {"index": 1, "codec_type": "audio"},
            {"index": 2, "codec_type": "subtitle"},
            {"index": 3, "codec_type": "subtitle"},
        ]
    )

    with (
        patch("remux.get_media_streams", return_value=probe),
        patch("remux._make_backup", return_value=str(tmp_path / "ep.mkv.bak")) as mk,
        patch("remux._remux_mkvmerge") as run,
        patch("remux._verify"),
    ):
        backup = remove_subtitle_streams_by_index(str(video), [1])

    assert backup == str(tmp_path / "ep.mkv.bak")
    mk.assert_called_once()
    run.assert_called_once()

    # Second positional arg to _remux_mkvmerge is the GLOBAL stream_indices.
    # _remux_mkvmerge internally builds "!3" for --subtitle-tracks.
    stream_indices = run.call_args[0][1]
    assert stream_indices == [3]


def test_builds_mkvmerge_negative_track_selector(tmp_path):
    """Dropping subtitle-relative indices 0,2 maps to global track IDs [2, 4]."""
    from remux import remove_subtitle_streams_by_index

    video = tmp_path / "ep.mkv"
    video.write_bytes(b"fake")

    probe = _probe(
        [
            {"index": 0, "codec_type": "video"},
            {"index": 1, "codec_type": "audio"},
            {"index": 2, "codec_type": "subtitle"},  # sub_rel 0
            {"index": 3, "codec_type": "subtitle"},  # sub_rel 1
            {"index": 4, "codec_type": "subtitle"},  # sub_rel 2
        ]
    )

    with (
        patch("remux.get_media_streams", return_value=probe),
        patch("remux._make_backup", return_value=str(tmp_path / "ep.mkv.bak")) as mk,
        patch("remux._remux_mkvmerge") as run,
        patch("remux._verify"),
    ):
        backup = remove_subtitle_streams_by_index(str(video), [2, 0])

    assert backup == str(tmp_path / "ep.mkv.bak")
    mk.assert_called_once()
    run.assert_called_once()

    # sub_rel 0 -> global 2, sub_rel 2 -> global 4; sorted -> [2, 4].
    stream_indices = run.call_args[0][1]
    assert stream_indices == [2, 4]


def test_out_of_range_indices_are_skipped_returns_none(tmp_path):
    """If no supplied subtitle-relative index resolves to a sub stream, no-op (None)."""
    from remux import remove_subtitle_streams_by_index

    video = tmp_path / "ep.mkv"
    video.write_bytes(b"fake")

    probe = _probe(
        [
            {"index": 0, "codec_type": "video"},
            {"index": 1, "codec_type": "audio"},
            {"index": 2, "codec_type": "subtitle"},  # only sub_rel 0 exists
        ]
    )

    with (
        patch("remux.get_media_streams", return_value=probe),
        patch("remux._remux_mkvmerge") as run,
        patch("remux._verify"),
    ):
        backup = remove_subtitle_streams_by_index(str(video), [5, 9])

    assert backup is None
    run.assert_not_called()
