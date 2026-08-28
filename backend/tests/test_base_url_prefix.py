"""Serving Sublarr under a reverse-proxy path prefix.

The settings page has offered a "Base URL" field for a long time. It stored the
value and nothing ever read it: no route, no template, no link builder. Setting
it did nothing at all.

Wiring it follows the convention of the *arr applications this sits next to —
the application answers under the prefix itself, so the proxy can forward the
path unchanged (``proxy_pass http://host:5765;`` with no trailing slash). The
un-prefixed paths keep working too, deliberately: a wrong value in that field
would otherwise lock the user out of the UI that fixes it.

Two things have to line up for the browser:

* requests to ``/<prefix>/api/v1/...`` must reach the same routes as
  ``/api/v1/...``;
* the served ``index.html`` must carry ``<base href="/<prefix>/">`` so the
  relative asset URLs in the bundle resolve there and not against whatever deep
  client-side route the user reloaded on.
"""

from __future__ import annotations

import pytest

from db.config import save_config_entry


def _set_base_url(client, value: str) -> None:
    """Store the value and reload settings — exactly what PUT /config does.

    The prefix is read off the settings singleton because the middleware runs
    before Flask has an application context, so a test that only writes the
    config entry would not see the prefix take effect and would prove nothing.
    """
    from config import reload_settings
    from db.config import get_all_config_entries

    with client.application.app_context():
        save_config_entry("base_url", value)
        reload_settings(get_all_config_entries())


@pytest.fixture
def prefixed(client):
    """Set a base URL the way the settings page does."""
    _set_base_url(client, "/sublarr")
    return client


def test_api_answers_under_the_prefix(prefixed):
    resp = prefixed.get("/sublarr/api/v1/health")
    assert resp.status_code == 200, resp.get_data(as_text=True)[:200]
    assert "status" in resp.get_json(), resp.get_json()


def test_api_still_answers_without_the_prefix(prefixed):
    """A wrong Base URL must not lock the user out of fixing it."""
    resp = prefixed.get("/api/v1/health")
    assert resp.status_code == 200
    assert "status" in resp.get_json(), resp.get_json()


def test_unset_base_url_changes_nothing(client):
    _set_base_url(client, "")
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert "status" in resp.get_json(), resp.get_json()


def test_a_prefix_that_only_looks_like_one_is_not_stripped(prefixed):
    """``/sublarrX`` shares a prefix string but is a different location.

    It must not reach the API. What it gets instead is the SPA catch-all, the
    same as any other unknown path — so the check is "did not reach health",
    not a status code.
    """
    resp = prefixed.get("/sublarrX/api/v1/health")
    assert "status" not in (resp.get_json() or {}), resp.get_json()


@pytest.mark.parametrize("stored", ["/sublarr", "sublarr", "/sublarr/", "  /sublarr//  "])
def test_the_shapes_a_user_types_all_work(client, stored):
    _set_base_url(client, stored)
    body = client.get("/sublarr/api/v1/health").get_json()
    assert "status" in (body or {}), body


def test_index_html_carries_the_base_element(prefixed, tmp_path, monkeypatch):
    from flask import current_app

    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text(
        '<!DOCTYPE html><html><head><base href="/" />'
        '<script type="module" src="./assets/app.js"></script></head>'
        "<body><div id=root></div></body></html>",
        encoding="utf-8",
    )
    with prefixed.application.app_context():
        current_app.static_folder = str(static)

    body = prefixed.get("/sublarr/").get_data(as_text=True)

    assert '<base href="/sublarr/"' in body, body[:300]
    assert 'window.__SUBLARR_BASE__ = "/sublarr"' in body, body[:300]


def test_index_html_at_the_root_keeps_the_plain_base(client, tmp_path):
    from flask import current_app

    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text(
        '<!DOCTYPE html><html><head><base href="/" /></head><body></body></html>',
        encoding="utf-8",
    )
    with client.application.app_context():
        current_app.static_folder = str(static)

    body = client.get("/").get_data(as_text=True)

    assert '<base href="/"' in body
    assert 'window.__SUBLARR_BASE__ = ""' in body


class TestHostileBaseUrl:
    """The prefix reaches an HTML attribute and a JS string literal.

    It is written by an authenticated caller, but it is *stored* and then
    rendered for everyone who opens the page — and `/config/import` will take
    it from a backup file whose origin nobody checked. Neither sink may be
    escapable.
    """

    @pytest.mark.parametrize(
        "hostile",
        [
            '/x" onload="alert(1)',
            "/x'><script>alert(1)</script>",
            '/x";alert(1);//',
            "/x</script><script>alert(1)</script>",
            "/x\\",
            "javascript:alert(1)",
            "//evil.example.com",
        ],
    )
    def test_a_hostile_value_cannot_escape_either_sink(self, hostile):
        from base_path import inject_base_into_index, normalize_base_path

        shell = '<html><head><base href="/" /></head><body></body></html>'
        out = inject_base_into_index(shell, normalize_base_path(hostile))

        assert "<script>alert(1)</script>" not in out, out
        assert "onload=" not in out, out
        # exactly one base element and one marker script survive
        assert out.count("<base ") == 1, out
        assert out.count("<script>") == 1, out

    @pytest.mark.parametrize(
        "bad",
        ['/x" onload="y', "/x<script>", "javascript:alert(1)", "//evil.example.com", "/a b"],
    )
    def test_values_that_are_not_a_path_prefix_are_refused(self, bad):
        from base_path import normalize_base_path

        assert normalize_base_path(bad) == "", f"{bad!r} was accepted as a prefix"

    @pytest.mark.parametrize("good", ["/sublarr", "sublarr", "/media/subs", "/a_b-c.d~e"])
    def test_real_prefixes_still_pass(self, good):
        from base_path import normalize_base_path

        assert normalize_base_path(good).startswith("/")


class TestMiddlewareNeverBuildsSettings:
    """The prefix lookup must never be the thing that creates the settings.

    The middleware runs before Flask pushes an application context, and
    ``get_settings()`` builds the singleton by merging the database overrides
    on top of the defaults — a read it cannot do without that context. Calling
    it from here therefore caches a Settings object with **every stored setting
    missing**, and every later reader gets that object: measured, an override of
    ``wanted_anime_only=False`` came back ``True`` and stayed ``True``.

    So the rule is not "handle the exception" but "never trigger the build".
    An unbuilt singleton means serve at the root for that one request, which is
    the safe default and corrects itself as soon as the app has started.
    """

    def test_get_base_path_does_not_create_the_singleton(self):
        import config_singleton
        from base_path import get_base_path

        config_singleton._settings = None
        try:
            assert get_base_path() == ""
            assert config_singleton._settings is None, (
                "the prefix lookup built the settings singleton — it would be "
                "built without the database overrides"
            )
        finally:
            config_singleton._settings = None

    def test_stored_overrides_survive_a_request(self, client):
        """The end the rule protects: a DB override must not be lost."""
        import config_singleton
        from config import get_settings, reload_settings
        from db.config import get_all_config_entries, save_config_entry

        with client.application.app_context():
            save_config_entry("wanted_anime_only", "false")
            reload_settings(get_all_config_entries())

        config_singleton._settings = None
        client.get("/api/v1/health")

        with client.application.app_context():
            reload_settings(get_all_config_entries())
            assert get_settings().wanted_anime_only is False
