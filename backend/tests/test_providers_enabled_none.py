"""``providers_enabled`` can say "no provider at all" (#61 A11).

Empty means "every provider that is not opt-in", so switching off the last
provider wrote "" and turned them all back on. "none" is the empty selection.
"""

from providers.registry import default_enabled_names, resolve_enabled_names


def test_none_enables_nothing():
    assert resolve_enabled_names("none") == set()
    assert resolve_enabled_names(" NONE ") == set()


def test_empty_still_means_the_defaults():
    assert resolve_enabled_names("") == default_enabled_names()


def test_the_support_report_reads_the_setting_like_the_manager(client):
    """It had its own parser: an empty value showed opt-in providers as enabled."""
    from unittest.mock import MagicMock, patch

    import config
    from providers.registry import NO_PROVIDERS
    from routes.system.support_sections import provider_rows

    real = config.get_settings()
    fake = MagicMock(wraps=real, providers_enabled=NO_PROVIDERS)
    with client.application.app_context(), patch("config.get_settings", return_value=fake):
        rows = provider_rows()

    assert rows and not any(r["enabled"] for r in rows)
