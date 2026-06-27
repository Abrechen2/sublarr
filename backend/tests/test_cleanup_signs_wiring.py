"""Tests for signs_cleanup wiring into rules route, runner, and scheduler."""

from unittest.mock import MagicMock, patch


def test_valid_types_includes_signs_cleanup():
    import inspect

    from routes.cleanup import rules

    src = inspect.getsource(rules.create_rule)
    assert "signs_cleanup" in src


def test_execute_rule_dispatches_signs_cleanup():
    from services import cleanup_rule_runner

    rule = {
        "id": 9,
        "rule_type": "signs_cleanup",
        "name": "Signs",
        "config_json": {"strip_embedded": False},
    }
    repo = MagicMock()
    repo.get_rule.return_value = rule
    with (
        patch.object(cleanup_rule_runner, "CleanupRepository", return_value=repo),
        patch(
            "services.cleanup_signs.execute_signs_cleanup",
            return_value={
                "trashed_sidecars": 2,
                "stripped_files": 0,
                "stripped_tracks": 0,
                "bytes_freed": 0,
            },
        ) as ex,
        patch("config.get_settings", return_value=MagicMock(media_path="/media")),
    ):
        out = cleanup_rule_runner.execute_rule(9)
    ex.assert_called_once()
    assert out["status"] in ("ok", "completed")


def test_preview_rule_dispatches_signs_cleanup():
    from services import cleanup_rule_runner

    rule = {"id": 9, "rule_type": "signs_cleanup", "name": "Signs", "config_json": {}}
    repo = MagicMock()
    repo.get_rule.return_value = rule
    with (
        patch.object(cleanup_rule_runner, "CleanupRepository", return_value=repo),
        patch(
            "services.cleanup_signs.execute_signs_cleanup",
            return_value={
                "would_remove_sidecars": 3,
                "would_strip_files": 0,
                "would_strip_tracks": 0,
                "examples": [],
            },
        ) as ex,
        patch("config.get_settings", return_value=MagicMock(media_path="/media")),
    ):
        out = cleanup_rule_runner.preview_rule(9)
    ex.assert_called_once_with("/media", {}, dry_run=True)
    assert out["rule_type"] == "signs_cleanup"
