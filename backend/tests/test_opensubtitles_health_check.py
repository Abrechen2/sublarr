"""health_check must probe an endpoint the configured auth mode can satisfy.

Found 2026-08-20: /providers/test/opensubtitles reported 401 on an
API-key-only install while search and download worked fine (prod: 888
downloads in the same 48 hours). ``/infos/user`` requires a user JWT that a
key-only session never holds — the health check was asking a question the
configured auth mode cannot answer. Key-only sessions now probe
``/infos/formats`` (Api-Key alone suffices); sessions holding a user token
keep the richer ``/infos/user`` with its remaining-downloads counter and
fall back to the key probe when that token has gone stale.
"""

from unittest.mock import MagicMock

from providers.opensubtitles import OpenSubtitlesProvider


def _resp(status=200, data=None):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = {"data": data or {}}
    return r


def _provider(username="", password="", token=None):
    p = OpenSubtitlesProvider(api_key="k", username=username, password=password)
    p.session = MagicMock()
    p.session.headers = {}
    if token:
        p._token = token
        p.session.headers["Authorization"] = f"Bearer {token}"
    return p


class TestKeyOnlyMode:
    def test_probes_formats_not_user(self):
        """No user token → the key-only endpoint is the only fair question."""
        p = _provider()
        p.session.get.return_value = _resp(200)

        healthy, msg = p.health_check()

        assert healthy
        (url,) = p.session.get.call_args.args
        assert url.endswith("/infos/formats")

    def test_probe_strips_any_authorization_header(self):
        """A stale bearer on the session must not poison the key-only probe.

        requests removes a session header when the per-request value is None —
        the probe has to use that mechanism explicitly.
        """
        p = _provider()
        p.session.get.return_value = _resp(200)

        p.health_check()

        headers = p.session.get.call_args.kwargs.get("headers") or {}
        assert "Authorization" in headers and headers["Authorization"] is None

    def test_invalid_key_reports_the_status(self):
        p = _provider()
        p.session.get.return_value = _resp(403)

        healthy, msg = p.health_check()

        assert not healthy
        assert "403" in msg

    def test_no_api_key_short_circuits(self):
        p = OpenSubtitlesProvider(api_key="")
        healthy, msg = p.health_check()
        assert not healthy
        assert "API key" in msg

    def test_uninitialized_short_circuits(self):
        p = OpenSubtitlesProvider(api_key="k")
        healthy, msg = p.health_check()
        assert not healthy
        assert "initialized" in msg.lower()


class TestUserSessionMode:
    def test_user_session_reports_remaining_downloads(self):
        p = _provider(username="u", password="pw", token="t")
        p.session.get.return_value = _resp(200, {"remaining_downloads": 42})

        healthy, msg = p.health_check()

        assert healthy
        assert "42" in msg
        (url,) = p.session.get.call_args_list[0].args
        assert url.endswith("/infos/user")

    def test_stale_token_falls_back_to_key_probe(self):
        """An expired JWT must not fail the check — the download path refreshes
        its token on demand, so a valid API key is still a healthy provider."""
        p = _provider(username="u", password="pw", token="stale")
        p.session.get.side_effect = [_resp(401), _resp(200)]

        healthy, msg = p.health_check()

        assert healthy
        (url,) = p.session.get.call_args_list[1].args
        assert url.endswith("/infos/formats")

    def test_stale_token_and_bad_key_is_unhealthy(self):
        p = _provider(username="u", password="pw", token="stale")
        p.session.get.side_effect = [_resp(401), _resp(401)]

        healthy, msg = p.health_check()

        assert not healthy
        assert "401" in msg
