"""Tests for the provider-download foreign-track cleanup hook (Feature B).

Covers:
  * ``_video_for_sidecar`` — resolving the companion video from a sidecar.
  * ``maybe_run_foreign_track_cleanup`` — keep-set = target ∪ always-keep,
    expanded to raw ffprobe tags so the target language is never stripped.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def test_video_for_sidecar_resolves_companion(tmp_path):
    from providers.download_manager import _video_for_sidecar

    (tmp_path / "Show - S01E01.mkv").write_bytes(b"v")
    sidecar = str(tmp_path / "Show - S01E01.de.srt")
    assert _video_for_sidecar(sidecar) == str(tmp_path / "Show - S01E01.mkv")


def test_video_for_sidecar_handles_modifier(tmp_path):
    from providers.download_manager import _video_for_sidecar

    (tmp_path / "Ep.mkv").write_bytes(b"v")
    # <base>.<lang>.<modifier>.<ext>
    assert _video_for_sidecar(str(tmp_path / "Ep.en.forced.srt")) == str(tmp_path / "Ep.mkv")


def test_video_for_sidecar_none_when_missing(tmp_path):
    from providers.download_manager import _video_for_sidecar

    assert _video_for_sidecar(str(tmp_path / "NoVideo.de.srt")) is None


def test_cleanup_keeps_target_plus_always_keep(tmp_path):
    """target_language='de' + always_keep=['de','en'] must keep ger+eng tags."""
    from services import foreign_track_cleanup as ftc

    video = str(tmp_path / "Ep.mkv")
    (tmp_path / "Ep.mkv").write_bytes(b"v")

    fake_settings = SimpleNamespace(
        cleanup_foreign_tracks_default=True,
        cleanup_foreign_tracks_keep_und=True,
        cleanup_foreign_tracks_keep_languages=["de", "en"],
    )
    strip = MagicMock(return_value=None)
    with (
        patch("config.get_settings", return_value=fake_settings),
        patch("remux.remove_foreign_subtitle_streams", strip),
    ):
        ftc.maybe_run_foreign_track_cleanup({"target_language": "de"}, video)

    strip.assert_called_once()
    kept = strip.call_args.kwargs["target_languages"]
    assert {"ger", "deu", "eng", "en", "de"}.issubset(kept)
    assert strip.call_args.kwargs["keep_und"] is True


def test_cleanup_skipped_when_disabled(tmp_path):
    """Global default off and no series override → strip never called."""
    from services import foreign_track_cleanup as ftc

    fake_settings = SimpleNamespace(
        cleanup_foreign_tracks_default=False,
        cleanup_foreign_tracks_keep_und=True,
        cleanup_foreign_tracks_keep_languages=["de", "en"],
    )
    strip = MagicMock()
    with (
        patch("config.get_settings", return_value=fake_settings),
        patch("remux.remove_foreign_subtitle_streams", strip),
    ):
        ftc.maybe_run_foreign_track_cleanup({"target_language": "de"}, str(tmp_path / "Ep.mkv"))

    strip.assert_not_called()
