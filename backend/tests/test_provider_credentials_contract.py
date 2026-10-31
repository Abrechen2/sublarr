"""Every credential a provider form shows can be saved and reaches the provider.

Audit #61 A01: five providers declared bare ``username`` / ``password`` /
``apikey`` fields. PUT /config refused them ("Unknown config key"), and the
manager read settings of those names, which do not exist — the accounts of
LegendasDivx, Addic7ed (subliminal) and both OpenSubtitles wrappers could not
be configured at all.
"""

import importlib
import pkgutil

import pytest

import providers
from providers import _PROVIDER_CLASSES


def _builtin_fields():
    for mod in pkgutil.iter_modules(providers.__path__):
        try:
            importlib.import_module(f"providers.{mod.name}")
        except Exception:  # noqa: BLE001 — optional dependencies
            continue
    for name, cls in sorted(_PROVIDER_CLASSES.items()):
        if getattr(cls, "is_plugin", False) or getattr(cls, "hub_id", None):
            continue
        for field in getattr(cls, "config_fields", []) or []:
            yield name, field


FIELDS = list(_builtin_fields())


def test_there_are_provider_fields_to_check():
    assert len(FIELDS) > 20


@pytest.mark.parametrize(("provider", "field"), FIELDS, ids=[f"{p}:{f['key']}" for p, f in FIELDS])
def test_a_provider_field_is_a_setting(provider, field):
    from routes.config.keys import model_config_keys

    assert field["key"] in model_config_keys(), f"{provider} declares {field['key']!r}"


def test_a_saved_account_reaches_the_provider(client):
    from providers import get_provider_manager

    response = client.put(
        "/api/v1/config",
        json={
            "legendasdivx_username": "alice",
            "legendasdivx_password": "s3cret",
            "opensubtitlescom_subliminal_apikey": "k3y",
        },
    )
    assert response.status_code == 200, response.get_json()

    with client.application.app_context():
        manager = get_provider_manager()
    assert manager._get_provider_config("legendasdivx") == {
        "username": "alice",
        "password": "s3cret",
    }
    assert manager._get_provider_config("opensubtitlescom_subliminal")["apikey"] == "k3y"


def test_napisy24_keeps_its_public_account_until_one_is_entered(client):
    from providers import get_provider_manager

    with client.application.app_context():
        config = get_provider_manager()._get_provider_config("napisy24")

    assert config["username"] == "subliminal"


def test_the_api_key_is_masked():
    from config_settings import is_sensitive_config_key

    assert is_sensitive_config_key("opensubtitlescom_subliminal_apikey")
