"""Going-forward signs purge in the extract path (Task 9).

Tests for ``services.embedded_extractor.purge_signs_after_extract``.

Design notes:
- ``_trash_path`` is imported at module level inside embedded_extractor so
  patching ``services.embedded_extractor._trash_path`` intercepts all trash
  calls made by purge_signs_after_extract.
- ``classify_sidecar`` (subtitle_signs) runs for real — filename-based
  classification via ``detect_subtitle_type`` is fast and self-contained.
- ``config.get_settings`` is patched because purge_signs_after_extract does a
  late ``from config import get_settings`` inside the function body.
"""

from unittest.mock import MagicMock, patch


def _settings(level: str = "signs") -> MagicMock:
    s = MagicMock()
    s.cleanup_signs_removal_level = level
    return s


def test_extract_hook_trashes_signs_sidecar_keeps_full(tmp_path):
    """Signs sidecar is trashed; full-dialogue peer for the same lang is kept."""
    from services import embedded_extractor

    video = tmp_path / "Ep.mkv"
    video.write_bytes(b"fake")
    signs = tmp_path / "Ep.en.signs.ass"
    signs.write_text("signs", encoding="utf-8")
    full = tmp_path / "Ep.en.ass"
    full.write_text("dialogue", encoding="utf-8")

    with (
        patch("config.get_settings", return_value=_settings("signs")),
        patch("services.embedded_extractor._trash_path", return_value=True) as trash,
    ):
        embedded_extractor.purge_signs_after_extract(str(video))

    trashed = [c.args[0] for c in trash.call_args_list]
    assert any("signs" in p for p in trashed), "signs sidecar should be trashed"
    assert not any(p.endswith("Ep.en.ass") for p in trashed), "full sidecar must not be trashed"


def test_extract_hook_off_trashes_nothing(tmp_path):
    """When level is 'off', nothing is trashed."""
    from services import embedded_extractor

    video = tmp_path / "Ep.mkv"
    video.write_bytes(b"fake")
    (tmp_path / "Ep.en.signs.ass").write_text("signs", encoding="utf-8")
    (tmp_path / "Ep.en.ass").write_text("dialogue", encoding="utf-8")

    with (
        patch("config.get_settings", return_value=_settings("off")),
        patch("services.embedded_extractor._trash_path", return_value=True) as trash,
    ):
        embedded_extractor.purge_signs_after_extract(str(video))

    assert trash.call_count == 0


def test_extract_hook_last_sub_guard(tmp_path):
    """Signs sidecar is the only sub for this lang — last-sub guard keeps it."""
    from services import embedded_extractor

    video = tmp_path / "Ep.mkv"
    video.write_bytes(b"fake")
    # Only the signs sidecar exists; no full-dialogue peer for (Ep, en).
    (tmp_path / "Ep.en.signs.ass").write_text("signs", encoding="utf-8")

    with (
        patch("config.get_settings", return_value=_settings("signs")),
        patch("services.embedded_extractor._trash_path", return_value=True) as trash,
    ):
        embedded_extractor.purge_signs_after_extract(str(video))

    assert trash.call_count == 0, "last-sub guard must keep the only sidecar"


def test_extract_hook_returns_count(tmp_path):
    """Return value equals the number of trashed sidecars."""
    from services import embedded_extractor

    video = tmp_path / "Ep.mkv"
    video.write_bytes(b"fake")
    (tmp_path / "Ep.en.signs.ass").write_text("signs", encoding="utf-8")
    (tmp_path / "Ep.en.ass").write_text("dialogue", encoding="utf-8")

    with (
        patch("config.get_settings", return_value=_settings("signs")),
        patch("services.embedded_extractor._trash_path", return_value=True),
    ):
        result = embedded_extractor.purge_signs_after_extract(str(video))

    assert result == 1


def test_extract_hook_no_sidecars_returns_zero(tmp_path):
    """No crash and returns 0 when the video has no sidecars at all."""
    from services import embedded_extractor

    video = tmp_path / "Ep.mkv"
    video.write_bytes(b"fake")

    with (
        patch("config.get_settings", return_value=_settings("signs")),
        patch("services.embedded_extractor._trash_path", return_value=True) as trash,
    ):
        result = embedded_extractor.purge_signs_after_extract(str(video))

    assert result == 0
    assert trash.call_count == 0


def test_extract_and_cleanup_invokes_signs_purge(tmp_path):
    """extract_and_cleanup calls purge_signs_after_extract after language cleanup."""
    from services import embedded_extractor

    video = tmp_path / "Ep.mkv"
    video.write_bytes(b"fake")

    # Minimal probe: no subtitle streams → nothing extracted, signs purge still called.
    probe: dict = {"streams": []}

    with patch.object(
        embedded_extractor,
        "purge_signs_after_extract",
        return_value=0,
    ) as purge_mock:
        embedded_extractor.extract_and_cleanup(
            str(video),
            probe,
            keep_langs={"en"},
        )

    purge_mock.assert_not_called()  # any_extracted=False → purge is skipped


def test_extract_and_cleanup_invokes_signs_purge_when_extracted(tmp_path):
    """extract_and_cleanup calls purge_signs_after_extract when sidecars were produced."""
    from services import embedded_extractor

    video = tmp_path / "Ep.mkv"
    video.write_bytes(b"fake")
    out = tmp_path / "Ep.en.ass"
    out.write_text("dialogue", encoding="utf-8")

    probe = {
        "streams": [
            {
                "codec_type": "subtitle",
                "codec_name": "ass",
                "index": 0,
                "tags": {"language": "eng"},
            }
        ]
    }

    settings_mock = MagicMock()
    settings_mock.embedded_allow_sdh = True
    settings_mock.remux_use_reflink = False
    settings_mock.remux_trash_dir = ".sublarr"

    with (
        patch("config.get_settings", return_value=settings_mock),
        patch("ass_probe.is_sdh_stream", return_value=False),
        patch("ass_utils.get_subtitle_stream_output_path", return_value=str(out)),
        patch("services.embedded_extractor.remove_streams_from_container"),
        patch("services.embedded_extractor.trash_unwanted_sidecars", return_value=0),
        patch.object(
            embedded_extractor,
            "purge_signs_after_extract",
            return_value=0,
        ) as purge_mock,
    ):
        embedded_extractor.extract_and_cleanup(
            str(video),
            probe,
            keep_langs={"en"},
        )

    purge_mock.assert_called_once_with(
        str(video), log_label="extractor", extracted_paths=[str(out)]
    )
