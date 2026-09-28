"""The payload can now say how far an install got, not only that it exists.

The aggregate could always count installs and pings. It could never say
anything about why the rest stopped, because no field distinguishes an install
that never finished setup from one that ran for months and was switched off.

On 2026-09-28 that gap was the whole story: 108 installs, 56 active, cohort
retention down from 33% to 22% in six weeks — and nothing to narrow it with.

Four booleans, in the order an install passes them: wizard, library, scheduler,
first download. A drop-off now lands on one of them. They stay booleans on
purpose — the payload contract is enum/bool/bucket, and "has this ever
happened" answers the question without describing anyone's library.
"""

from unittest.mock import patch

import pytest

from services.usage_stats import _funnel, build_usage_payload

FLAGS = ("setup_completed", "library_scanned", "scheduler_ran", "first_download_done")


class TestTheShapeOfTheGroup:
    def test_every_flag_is_present_and_boolean(self, app_ctx):
        funnel = _funnel()
        assert set(funnel) == set(FLAGS)
        for name, value in funnel.items():
            assert isinstance(value, bool), f"{name} is {type(value).__name__}, not bool"

    def test_it_reaches_the_payload(self, app_ctx):
        payload = build_usage_payload()
        assert "funnel" in payload
        assert set(payload["funnel"]) == set(FLAGS)

    def test_nothing_in_it_describes_the_library(self, app_ctx):
        """No counts, no sizes, no names — the reason it can be a bool group."""
        for value in _funnel().values():
            assert value in (True, False)


class TestAFreshInstallReadsAsFresh:
    def test_an_empty_install_reports_false(self, app_ctx):
        """The case the retention question is actually about."""
        with (
            patch("db.config.get_config_entry", return_value=None),
            patch("services.usage_stats._count_rows", return_value=0),
            patch("db.wanted.get_wanted_count", return_value=0),
        ):
            assert _funnel() == dict.fromkeys(FLAGS, False)

    def test_a_working_install_reports_true(self, app_ctx):
        with (
            patch("db.config.get_config_entry", return_value="true"),
            patch("services.usage_stats._count_rows", return_value=5),
            patch("db.wanted.get_wanted_count", return_value=42),
        ):
            assert _funnel() == dict.fromkeys(FLAGS, True)

    @pytest.mark.parametrize("raw", ["true", "True", "TRUE"])
    def test_the_wizard_flag_is_read_case_insensitively(self, app_ctx, raw):
        with patch("db.config.get_config_entry", return_value=raw):
            assert _funnel()["setup_completed"] is True

    @pytest.mark.parametrize("raw", ["false", "", None, "1", "yes"])
    def test_only_true_means_completed(self, app_ctx, raw):
        """A half-written flag must not read as a finished wizard."""
        with patch("db.config.get_config_entry", return_value=raw):
            assert _funnel()["setup_completed"] is False


class TestItCannotBreakThePing:
    def test_a_broken_query_is_a_false_not_an_exception(self, app_ctx):
        """Telemetry is best-effort: a funnel that cannot be derived must not
        cost the ping the fields that can."""
        with patch("services.usage_stats._count_rows", side_effect=RuntimeError("no table")):
            funnel = _funnel()
        assert funnel["first_download_done"] is False
        assert funnel["scheduler_ran"] is False

    def test_a_broken_funnel_still_leaves_a_payload(self, app_ctx):
        with patch("services.usage_stats._funnel", side_effect=RuntimeError("boom")):
            payload = build_usage_payload()
        assert payload["install_id"]
        assert "version" in payload
