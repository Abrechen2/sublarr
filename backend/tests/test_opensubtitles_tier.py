import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

import pytest

from providers.base import ProviderAuthError, SubtitleResult
from providers.opensubtitles import OpenSubtitlesProvider


def _make_download_result():
    return SubtitleResult(
        provider_name="opensubtitles",
        subtitle_id="123",
        language="de",
        filename="Subtitle.de.srt",
        provider_data={"file_id": 7391597},
    )


def _download_link_response():
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "link": "https://opensubtitles.com/file",
        "file_name": "Subtitle.de.srt",
    }
    return response


def _login_response(token="new-token"):
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"token": token}
    return response


def _make_download_provider(username="user", password="pass", token="old-token"):
    provider = OpenSubtitlesProvider(
        api_key="test-key",
        username=username,
        password=password,
    )
    provider.session = MagicMock()
    provider.session.headers = {}
    if token:
        provider._token = token
        provider.session.headers["Authorization"] = f"Bearer {token}"
    return provider


def test_detects_free_tier_from_user_info_response():
    fake_session = MagicMock()
    fake_session.get.return_value.status_code = 200
    fake_session.get.return_value.json.return_value = {
        "data": {"level": "Sub leecher", "vip": False},
    }
    p = OpenSubtitlesProvider.__new__(OpenSubtitlesProvider)
    p.session = fake_session
    p.api_key = "x"
    assert p.detect_tier() == "free"


def test_detects_vip_tier():
    fake_session = MagicMock()
    fake_session.get.return_value.status_code = 200
    fake_session.get.return_value.json.return_value = {
        "data": {"level": "VIP member", "vip": True},
    }
    p = OpenSubtitlesProvider.__new__(OpenSubtitlesProvider)
    p.session = fake_session
    p.api_key = "x"
    assert p.detect_tier() == "vip"


def test_defaults_to_free_on_failure():
    fake_session = MagicMock()
    fake_session.get.side_effect = Exception("network")
    p = OpenSubtitlesProvider.__new__(OpenSubtitlesProvider)
    p.session = fake_session
    p.api_key = "x"
    assert p.detect_tier() == "free"


def test_detect_tier_caches_result():
    fake_session = MagicMock()
    fake_session.get.return_value.status_code = 200
    fake_session.get.return_value.json.return_value = {
        "data": {"level": "VIP member", "vip": True},
    }
    p = OpenSubtitlesProvider.__new__(OpenSubtitlesProvider)
    p.session = fake_session
    p.api_key = "x"
    assert p.detect_tier() == "vip"
    assert p.detect_tier() == "vip"  # second call uses cache
    assert p.detect_tier() == "vip"
    assert fake_session.get.call_count == 1


def test_detect_tier_force_refresh_bypasses_cache():
    fake_session = MagicMock()
    fake_session.get.return_value.status_code = 200
    fake_session.get.return_value.json.return_value = {
        "data": {"level": "Sub leecher", "vip": False},
    }
    p = OpenSubtitlesProvider.__new__(OpenSubtitlesProvider)
    p.session = fake_session
    p.api_key = "x"
    p.detect_tier()
    p.detect_tier(force=True)
    assert fake_session.get.call_count == 2


def test_download_auth_401_refreshes_token_once_and_retries():
    provider = _make_download_provider()
    calls = {"download": 0, "login": 0}

    def post(url, json):
        if url.endswith("/login"):
            calls["login"] += 1
            return _login_response()
        if url.endswith("/download"):
            calls["download"] += 1
            if calls["download"] == 1:
                raise ProviderAuthError(
                    "Authentication failed for /download: HTTP 401", status_code=401
                )
            return _download_link_response()
        raise AssertionError(f"unexpected URL: {url}")

    provider.session.post.side_effect = post

    with patch("providers.opensubtitles._stream_download", return_value=b"payload"):
        assert provider.download(_make_download_result()) == b"payload"

    assert calls == {"download": 2, "login": 1}
    assert provider._token == "new-token"
    assert provider.session.headers["Authorization"] == "Bearer new-token"


def test_download_auth_401_after_refresh_raises_without_second_retry():
    provider = _make_download_provider()
    calls = {"download": 0, "login": 0}

    def post(url, json):
        if url.endswith("/login"):
            calls["login"] += 1
            return _login_response()
        if url.endswith("/download"):
            calls["download"] += 1
            raise ProviderAuthError(
                "Authentication failed for /download: HTTP 401", status_code=401
            )
        raise AssertionError(f"unexpected URL: {url}")

    provider.session.post.side_effect = post

    with (
        patch("providers.opensubtitles._stream_download", return_value=b"payload"),
        pytest.raises(ProviderAuthError),
    ):
        provider.download(_make_download_result())

    assert calls == {"download": 2, "login": 1}


def test_download_auth_401_failed_refresh_raises_original_error_without_retry():
    provider = _make_download_provider()
    calls = {"download": 0, "login": 0}

    def post(url, json):
        if url.endswith("/login"):
            calls["login"] += 1
            return _login_response(token="")
        if url.endswith("/download"):
            calls["download"] += 1
            raise ProviderAuthError(
                "Authentication failed for /download: HTTP 401", status_code=401
            )
        raise AssertionError(f"unexpected URL: {url}")

    provider.session.post.side_effect = post

    with (
        patch("providers.opensubtitles._stream_download", return_value=b"payload"),
        pytest.raises(ProviderAuthError),
    ):
        provider.download(_make_download_result())

    assert calls == {"download": 1, "login": 1}


def test_download_auth_401_without_credentials_raises_without_login_attempt():
    provider = _make_download_provider(username="", password="", token=None)
    calls = {"download": 0, "login": 0}

    def post(url, json):
        if url.endswith("/login"):
            calls["login"] += 1
            return _login_response()
        if url.endswith("/download"):
            calls["download"] += 1
            raise ProviderAuthError(
                "Authentication failed for /download: HTTP 401", status_code=401
            )
        raise AssertionError(f"unexpected URL: {url}")

    provider.session.post.side_effect = post

    with pytest.raises(ProviderAuthError):
        provider.download(_make_download_result())

    assert calls == {"download": 1, "login": 0}


def test_concurrent_download_auth_401s_share_one_token_refresh():
    provider = _make_download_provider()
    calls = {"download": 0, "login": 0}
    state_lock = threading.Lock()
    first_failures = threading.Barrier(2)

    def post(url, json):
        if url.endswith("/login"):
            with state_lock:
                calls["login"] += 1
            return _login_response()
        if url.endswith("/download"):
            with state_lock:
                calls["download"] += 1
                attempt = calls["download"]
            if attempt <= 2:
                first_failures.wait(timeout=2)
                raise ProviderAuthError(
                    "Authentication failed for /download: HTTP 401", status_code=401
                )
            return _download_link_response()
        raise AssertionError(f"unexpected URL: {url}")

    provider.session.post.side_effect = post

    with (
        patch("providers.opensubtitles._stream_download", return_value=b"payload"),
        ThreadPoolExecutor(max_workers=2) as executor,
    ):
        futures = [
            executor.submit(provider.download, _make_download_result()),
            executor.submit(provider.download, _make_download_result()),
        ]
        results = [future.result(timeout=2) for future in futures]

    assert results == [b"payload", b"payload"]
    assert calls == {"download": 4, "login": 1}
