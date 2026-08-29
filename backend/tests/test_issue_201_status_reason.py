"""#201 (core) — say WHY a provider is unhealthy, machine-readably.

The UI mapped every ``healthy: false`` onto one label, "Unreachable". A
provider that simply has no account configured therefore read as a network
problem, which sends you looking in the wrong place: on the reporting install
`titlovi` displayed "Unreachable" while the real answer was "no credentials
stored".

The backend already distinguishes the cases internally and then flattens them
into a free-text ``message`` the UI cannot branch on. ``status_reason`` carries
the same distinction in a form the frontend can map, and gives #200/#197
something to key off later.
"""

import pytest

from providers.manager_status_mixin import _classify_health, _uninitialized_reason


class TestClassifyHealth:
    def test_a_working_provider(self):
        healthy, _msg, reason = _classify_health(
            auto_disabled=False,
            cb_state="closed",
            consecutive_failures=0,
            total_searches=100,
            results=40,
            downloads=9,
        )
        assert (healthy, reason) == (True, "ok")

    def test_auto_disabled_wins_over_everything(self):
        healthy, _msg, reason = _classify_health(
            auto_disabled=True,
            cb_state="open",
            consecutive_failures=9,
            total_searches=0,
            results=0,
            downloads=0,
        )
        assert (healthy, reason) == (False, "auto_disabled")

    def test_open_circuit(self):
        healthy, _msg, reason = _classify_health(
            auto_disabled=False,
            cb_state="open",
            consecutive_failures=0,
            total_searches=10,
            results=5,
            downloads=1,
        )
        assert (healthy, reason) == (False, "circuit_open")

    def test_consecutive_failures(self):
        healthy, msg, reason = _classify_health(
            auto_disabled=False,
            cb_state="closed",
            consecutive_failures=4,
            total_searches=10,
            results=5,
            downloads=1,
        )
        assert (healthy, reason) == (False, "consecutive_failures")
        assert "4" in msg, "the number belongs in the message the user reads"

    def test_answers_but_never_delivers(self):
        """The #198 verdict must be its own reason, not folded into the
        network-problem bucket."""
        healthy, msg, reason = _classify_health(
            auto_disabled=False,
            cb_state="closed",
            consecutive_failures=0,
            total_searches=1666,
            results=0,
            downloads=0,
        )
        assert (healthy, reason) == (False, "no_results")
        assert "1666" in msg

    def test_never_delivering_does_not_outrank_a_real_failure(self):
        _healthy, _msg, reason = _classify_health(
            auto_disabled=False,
            cb_state="closed",
            consecutive_failures=5,
            total_searches=1666,
            results=0,
            downloads=0,
        )
        assert reason == "consecutive_failures"


class _Settings:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


class TestUninitializedReason:
    def test_a_required_field_left_empty_is_not_a_network_problem(self):
        fields = [
            {"key": "titlovi_username", "required": True},
            {"key": "titlovi_password", "required": True},
        ]
        msg, reason = _uninitialized_reason(
            fields, _Settings(titlovi_username="", titlovi_password="")
        )
        assert reason == "no_credentials"
        assert "credential" in msg.lower()

    def test_partially_filled_still_counts_as_missing(self):
        fields = [
            {"key": "titlovi_username", "required": True},
            {"key": "titlovi_password", "required": True},
        ]
        msg, reason = _uninitialized_reason(
            fields, _Settings(titlovi_username="dennis", titlovi_password="")
        )
        assert reason == "no_credentials"
        assert msg

    def test_optional_fields_do_not_trigger_it(self):
        fields = [{"key": "some_option", "required": False}]
        _msg, reason = _uninitialized_reason(fields, _Settings(some_option=""))
        assert reason == "not_initialized"

    def test_all_credentials_present_means_something_else_went_wrong(self):
        fields = [{"key": "jimaku_api_key", "required": True}]
        _msg, reason = _uninitialized_reason(fields, _Settings(jimaku_api_key="abc"))
        assert reason == "not_initialized"

    def test_no_config_fields_at_all(self):
        _msg, reason = _uninitialized_reason([], _Settings())
        assert reason == "not_initialized"


class TestPayloadCarriesTheReason:
    """A pure function nobody reads is worth nothing — the status payload has
    to actually carry the field."""

    def test_status_dict_includes_status_reason(self, app_ctx, monkeypatch):
        from providers import ProviderManager

        manager = ProviderManager()
        statuses = manager.get_provider_status()
        assert statuses, "no providers registered"
        for s in statuses:
            assert "status_reason" in s, f"{s['name']} has no status_reason"

    @pytest.mark.parametrize(
        "reason",
        ["ok", "auto_disabled", "circuit_open", "consecutive_failures", "no_results",
         "no_credentials", "not_initialized"],
    )
    def test_every_reason_is_declared_for_the_frontend(self, reason):
        """Guards the trap that has cost us twice: a new backend enum value
        with no frontend counterpart renders as a blank or a wrong label."""
        from providers.manager_status_mixin import STATUS_REASONS

        assert reason in STATUS_REASONS
