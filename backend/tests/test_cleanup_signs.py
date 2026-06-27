"""Tests for services.cleanup_signs — sidecar signs removal executor."""

from unittest.mock import MagicMock, patch


def _settings(media):
    s = MagicMock()
    s.cleanup_signs_removal_level = "signs_forced"
    s.media_path = str(media)
    return s


def test_off_level_removes_nothing(tmp_path):
    from services.cleanup_signs import execute_signs_cleanup

    (tmp_path / "Show.en.signs.ass").write_text("signs", encoding="utf-8")
    s = _settings(tmp_path)
    s.cleanup_signs_removal_level = "off"
    with patch("config.get_settings", return_value=s):
        result = execute_signs_cleanup(str(tmp_path), {"permanent_delete": True}, dry_run=False)
    assert result["trashed_sidecars"] == 0
    assert (tmp_path / "Show.en.signs.ass").exists()


def test_trashes_signs_sidecar(tmp_path):
    from services.cleanup_signs import execute_signs_cleanup

    (tmp_path / "Show.en.signs.ass").write_text("signs", encoding="utf-8")
    (tmp_path / "Show.en.ass").write_text("full dialogue", encoding="utf-8")
    with patch("config.get_settings", return_value=_settings(tmp_path)):
        result = execute_signs_cleanup(
            str(tmp_path), {"permanent_delete": True, "strip_embedded": False}, dry_run=False
        )
    assert result["trashed_sidecars"] == 1
    assert not (tmp_path / "Show.en.signs.ass").exists()
    assert (tmp_path / "Show.en.ass").exists()  # full track untouched


def test_last_sub_guard_keeps_only_track(tmp_path):
    """A signs sidecar that is the ONLY sub for the episode+lang is kept."""
    from services.cleanup_signs import execute_signs_cleanup

    (tmp_path / "Show.en.signs.ass").write_text("signs", encoding="utf-8")
    cfg = {"permanent_delete": True, "strip_embedded": False, "keep_languages": ["en"]}
    with patch("config.get_settings", return_value=_settings(tmp_path)):
        result = execute_signs_cleanup(str(tmp_path), cfg, dry_run=False)
    assert result["trashed_sidecars"] == 0
    assert (tmp_path / "Show.en.signs.ass").exists()


def test_dry_run_changes_nothing(tmp_path):
    from services.cleanup_signs import execute_signs_cleanup

    (tmp_path / "Show.en.signs.ass").write_text("signs", encoding="utf-8")
    (tmp_path / "Show.en.ass").write_text("full", encoding="utf-8")
    with patch("config.get_settings", return_value=_settings(tmp_path)):
        result = execute_signs_cleanup(str(tmp_path), {"strip_embedded": False}, dry_run=True)
    assert result["would_remove_sidecars"] == 1
    assert (tmp_path / "Show.en.signs.ass").exists()


def test_aborts_on_unreachable_media():
    from services.cleanup_signs import execute_signs_cleanup

    with patch("config.get_settings") as gs:
        gs.return_value.cleanup_signs_removal_level = "signs"
        result = execute_signs_cleanup("/nonexistent/xyz", {}, dry_run=False)
    assert result.get("aborted")
