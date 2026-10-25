"""Socket.IO origin check (Forgejo #60).

The Engine.IO handshake rejects any ``Origin`` that is not allowed with a 400.
Before the fix the allowlist was exactly ``SUBLARR_CORS_ORIGINS``, whose
default only listed localhost — so a browser that opened Sublarr through its
LAN IP or a domain loaded the UI but never got live updates.

Contract under test:
- the app's own origin (the ``Host`` header the WSGI server sees) is always
  allowed, with no env var set;
- a foreign origin is rejected;
- ``SUBLARR_CORS_ORIGINS`` adds foreign origins on top of same-origin;
- ``X-Forwarded-Host`` / ``X-Forwarded-Proto`` are NOT trusted — Sublarr runs
  no ProxyFix, so a client could set them to anything.
"""

import os

import pytest

from app import create_app
from config import get_settings, reload_settings
from config_settings import BootSettings
from socketio_origins import build_origin_checker, is_same_origin

HANDSHAKE = "/socket.io/?EIO=4&transport=polling"
LAN = "192.168.1.50:5765"


def _handshake(app, origin, host=LAN, scheme="http", headers=None):
    client = app.test_client()
    all_headers = {"Origin": origin} if origin else {}
    all_headers.update(headers or {})
    return client.get(HANDSHAKE, base_url=f"{scheme}://{host}", headers=all_headers)


@pytest.fixture
def make_app(temp_db):
    def _make(cors_origins=None):
        if cors_origins is None:
            os.environ.pop("SUBLARR_CORS_ORIGINS", None)
        else:
            os.environ["SUBLARR_CORS_ORIGINS"] = cors_origins
        reload_settings()
        app = create_app(testing=True)
        app.config["TESTING"] = True
        return app

    yield _make
    os.environ.pop("SUBLARR_CORS_ORIGINS", None)
    reload_settings()


# ---------------------------------------------------------------- handshake


def test_default_is_same_origin_only(make_app):
    make_app()
    assert get_settings().cors_origins == ""
    assert BootSettings.model_fields["cors_origins"].default == ""


def test_own_lan_origin_accepted_without_env_var(make_app):
    app = make_app()
    resp = _handshake(app, f"http://{LAN}")
    assert resp.status_code == 200
    assert resp.headers.get("Access-Control-Allow-Origin") == f"http://{LAN}"


def test_own_domain_origin_accepted_without_env_var(make_app):
    app = make_app()
    resp = _handshake(app, "http://sublarr.example.com", host="sublarr.example.com")
    assert resp.status_code == 200


def test_foreign_origin_rejected(make_app):
    app = make_app()
    assert _handshake(app, "http://evil.example").status_code == 400


def test_localhost_dev_origin_no_longer_allowed_by_default(make_app):
    app = make_app()
    assert _handshake(app, "http://localhost:5173").status_code == 400


def test_same_host_other_port_rejected(make_app):
    app = make_app()
    assert _handshake(app, "http://192.168.1.50:8080").status_code == 400


def test_configured_extra_origin_accepted(make_app):
    app = make_app("https://other.example, http://localhost:5173")
    assert _handshake(app, "https://other.example").status_code == 200
    assert _handshake(app, "http://localhost:5173").status_code == 200
    # The list extends same-origin, it does not replace it.
    assert _handshake(app, f"http://{LAN}").status_code == 200
    assert _handshake(app, "http://evil.example").status_code == 400


def test_wildcard_still_allows_everything(make_app):
    app = make_app("*")
    assert _handshake(app, "http://evil.example").status_code == 200


def test_request_without_origin_accepted(make_app):
    app = make_app()
    assert _handshake(app, None).status_code == 200


def test_tls_terminating_proxy_forwarding_host(make_app):
    # Proxy terminates TLS and forwards Host; Sublarr itself sees plain http.
    app = make_app()
    resp = _handshake(app, "https://sublarr.example.com", host="sublarr.example.com")
    assert resp.status_code == 200


def test_x_forwarded_host_is_not_trusted(make_app):
    app = make_app()
    resp = _handshake(
        app,
        "http://evil.example",
        headers={"X-Forwarded-Host": "evil.example", "X-Forwarded-Proto": "http"},
    )
    assert resp.status_code == 400


def test_vite_dev_proxy_keeps_host(make_app):
    # frontend/vite.config.ts proxies /socket.io WITHOUT changeOrigin, so the
    # backend sees Host localhost:5173 alongside Origin localhost:5173.
    app = make_app()
    resp = _handshake(app, "http://localhost:5173", host="localhost:5173")
    assert resp.status_code == 200


# ---------------------------------------------------------------- helpers


@pytest.mark.parametrize(
    ("origin", "host", "expected"),
    [
        ("http://192.168.1.50:5765", "192.168.1.50:5765", True),
        ("http://Sublarr.Example.com", "sublarr.example.com", True),
        ("https://sublarr.example.com", "sublarr.example.com", True),
        ("https://sublarr.example.com", "sublarr.example.com:443", True),
        ("http://sublarr.example.com:80", "sublarr.example.com", True),
        ("https://sublarr.example.com:8443", "sublarr.example.com", False),
        ("http://[::1]:5765", "[::1]:5765", True),
        ("http://evil.example", "sublarr.example.com", False),
        ("ftp://sublarr.example.com", "sublarr.example.com", False),
        ("null", "sublarr.example.com", False),
        ("http://sublarr.example.com", "", False),
        ("http://sublarr.example.com:notaport", "sublarr.example.com", False),
    ],
)
def test_is_same_origin(origin, host, expected):
    assert is_same_origin(origin, host) is expected


def test_checker_ignores_forwarded_headers():
    check = build_origin_checker("")
    environ = {
        "HTTP_HOST": LAN,
        "HTTP_X_FORWARDED_HOST": "evil.example",
        "HTTP_X_FORWARDED_PROTO": "https",
    }
    assert check("https://evil.example", environ) is False
    assert check(f"http://{LAN}", environ) is True


def test_checker_normalises_configured_list():
    check = build_origin_checker(" https://Other.Example/ ,,")
    assert check("https://other.example", {"HTTP_HOST": LAN}) is True
    assert check("http://other.example", {"HTTP_HOST": LAN}) is False


def test_checker_wildcard():
    assert build_origin_checker("http://a.example, *") == "*"
