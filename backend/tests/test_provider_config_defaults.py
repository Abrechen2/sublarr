"""A provider default must be the same wherever it is written down.

GitHub #249: a provider's default lives in up to three places — the
``config_fields`` entry, the ``UISettings`` field and the constructor
parameter. At runtime the setting wins whenever it is non-empty
(``_get_provider_config``), so changing only the provider left users on the
old default while the provider's own test passed. An empty setting falls
through to the field default (napisy24's public login), so "" is allowed.
"""

import inspect

import pytest

from config_settings import UISettings
from providers.registry import _PROVIDER_CLASSES, import_builtin_providers


def _builtin_fields():
    import_builtin_providers()
    for name, cls in sorted(_PROVIDER_CLASSES.items()):
        if getattr(cls, "is_plugin", False) or getattr(cls, "hub_id", ""):
            continue
        for field in getattr(cls, "config_fields", []):
            if field["key"] in UISettings.model_fields:
                yield pytest.param(name, cls, field, id=f"{name}:{field['key']}")


FIELDS = list(_builtin_fields())


def test_the_check_sees_the_providers_from_the_issue():
    keys = {p.values[2]["key"] for p in FIELDS}
    assert {"animetosho_root_attachments", "subsdump_url"} <= keys


@pytest.mark.parametrize(("name", "cls", "field"), FIELDS)
def test_setting_default_matches_the_field_default(name, cls, field):
    setting_default = UISettings.model_fields[field["key"]].default
    if setting_default in ("", None):
        return  # falls through to the field default at runtime
    assert setting_default == field.get("default", ""), (
        f"UISettings.{field['key']} defaults to {setting_default!r}, "
        f"{name}.config_fields to {field.get('default', '')!r}"
    )


@pytest.mark.parametrize(("name", "cls", "field"), FIELDS)
def test_constructor_default_matches_the_field_default(name, cls, field):
    param = field["key"].removeprefix(f"{name}_")
    sig = inspect.signature(cls.__init__).parameters.get(param)
    if sig is None or sig.default is inspect.Parameter.empty:
        return
    assert sig.default == field.get("default", ""), (
        f"{name}.__init__({param}=...) defaults to {sig.default!r}, "
        f"config_fields to {field.get('default', '')!r}"
    )
