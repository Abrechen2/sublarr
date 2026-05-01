"""Tests for the ``old_subtitle_baks`` rule_type dispatch.

The actual cleanup logic lives in ``services.subtitle_backups`` and has its
own thorough test suite. These tests pin the integration: a rule with
rule_type=old_subtitle_baks must (a) reach cleanup_subtitle_baks, (b) update
the rule's last_run timestamp, and (c) log a CleanupHistory row with the
right action_type and files_deleted count — both via the on-demand
``execute_rule`` path AND the scheduled ``_execute_cleanup`` tick.
"""

from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# execute_rule (on-demand "Run now" path)
# ---------------------------------------------------------------------------


class TestExecuteRuleOldSubtitleBaks:
    def test_dispatches_to_cleanup_subtitle_baks(self, app_ctx):
        """Rule with type=old_subtitle_baks must reach the service helper."""
        from db.repositories.cleanup import CleanupRepository
        from services.cleanup_rule_runner import execute_rule

        repo = CleanupRepository()
        rule = repo.create_rule(
            name="Subtitle bak cleanup",
            rule_type="old_subtitle_baks",
            config_json='{"retention_days": 30}',
            enabled=True,
            schedule="weekly",
        )

        fake_result = {
            "deleted": ["/media/Show/ep.en.bak.srt", "/media/Show/ep2.de.bak.srt"],
            "orphans_purged": 1,
            "skipped": 0,
            "errors": [],
        }
        with patch(
            "services.subtitle_backups.cleanup_subtitle_baks",
            return_value=fake_result,
        ) as mock_cleanup:
            result = execute_rule(rule["id"])

        assert mock_cleanup.called, "cleanup_subtitle_baks must be invoked"
        assert result["status"] == "completed"
        assert result["rule"] == "Subtitle bak cleanup"
        assert result["deleted"] == 2
        assert result["orphans_purged"] == 1
        assert result["bytes_freed"] == 0

    def test_logs_cleanup_history(self, app_ctx):
        """A history row with action_type=old_subtitle_baks must be written."""
        from db.repositories.cleanup import CleanupRepository
        from services.cleanup_rule_runner import execute_rule

        repo = CleanupRepository()
        rule = repo.create_rule(
            name="bak cleanup",
            rule_type="old_subtitle_baks",
            config_json="{}",
        )

        fake_result = {"deleted": ["/x.bak.srt"], "orphans_purged": 0}
        with patch(
            "services.subtitle_backups.cleanup_subtitle_baks",
            return_value=fake_result,
        ):
            execute_rule(rule["id"])

        history = repo.get_history(per_page=10)["items"]
        bak_rows = [h for h in history if h["action_type"] == "old_subtitle_baks"]
        assert len(bak_rows) == 1
        assert bak_rows[0]["files_deleted"] == 1
        assert bak_rows[0]["rule_id"] == rule["id"]

    def test_updates_rule_last_run(self, app_ctx):
        """The rule's last_run must be updated after a successful execute."""
        from db.repositories.cleanup import CleanupRepository
        from services.cleanup_rule_runner import execute_rule

        repo = CleanupRepository()
        rule = repo.create_rule(
            name="bak cleanup",
            rule_type="old_subtitle_baks",
            config_json="{}",
        )
        assert rule.get("last_run_at") in (None, "")  # fresh rule has no last_run_at

        with patch(
            "services.subtitle_backups.cleanup_subtitle_baks",
            return_value={"deleted": [], "orphans_purged": 0},
        ):
            execute_rule(rule["id"])

        refreshed = repo.get_rule(rule["id"])
        assert refreshed["last_run_at"], "last_run_at must be set after execute"

    def test_passes_retention_days_from_config(self, app_ctx):
        """``config.retention_days`` must override the settings default."""
        from db.repositories.cleanup import CleanupRepository
        from services.cleanup_rule_runner import execute_rule

        repo = CleanupRepository()
        rule = repo.create_rule(
            name="bak cleanup",
            rule_type="old_subtitle_baks",
            config_json='{"retention_days": 7}',
        )

        with patch(
            "services.subtitle_backups.cleanup_subtitle_baks",
            return_value={"deleted": [], "orphans_purged": 0},
        ) as mock_cleanup:
            execute_rule(rule["id"])

        # The helper signature is cleanup_subtitle_baks(media_roots, *, older_than_days=..., orphans_only=...)
        kwargs = mock_cleanup.call_args.kwargs
        assert kwargs.get("older_than_days") == 7
        assert kwargs.get("orphans_only") is False

    def test_falls_back_to_settings_default(self, app_ctx):
        """When config.retention_days is missing, settings default is used."""
        from db.repositories.cleanup import CleanupRepository
        from services.cleanup_rule_runner import execute_rule

        repo = CleanupRepository()
        rule = repo.create_rule(
            name="bak cleanup",
            rule_type="old_subtitle_baks",
            config_json="{}",  # no retention override
        )

        # Patch settings to expose a known default
        from unittest.mock import MagicMock

        fake_settings = MagicMock()
        fake_settings.subtitle_bak_retention_days = 45
        fake_settings.media_path = ""
        fake_settings.extra_media_paths = ""

        with (
            patch("config.get_settings", return_value=fake_settings),
            patch(
                "services.subtitle_backups.cleanup_subtitle_baks",
                return_value={"deleted": [], "orphans_purged": 0},
            ) as mock_cleanup,
        ):
            execute_rule(rule["id"])

        kwargs = mock_cleanup.call_args.kwargs
        assert kwargs.get("older_than_days") == 45


# ---------------------------------------------------------------------------
# _execute_cleanup (scheduled tick)
# ---------------------------------------------------------------------------


class TestScheduledExecutionOldSubtitleBaks:
    def test_scheduled_run_invokes_cleanup_and_logs(self, app_ctx):
        """The scheduler tick path must also dispatch old_subtitle_baks."""
        from cleanup_scheduler import _execute_cleanup
        from db.repositories.cleanup import CleanupRepository

        repo = CleanupRepository()
        rule = repo.create_rule(
            name="weekly bak",
            rule_type="old_subtitle_baks",
            config_json="{}",
            enabled=True,
            schedule="weekly",  # must be in {daily, weekly, after_scan}
        )

        fake_result = {
            "deleted": ["/media/x.en.bak.srt", "/media/y.de.bak.srt"],
            "orphans_purged": 1,
        }
        with patch(
            "services.subtitle_backups.cleanup_subtitle_baks",
            return_value=fake_result,
        ) as mock_cleanup:
            _execute_cleanup()

        assert mock_cleanup.called

        history = repo.get_history(per_page=10)["items"]
        scheduled_rows = [
            h for h in history if h["action_type"] == "scheduled_subtitle_bak_cleanup"
        ]
        assert len(scheduled_rows) == 1
        assert scheduled_rows[0]["files_deleted"] == 2
        assert scheduled_rows[0]["rule_id"] == rule["id"]

    def test_disabled_rule_is_skipped(self, app_ctx):
        """Disabled or manual-only rules must not run via the scheduler tick."""
        from cleanup_scheduler import _execute_cleanup
        from db.repositories.cleanup import CleanupRepository

        repo = CleanupRepository()
        repo.create_rule(
            name="manual bak",
            rule_type="old_subtitle_baks",
            config_json="{}",
            enabled=True,
            schedule="manual",  # not in {daily, weekly, after_scan}
        )
        repo.create_rule(
            name="disabled bak",
            rule_type="old_subtitle_baks",
            config_json="{}",
            enabled=False,
            schedule="weekly",
        )

        with patch(
            "services.subtitle_backups.cleanup_subtitle_baks",
            return_value={"deleted": [], "orphans_purged": 0},
        ) as mock_cleanup:
            _execute_cleanup()

        assert not mock_cleanup.called, (
            "Disabled / manual rules must never reach cleanup_subtitle_baks"
        )
