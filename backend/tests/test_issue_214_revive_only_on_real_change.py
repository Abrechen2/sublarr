"""#214 — revive only when a provider really became usable.

The trigger used to fire on the *name* of a saved key: if `providers_enabled`
or any provider credential appeared in the request body, up to
`wanted_revive_max_per_run` exhausted items (default 200) were put back in
rotation. Whether the value had changed never entered into it.

Three consequences the reporter measured against v1.15.0-rc.14:

- Switching a provider **off** counted as one becoming usable. Culling five
  broken providers would revive a batch for which nothing had improved.
- Resending an **unchanged** value counted too, so any form that posts a
  provider key alongside unrelated settings reset part of the backlog.
- The revived items then searched **every** enabled provider, not the one that
  changed — on his install, a SubDL test spent the OpenSubtitles daily
  download quota on items that were never SubDL candidates.

This file covers the trigger (his part 1). Aiming the retry at the provider
that changed (his part 2) is not addressed here: a wanted item does not record
which provider it was waiting for, so that needs a data-model answer first.

Note `providers_enabled` semantics, which is where the old test was wrong:
**empty means every provider is enabled**, so saving one name over an empty
value is a restriction, not an addition.
"""

import pytest

from routes.config.core import _enabled_provider_set, _providers_became_usable


@pytest.fixture
def owners(app_ctx):
    """One real credential key and the provider that declares it."""
    from routes.config.core import _provider_field_owners

    mapping = _provider_field_owners()
    assert mapping, "no provider declares config_fields — the check would be empty"
    key = sorted(mapping)[0]
    return key, mapping[key]


class TestTheEnabledList:
    def test_adding_one_counts(self):
        became = _providers_became_usable(
            {"providers_enabled": "opensubtitles,subdl"},
            {"providers_enabled": "opensubtitles"},
        )
        assert became == {"subdl"}

    def test_removing_one_counts_for_nothing(self):
        """The reporter's case: culling dead providers made nothing usable."""
        became = _providers_became_usable(
            {"providers_enabled": "opensubtitles"},
            {"providers_enabled": "opensubtitles,subdl"},
        )
        assert became == set()

    def test_an_unchanged_list_counts_for_nothing(self):
        became = _providers_became_usable(
            {"providers_enabled": "opensubtitles,subdl"},
            {"providers_enabled": "opensubtitles,subdl"},
        )
        assert became == set()

    def test_reordering_is_not_a_change(self):
        became = _providers_became_usable(
            {"providers_enabled": "subdl,opensubtitles"},
            {"providers_enabled": "opensubtitles,subdl"},
        )
        assert became == set()

    def test_narrowing_from_empty_is_a_restriction_not_an_addition(self, app_ctx):
        """Empty means all. This save turns providers OFF, and used to revive."""
        became = _providers_became_usable(
            {"providers_enabled": "opensubtitles"},
            {"providers_enabled": ""},
        )
        assert became == set()

    def test_widening_to_empty_re_enables_the_rest(self, app_ctx):
        """Clearing the list switches everything back on — that IS an addition."""
        from providers.registry import _PROVIDER_CLASSES

        became = _providers_became_usable(
            {"providers_enabled": ""},
            {"providers_enabled": "opensubtitles"},
        )
        assert became == set(_PROVIDER_CLASSES) - {"opensubtitles"}
        assert became, "no provider came back from clearing the allowlist"

    def test_empty_resolves_to_every_provider(self, app_ctx):
        from providers.registry import _PROVIDER_CLASSES

        assert _enabled_provider_set("", set(_PROVIDER_CLASSES)) == set(_PROVIDER_CLASSES)
        assert _enabled_provider_set("  ", set(_PROVIDER_CLASSES)) == set(_PROVIDER_CLASSES)


class TestCredentials:
    def test_a_new_key_makes_its_provider_usable(self, owners):
        key, provider = owners
        assert _providers_became_usable({key: "fresh-key"}, {key: ""}) == {provider}

    def test_a_replaced_key_counts(self, owners):
        key, provider = owners
        assert _providers_became_usable({key: "new"}, {key: "old"}) == {provider}

    def test_the_same_key_resent_counts_for_nothing(self, owners):
        """Any form that posts this key alongside unrelated settings."""
        key, _provider = owners
        assert _providers_became_usable({key: "same"}, {key: "same"}) == set()

    def test_whitespace_is_not_a_change(self, owners):
        key, _provider = owners
        assert _providers_became_usable({key: " same "}, {key: "same"}) == set()

    def test_clearing_a_key_counts_for_nothing(self, owners):
        """Removing a credential is the opposite of becoming usable."""
        key, _provider = owners
        assert _providers_became_usable({key: ""}, {key: "old"}) == set()

    def test_a_masked_value_counts_for_nothing(self, owners):
        """The mask means "unchanged"; the save loop skips it too."""
        from routes.config.core import _MASK_SENTINEL

        key, _provider = owners
        assert _providers_became_usable({key: _MASK_SENTINEL}, {key: "old"}) == set()

    def test_only_the_provider_that_changed_is_named(self, owners):
        key, provider = owners
        became = _providers_became_usable({key: "new"}, {key: "old"})
        assert became == {provider}, "the revive would aim at providers that did not change"


class TestUnrelatedSaves:
    def test_a_save_with_no_provider_keys_counts_for_nothing(self):
        assert _providers_became_usable({"log_level": "INFO"}, {}) == set()

    def test_an_empty_save_counts_for_nothing(self):
        assert _providers_became_usable({}, {}) == set()


class TestTheOffSwitch:
    """His point 3: a way to turn the provider trigger off.

    A separate flag rather than letting `wanted_revive_max_per_run` reach 0,
    because that cap is shared with the age trigger — he wants to keep
    revive-by-age, and one knob for both would take it with it.
    """

    def test_it_defaults_to_on(self):
        from config_settings import Settings

        assert Settings().wanted_revive_on_provider_change is True

    def test_it_can_be_switched_off(self):
        from config_settings import Settings

        assert (
            Settings(wanted_revive_on_provider_change=False).wanted_revive_on_provider_change
            is False
        )

    def test_the_route_honours_it(self, monkeypatch):
        from routes.config import core

        class S:
            wanted_revive_on_provider_change = False

        monkeypatch.setattr("config.peek_settings", lambda: S())
        assert core._revive_on_provider_change_enabled() is False

    def test_a_missing_setting_keeps_todays_behaviour(self, monkeypatch):
        """An older database has no row for it; the default is on."""
        from routes.config import core

        monkeypatch.setattr("config.peek_settings", lambda: object())
        assert core._revive_on_provider_change_enabled() is True

    def test_it_is_reachable_through_the_config_api(self):
        """A setting no view declares cannot be switched on or off by anyone."""
        import config_views

        declared: set[str] = set()
        for name in dir(config_views):
            fields = getattr(getattr(config_views, name), "_fields", None)
            if isinstance(fields, frozenset):
                declared |= set(fields)
        assert "wanted_revive_on_provider_change" in declared

    def test_the_age_trigger_is_untouched_by_it(self):
        """His acceptance criterion: revive_exhausted_by_age stays as it was."""
        import inspect

        from services import wanted_revive

        source = inspect.getsource(wanted_revive.revive_exhausted_by_age)
        assert "wanted_revive_on_provider_change" not in source
