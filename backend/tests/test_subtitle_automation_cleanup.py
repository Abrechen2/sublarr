"""Foreign-track cleanup tests (Phase 6).

Covers:
- `remux.remove_foreign_subtitle_streams`: identifies non-target-language
  subtitle streams in the container and remuxes them out using the
  existing `remove_subtitle_streams` helper (backup-to-trash preserved).
- Policy resolver `should_cleanup_foreign_tracks`: per-series override
  (NULL → inherit) + global default.
"""

from unittest.mock import patch

from config_settings import Settings


class TestShouldCleanupForeignTracks:
    from services.foreign_track_cleanup import should_cleanup_foreign_tracks

    def test_override_true_wins_over_global_false(self):
        from services.foreign_track_cleanup import should_cleanup_foreign_tracks

        assert should_cleanup_foreign_tracks(series_override=True, global_default=False) is True

    def test_override_false_wins_over_global_true(self):
        from services.foreign_track_cleanup import should_cleanup_foreign_tracks

        assert should_cleanup_foreign_tracks(series_override=False, global_default=True) is False

    def test_override_none_falls_through_to_global_true(self):
        from services.foreign_track_cleanup import should_cleanup_foreign_tracks

        assert should_cleanup_foreign_tracks(series_override=None, global_default=True) is True

    def test_override_none_falls_through_to_global_false(self):
        from services.foreign_track_cleanup import should_cleanup_foreign_tracks

        assert should_cleanup_foreign_tracks(series_override=None, global_default=False) is False


class TestForeignTrackRemoval:
    """`remove_foreign_subtitle_streams`: identify non-target streams and
    remux them out, preserving target + audio + video."""

    def _probe_with_many_langs(self):
        return {
            "streams": [
                {"codec_type": "video", "index": 0},
                {"codec_type": "audio", "index": 1, "tags": {"language": "ger"}},
                {"codec_type": "audio", "index": 2, "tags": {"language": "eng"}},
                {
                    "codec_type": "subtitle",
                    "codec_name": "subrip",
                    "index": 3,
                    "tags": {"language": "ger"},
                },
                {
                    "codec_type": "subtitle",
                    "codec_name": "subrip",
                    "index": 4,
                    "tags": {"language": "eng"},
                },
                {
                    "codec_type": "subtitle",
                    "codec_name": "subrip",
                    "index": 5,
                    "tags": {"language": "fre"},
                },
                {
                    "codec_type": "subtitle",
                    "codec_name": "subrip",
                    "index": 6,
                    "tags": {"language": "jpn"},
                },
                {
                    "codec_type": "subtitle",
                    "codec_name": "subrip",
                    "index": 7,
                    "tags": {"language": "und"},
                },
            ]
        }

    def test_removes_only_non_target_subtitle_streams(self):
        from remux import remove_foreign_subtitle_streams

        probe = self._probe_with_many_langs()
        with (
            patch("remux.get_media_streams", return_value=probe),
            patch("remux.remove_subtitle_streams") as remove_mock,
        ):
            result = remove_foreign_subtitle_streams(
                video_path="/media/foo.mkv",
                target_languages={"ger", "eng"},
                keep_und=False,
            )
        # Called once with the 3 foreign streams (fre, jpn, und).
        remove_mock.assert_called_once()
        args, kwargs = remove_mock.call_args
        streams = kwargs.get("streams") or (args[1] if len(args) > 1 else None)
        # streams is list[(global_idx, sub_only_idx)]
        removed_global = sorted(s[0] for s in streams)
        assert removed_global == [5, 6, 7]
        assert result is not None

    def test_keep_und_keeps_undetermined_tracks(self):
        from remux import remove_foreign_subtitle_streams

        probe = self._probe_with_many_langs()
        with (
            patch("remux.get_media_streams", return_value=probe),
            patch("remux.remove_subtitle_streams") as remove_mock,
        ):
            remove_foreign_subtitle_streams(
                video_path="/media/foo.mkv",
                target_languages={"ger", "eng"},
                keep_und=True,
            )
        _, kwargs = remove_mock.call_args
        streams = kwargs.get("streams") or remove_mock.call_args.args[1]
        removed_global = sorted(s[0] for s in streams)
        # und (7) stays; only fre (5) + jpn (6) removed.
        assert removed_global == [5, 6]

    def test_no_foreign_tracks_returns_none_without_remux_call(self):
        """Don't touch the file if there's nothing to remove — avoids
        pointless backups when container is already clean."""
        from remux import remove_foreign_subtitle_streams

        probe = {
            "streams": [
                {"codec_type": "video", "index": 0},
                {"codec_type": "audio", "index": 1, "tags": {"language": "ger"}},
                {
                    "codec_type": "subtitle",
                    "codec_name": "subrip",
                    "index": 2,
                    "tags": {"language": "ger"},
                },
                {
                    "codec_type": "subtitle",
                    "codec_name": "subrip",
                    "index": 3,
                    "tags": {"language": "eng"},
                },
            ]
        }
        with (
            patch("remux.get_media_streams", return_value=probe),
            patch("remux.remove_subtitle_streams") as remove_mock,
        ):
            result = remove_foreign_subtitle_streams(
                video_path="/media/foo.mkv",
                target_languages={"ger", "eng"},
                keep_und=False,
            )
        remove_mock.assert_not_called()
        assert result is None

    def test_empty_target_set_is_noop(self):
        """Defensive: no target languages → never strip everything.
        Return None without calling remux."""
        from remux import remove_foreign_subtitle_streams

        probe = {
            "streams": [
                {
                    "codec_type": "subtitle",
                    "codec_name": "subrip",
                    "index": 2,
                    "tags": {"language": "ger"},
                }
            ]
        }
        with (
            patch("remux.get_media_streams", return_value=probe),
            patch("remux.remove_subtitle_streams") as remove_mock,
        ):
            result = remove_foreign_subtitle_streams(
                video_path="/media/foo.mkv",
                target_languages=set(),
                keep_und=False,
            )
        remove_mock.assert_not_called()
        assert result is None

    def test_ignores_non_subtitle_streams(self):
        """Audio/video streams must never appear in the removal list."""
        from remux import remove_foreign_subtitle_streams

        probe = self._probe_with_many_langs()
        with (
            patch("remux.get_media_streams", return_value=probe),
            patch("remux.remove_subtitle_streams") as remove_mock,
        ):
            remove_foreign_subtitle_streams(
                video_path="/media/foo.mkv",
                target_languages={"ger", "eng"},
                keep_und=False,
            )
        _, kwargs = remove_mock.call_args
        streams = kwargs.get("streams") or remove_mock.call_args.args[1]
        removed_global = {s[0] for s in streams}
        # No audio (1, 2) or video (0) in the removal list.
        assert 0 not in removed_global
        assert 1 not in removed_global
        assert 2 not in removed_global
