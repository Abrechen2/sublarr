"""Tests for the hardlink-aware remux policy (issue #160).

Most *arr setups hardlink the library to the download folder; every
container rewrite (temp + atomic replace) silently breaks that link. The
``remux_hardlink_policy`` setting gates all container rewrites centrally:
skip (default) | warn (proceed + auditable log) | allow (old behaviour).
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest


def _settings(policy: str):
    s = MagicMock()
    s.remux_hardlink_policy = policy
    s.remux_use_reflink = False
    s.remux_trash_dir = ".sublarr"
    return s


@pytest.fixture
def hardlinked_video(tmp_path):
    video = tmp_path / "ep.mkv"
    video.write_bytes(b"fake video")
    link = tmp_path / "seed.mkv"
    os.link(video, link)
    assert os.stat(video).st_nlink == 2
    return video


@pytest.fixture
def plain_video(tmp_path):
    video = tmp_path / "ep.mkv"
    video.write_bytes(b"fake video")
    return video


class TestCheckHardlinkPolicy:
    def test_skip_refuses_hardlinked_file(self, hardlinked_video):
        from remux import check_hardlink_policy

        with patch("config.get_settings", return_value=_settings("skip")):
            assert check_hardlink_policy(str(hardlinked_video)) is False

    def test_warn_proceeds_on_hardlinked_file(self, hardlinked_video, caplog):
        import logging

        from remux import check_hardlink_policy

        with (
            caplog.at_level(logging.WARNING, logger="remux"),
            patch("config.get_settings", return_value=_settings("warn")),
        ):
            assert check_hardlink_policy(str(hardlinked_video)) is True
        assert any("hardlink" in r.message.lower() for r in caplog.records)

    def test_allow_proceeds_silently(self, hardlinked_video):
        from remux import check_hardlink_policy

        with patch("config.get_settings", return_value=_settings("allow")):
            assert check_hardlink_policy(str(hardlinked_video)) is True

    def test_unlinked_file_always_proceeds(self, plain_video):
        from remux import check_hardlink_policy

        for policy in ("skip", "warn", "allow"):
            with patch("config.get_settings", return_value=_settings(policy)):
                assert check_hardlink_policy(str(plain_video)) is True

    def test_missing_file_does_not_block(self, tmp_path):
        from remux import check_hardlink_policy

        with patch("config.get_settings", return_value=_settings("skip")):
            assert check_hardlink_policy(str(tmp_path / "gone.mkv")) is True

    def test_settings_failure_defaults_to_skip(self, hardlinked_video):
        from remux import check_hardlink_policy

        with patch("config.get_settings", side_effect=RuntimeError("no settings")):
            assert check_hardlink_policy(str(hardlinked_video)) is False


class TestRemoveSubtitleStreamsHardlinkGate:
    def test_skip_policy_returns_none_and_leaves_file_untouched(self, hardlinked_video):
        import remux as remux_mod

        original = hardlinked_video.read_bytes()

        with (
            patch("config.get_settings", return_value=_settings("skip")),
            patch("remux._remux_mkvmerge") as mock_mkv,
            patch("remux._remux_ffmpeg") as mock_ff,
        ):
            result = remux_mod.remove_subtitle_streams(
                video_path=str(hardlinked_video),
                streams=[(2, 0)],
            )

        assert result is None
        mock_mkv.assert_not_called()
        mock_ff.assert_not_called()
        assert hardlinked_video.read_bytes() == original
        assert os.stat(hardlinked_video).st_nlink == 2, "hardlink must survive"

    def test_allow_policy_rewrites(self, hardlinked_video):
        import remux as remux_mod

        def _fake_remux(video_path, indices, out):
            with open(out, "wb") as fh:
                fh.write(b"remuxed")

        with (
            patch("config.get_settings", return_value=_settings("allow")),
            patch("remux._detect_backend", return_value="mkvmerge"),
            patch("remux._which", return_value=True),
            patch("remux._remux_mkvmerge", side_effect=_fake_remux),
            patch("remux._verify"),
            patch("remux._make_backup", return_value="/bak") as mock_bak,
        ):
            result = remux_mod.remove_subtitle_streams(
                video_path=str(hardlinked_video),
                streams=[(2, 0)],
            )

        assert result == "/bak"
        mock_bak.assert_called_once()

    def test_foreign_streams_skips_before_probe(self, hardlinked_video):
        import remux as remux_mod

        with (
            patch("config.get_settings", return_value=_settings("skip")),
            patch("remux.get_media_streams") as mock_probe,
        ):
            result = remux_mod.remove_foreign_subtitle_streams(
                video_path=str(hardlinked_video),
                target_languages={"de", "deu", "ger"},
            )

        assert result is None
        mock_probe.assert_not_called()

    def test_by_index_skips(self, hardlinked_video):
        import remux as remux_mod

        with (
            patch("config.get_settings", return_value=_settings("skip")),
            patch("remux.get_media_streams") as mock_probe,
        ):
            result = remux_mod.remove_subtitle_streams_by_index(
                video_path=str(hardlinked_video),
                drop_indices=[0],
            )

        assert result is None
        mock_probe.assert_not_called()
