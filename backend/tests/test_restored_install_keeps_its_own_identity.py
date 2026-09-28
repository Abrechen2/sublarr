"""A restored archive must not hand its anonymous install id to the new machine.

The id lives in ``config_entries``, so it travels inside every database backup.
Restore that archive onto a second instance — a test copy, a staging mirror, a
migration to new hardware kept alongside the old one — and both ping the
aggregate under one id. They overwrite each other: the aggregate counts one
install where there are two, and whichever pinged last defines what that
install looks like.

Measured on this project's own data, 2026-09-28. Prod and its RC mirror both
held ``b9549623ec6e4a2987c924ac0b63a7fd`` and pinged two minutes apart, so the
single "postgres" install in the public aggregate was describing the idle
mirror. Every percentage computed from 108 installs was therefore computed from
a number that is too low, by an unknown amount, in a way nothing in the data
reveals.

Consent is deliberately NOT reset: that is the operator's answer, and it does
not become untrue because the database moved.
"""

from unittest.mock import patch


class TestTheIdIsRetiredOnRestore:
    def test_refresh_after_restore_blanks_the_id(self):
        from services import database_restore

        saved = {}

        with (
            patch("db.config.save_config_entry", side_effect=lambda k, v: saved.update({k: v})),
            patch("db.config.get_all_config_entries", return_value={}),
            patch("config.reload_settings"),
            patch("cache_response.invalidate_response_cache"),
        ):
            database_restore.refresh_after_restore()

        assert saved.get("usage_stats_install_id") == "", (
            f"the restored id was kept — saved: {saved}"
        )

    def test_consent_is_left_alone(self):
        """Resetting the answer to a privacy question would be its own bug."""
        from services import database_restore

        saved = {}

        with (
            patch("db.config.save_config_entry", side_effect=lambda k, v: saved.update({k: v})),
            patch("db.config.get_all_config_entries", return_value={}),
            patch("config.reload_settings"),
            patch("cache_response.invalidate_response_cache"),
        ):
            database_restore.refresh_after_restore()

        assert "usage_stats_consent" not in saved

    def test_a_failure_here_cannot_fail_the_restore(self):
        """Telemetry is best-effort; a restore that worked must report success."""
        from services import database_restore

        with (
            patch("db.config.save_config_entry", side_effect=RuntimeError("no db")),
            patch("db.config.get_all_config_entries", return_value={}),
            patch("config.reload_settings"),
            patch("cache_response.invalidate_response_cache"),
        ):
            database_restore.refresh_after_restore()  # must not raise


class TestABlankedIdMintsANewOne:
    def test_empty_string_is_treated_as_absent(self):
        """The blanking relies on this: "" has to be falsy to the getter, or the
        restored instance would keep reporting under an empty id."""
        from services.usage_stats import get_or_create_install_id

        saved = {}

        with (
            patch("db.config.get_config_entry", return_value=""),
            patch("db.config.save_config_entry", side_effect=lambda k, v: saved.update({k: v})),
        ):
            new_id = get_or_create_install_id()

        assert new_id and new_id != ""
        assert len(new_id) == 32, f"expected a uuid4 hex, got {new_id!r}"
        assert saved.get("usage_stats_install_id") == new_id

    def test_two_restores_do_not_collide(self):
        """Two machines restored from the same archive must diverge."""
        from services.usage_stats import get_or_create_install_id

        ids = []
        for _ in range(2):
            with (
                patch("db.config.get_config_entry", return_value=""),
                patch("db.config.save_config_entry"),
            ):
                ids.append(get_or_create_install_id())

        assert ids[0] != ids[1]
