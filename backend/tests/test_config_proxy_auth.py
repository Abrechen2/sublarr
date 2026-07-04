from config_settings import UISettings
from config_singleton import reload_settings


def test_defaults():
    ui = UISettings()
    assert ui.proxy_auth_enabled is False
    assert ui.proxy_auth_trusted_ips == ""
    assert ui.proxy_auth_header == "Remote-User"


def test_overlay_from_config_entries():
    s = reload_settings(
        {
            "proxy_auth_enabled": "true",
            "proxy_auth_trusted_ips": "10.0.0.0/8, 192.168.1.5",
            "proxy_auth_header": "X-Forwarded-User",
        }
    )
    assert s.proxy_auth_enabled is True
    assert s.proxy_auth_trusted_ips == "10.0.0.0/8, 192.168.1.5"
    assert s.proxy_auth_header == "X-Forwarded-User"
    reload_settings({})  # reset the singleton for other tests
