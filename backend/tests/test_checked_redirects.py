"""Every redirect hop is checked like the first URL (code check 2026-11-05, N-2)."""

from unittest.mock import MagicMock, patch

import pytest

from security_utils import get_with_checked_redirects


def _resp(status, location=None):
    r = MagicMock()
    r.is_redirect = status in (301, 302, 303, 307, 308)
    r.status_code = status
    r.headers = {"Location": location} if location else {}
    return r


def test_a_redirect_to_a_blocked_host_is_refused():
    hops = [_resp(302, "http://169.254.169.254/latest/meta-data/")]
    with patch("requests.get", side_effect=hops) as get, pytest.raises(ValueError):
        get_with_checked_redirects("https://github.com/x.zip", timeout=5)
    assert get.call_count == 1
    assert get.call_args.kwargs["allow_redirects"] is False


def test_an_https_only_fetch_refuses_a_downgrade():
    hops = [_resp(302, "http://example.com/x.zip")]
    with patch("requests.get", side_effect=hops), pytest.raises(ValueError):
        get_with_checked_redirects("https://example.com/x.zip", https_only=True, timeout=5)


def test_allowed_redirects_are_followed():
    final = _resp(200)
    hops = [_resp(302, "/releases/x.zip"), final]
    with (
        patch("security_utils.validate_service_url", return_value=(True, None)),
        patch("requests.get", side_effect=hops) as get,
    ):
        assert get_with_checked_redirects("https://github.com/a", timeout=5) is final
    assert get.call_args.args[0] == "https://github.com/releases/x.zip"


def test_a_redirect_loop_ends():
    with (
        patch("security_utils.validate_service_url", return_value=(True, None)),
        patch("requests.get", return_value=_resp(302, "https://github.com/a")),
        pytest.raises(ValueError, match="Too many redirects"),
    ):
        get_with_checked_redirects("https://github.com/a", timeout=5)
