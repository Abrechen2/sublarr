"""Tests for the SPA static-serving path (app_routes_core.serve_spa).

Covers pre-compressed (.br/.gz) content-negotiation, correct Content-Type from
the original name, immutable caching for hashed /assets/, no-cache for the
index shell, the /api JSON-404 guard, and path-traversal safety.
"""

import gzip

import pytest
from flask import Flask

from app_routes_core import _register_app_routes


@pytest.fixture
def spa_app(tmp_path):
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    raw = b"console.log('sublarr');" + b"x" * 4096  # > 1 KB, clearly identifiable
    asset = static / "assets" / "app-abc123.js"
    asset.write_bytes(raw)
    (static / "assets" / "app-abc123.js.br").write_bytes(b"BROTLI-BYTES-STANDIN")
    (static / "assets" / "app-abc123.js.gz").write_bytes(gzip.compress(raw))
    (static / "index.html").write_bytes(b"<!doctype html><title>Sublarr</title>")

    app = Flask(__name__, static_folder=str(static))
    _register_app_routes(app)
    app.config.update(TESTING=True)
    return app, raw


def test_serves_brotli_when_accepted(spa_app):
    app, _ = spa_app
    r = app.test_client().get("/assets/app-abc123.js", headers={"Accept-Encoding": "br, gzip"})
    assert r.status_code == 200
    assert r.headers["Content-Encoding"] == "br"
    # Content-Type from the original name, not the .br (platform may say
    # text/javascript or application/javascript — both are valid for JS).
    assert "javascript" in r.headers["Content-Type"]
    assert "Accept-Encoding" in r.headers.get("Vary", "")
    assert "immutable" in r.headers["Cache-Control"]
    assert r.data == b"BROTLI-BYTES-STANDIN"


def test_falls_back_to_gzip(spa_app):
    app, raw = spa_app
    r = app.test_client().get("/assets/app-abc123.js", headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200
    assert r.headers["Content-Encoding"] == "gzip"
    assert gzip.decompress(r.data) == raw


def test_serves_raw_when_no_encoding(spa_app):
    app, raw = spa_app
    r = app.test_client().get("/assets/app-abc123.js", headers={"Accept-Encoding": "identity"})
    assert r.status_code == 200
    assert "Content-Encoding" not in r.headers
    assert r.data == raw
    assert "immutable" in r.headers["Cache-Control"]


def test_index_is_no_cache(spa_app):
    app, _ = spa_app
    r = app.test_client().get("/", headers={"Accept-Encoding": "br"})
    assert r.status_code == 200
    assert r.headers["Cache-Control"] == "no-cache"
    assert b"Sublarr" in r.data


def test_unknown_route_serves_index_shell(spa_app):
    # SPA client-side routes fall through to index.html (not 404).
    app, _ = spa_app
    r = app.test_client().get("/settings/general")
    assert r.status_code == 200
    assert b"<!doctype html>" in r.data


def test_api_paths_return_json_404(spa_app):
    app, _ = spa_app
    r = app.test_client().get("/api/v1/does-not-exist")
    assert r.status_code == 404
    assert r.get_json()["error"] == "Not found"


def test_path_traversal_is_blocked(spa_app):
    app, _ = spa_app
    # send_from_directory must reject escaping the static dir.
    r = app.test_client().get("/../../../etc/passwd")
    assert r.status_code in (403, 404) or b"passwd" not in r.data
