"""The automatic repairs are opt-in: an update never turns them on."""

from types import SimpleNamespace
from unittest.mock import patch

from config_settings import UISettings
from services.auto_repair import auto_repair_enabled


def test_off_by_default():
    assert UISettings.model_fields["auto_repair_enabled"].default is False


def test_follows_the_setting():
    with patch("config.get_settings", return_value=SimpleNamespace(auto_repair_enabled=True)):
        assert auto_repair_enabled() is True
    with patch("config.get_settings", side_effect=RuntimeError("no settings")):
        assert auto_repair_enabled() is False
