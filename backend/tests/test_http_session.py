"""Tests for providers/http_session module.

Covers: create_session, RetryingSession (default timeout, rate limit handling,
429 response, auth errors, X-RateLimit headers).
"""

import time
from unittest.mock import MagicMock, patch

import pytest
import requests

from providers.http_session import RetryingSession, create_session

# ---------------------------------------------------------------------------
# create_session
# ---------------------------------------------------------------------------


class TestCreateSession:
    def test_returns_retrying_session(self):
        session = create_session()
        assert isinstance(session, RetryingSession)

    def test_default_user_agent(self):
        session = create_session()
        assert session.headers["User-Agent"] == "Sublarr/1.0"

    def test_custom_user_agent(self):
        session = create_session(user_agent="TestAgent/2.0")
        assert session.headers["User-Agent"] == "TestAgent/2.0"

    def test_default_timeout(self):
        session = create_session()
        assert session.default_timeout == 15

    def test_custom_timeout(self):
        session = create_session(timeout=30)
        assert session.default_timeout == 30

    def test_https_adapter_mounted(self):
        session = create_session()
        assert "https://" in session.adapters

    def test_http_adapter_mounted(self):
        session = create_session()
        assert "http://" in session.adapters


# ---------------------------------------------------------------------------
# RetryingSession — basics
# ---------------------------------------------------------------------------


class TestRetryingSessionBasics:
    def test_default_timeout_applied(self):
        session = RetryingSession(timeout=10)
        assert session.default_timeout == 10

    def test_rate_limit_remaining_no_throttle(self):
        session = RetryingSession()
        assert session.rate_limit_remaining_seconds == 0.0

    def test_rate_limit_remaining_when_throttled(self):
        session = RetryingSession()
        session._rate_limit_until = time.time() + 30
        remaining = session.rate_limit_remaining_seconds
        assert 29 < remaining <= 30

    def test_rate_limit_remaining_expired(self):
        session = RetryingSession()
        session._rate_limit_until = time.time() - 10
        assert session.rate_limit_remaining_seconds == 0.0


# ---------------------------------------------------------------------------
# RetryingSession.request — timeout handling
# ---------------------------------------------------------------------------


class TestRetryingSessionTimeout:
    @patch.object(requests.Session, "request")
    def test_default_timeout_added(self, mock_request):
        mock_request.return_value = MagicMock(status_code=200, headers={})
        session = RetryingSession(timeout=20)
        session.request("GET", "https://example.com")
        _, kwargs = mock_request.call_args
        assert kwargs["timeout"] == 20

    @patch.object(requests.Session, "request")
    def test_explicit_timeout_preserved(self, mock_request):
        mock_request.return_value = MagicMock(status_code=200, headers={})
        session = RetryingSession(timeout=20)
        session.request("GET", "https://example.com", timeout=5)
        _, kwargs = mock_request.call_args
        assert kwargs["timeout"] == 5


# ---------------------------------------------------------------------------
# RetryingSession.request — error handling
# ---------------------------------------------------------------------------


class TestRetryingSessionErrors:
    @patch.object(requests.Session, "request")
    def test_connection_error_raised(self, mock_request):
        mock_request.side_effect = requests.ConnectionError("conn failed")
        session = RetryingSession()
        with pytest.raises(requests.ConnectionError):
            session.request("GET", "https://example.com")

    @patch.object(requests.Session, "request")
    def test_timeout_error_raised(self, mock_request):
        mock_request.side_effect = requests.Timeout("timed out")
        session = RetryingSession()
        with pytest.raises(requests.Timeout):
            session.request("GET", "https://example.com")


# ---------------------------------------------------------------------------
# RetryingSession.request — 429 rate limiting
# ---------------------------------------------------------------------------


class TestRetryingSession429:
    @patch.object(requests.Session, "request")
    def test_429_with_retry_after_header(self, mock_request):
        from providers.base import ProviderRateLimitError

        resp = MagicMock(status_code=429, headers={"Retry-After": "120"})
        mock_request.return_value = resp
        session = RetryingSession()

        with pytest.raises(ProviderRateLimitError, match="retry after 120s"):
            session.request("GET", "https://example.com")

        assert session._rate_limit_until is not None
        assert session._rate_limit_until > time.time()

    @patch.object(requests.Session, "request")
    def test_429_without_retry_after_defaults_60s(self, mock_request):
        from providers.base import ProviderRateLimitError

        resp = MagicMock(status_code=429, headers={})
        mock_request.return_value = resp
        session = RetryingSession()

        with pytest.raises(ProviderRateLimitError):
            session.request("GET", "https://example.com")

        # Default wait is 60 seconds
        assert session._rate_limit_until >= time.time() + 59

    @patch.object(requests.Session, "request")
    def test_429_non_integer_retry_after(self, mock_request):
        from providers.base import ProviderRateLimitError

        resp = MagicMock(status_code=429, headers={"Retry-After": "not-a-number"})
        mock_request.return_value = resp
        session = RetryingSession()

        with pytest.raises(ProviderRateLimitError):
            session.request("GET", "https://example.com")

        # Falls back to 60 seconds
        assert session._rate_limit_until >= time.time() + 59


# ---------------------------------------------------------------------------
# RetryingSession.request — auth errors
# ---------------------------------------------------------------------------


class TestRetryingSessionAuth:
    @patch.object(requests.Session, "request")
    def test_401_raises_auth_error(self, mock_request):
        from providers.base import ProviderAuthError

        resp = MagicMock(status_code=401, headers={})
        mock_request.return_value = resp
        session = RetryingSession()

        with pytest.raises(ProviderAuthError, match="Authentication failed"):
            session.request("GET", "https://example.com")

    @patch.object(requests.Session, "request")
    def test_403_raises_auth_error(self, mock_request):
        from providers.base import ProviderAuthError

        resp = MagicMock(status_code=403, headers={})
        mock_request.return_value = resp
        session = RetryingSession()

        with pytest.raises(ProviderAuthError, match="HTTP 403"):
            session.request("GET", "https://example.com")

    @pytest.mark.parametrize("status", [401, 403])
    @patch.object(requests.Session, "request")
    def test_the_status_travels_on_the_error(self, mock_request, status):
        """Callers recover differently from 401 and 403, and need to tell them apart.

        OpenSubtitles re-logs-in and retries once on 401, because its download
        token expires after 24h while search keeps working on the API key alone.
        On 403 it must not: the account simply may not have that file, and a
        second login only spends a request to be refused again.

        This assertion is the contract that makes that possible. Without the
        status on the exception the only discriminator is the message text, so
        rewording the line below would silently disable the recovery — and the
        provider's own tests, which build the exception themselves, would not
        notice.
        """
        from providers.base import ProviderAuthError

        mock_request.return_value = MagicMock(status_code=status, headers={})
        session = RetryingSession()

        with pytest.raises(ProviderAuthError) as excinfo:
            session.request("GET", "https://example.com")

        assert excinfo.value.status_code == status


# ---------------------------------------------------------------------------
# RetryingSession.request — X-RateLimit headers
# ---------------------------------------------------------------------------


class TestRetryingSessionRateLimitHeaders:
    @patch.object(requests.Session, "request")
    def test_low_remaining_sets_throttle(self, mock_request):
        resp = MagicMock(
            status_code=200,
            headers={
                "X-RateLimit-Remaining": "1",
                "X-RateLimit-Reset": "5",  # relative seconds
            },
        )
        mock_request.return_value = resp
        session = RetryingSession()
        session.request("GET", "https://example.com")

        assert session._rate_limit_until is not None
        assert session._rate_limit_until > time.time()

    @patch.object(requests.Session, "request")
    def test_remaining_above_1_no_throttle(self, mock_request):
        resp = MagicMock(
            status_code=200,
            headers={"X-RateLimit-Remaining": "10"},
        )
        mock_request.return_value = resp
        session = RetryingSession()
        session.request("GET", "https://example.com")

        assert session._rate_limit_until is None

    @patch.object(requests.Session, "request")
    def test_remaining_0_throttles(self, mock_request):
        resp = MagicMock(
            status_code=200,
            headers={"X-RateLimit-Remaining": "0"},
        )
        mock_request.return_value = resp
        session = RetryingSession()
        session.request("GET", "https://example.com")

        # Should set throttle with 5s default (no Reset header)
        assert session._rate_limit_until is not None

    @patch.object(requests.Session, "request")
    def test_unix_timestamp_reset(self, mock_request):
        """X-RateLimit-Reset as Unix timestamp (>1e9) -> absolute time."""
        future = time.time() + 60
        resp = MagicMock(
            status_code=200,
            headers={
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(future),
            },
        )
        mock_request.return_value = resp
        session = RetryingSession()
        session.request("GET", "https://example.com")

        assert session._rate_limit_until is not None
        # Should be close to the future timestamp
        assert abs(session._rate_limit_until - future) < 2

    @patch.object(requests.Session, "request")
    def test_millisecond_timestamp_reset(self, mock_request):
        """X-RateLimit-Reset as millisecond timestamp (>1e12) -> converted."""
        future_ms = (time.time() + 60) * 1000
        resp = MagicMock(
            status_code=200,
            headers={
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(future_ms),
            },
        )
        mock_request.return_value = resp
        session = RetryingSession()
        session.request("GET", "https://example.com")

        assert session._rate_limit_until is not None

    @patch.object(requests.Session, "request")
    def test_lowercase_header_names(self, mock_request):
        """Handles lowercase x-ratelimit-remaining header."""
        resp = MagicMock(
            status_code=200,
            headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "10"},
        )
        mock_request.return_value = resp
        session = RetryingSession()
        session.request("GET", "https://example.com")

        assert session._rate_limit_until is not None

    @patch.object(requests.Session, "request")
    def test_non_numeric_remaining_ignored(self, mock_request):
        """Non-numeric X-RateLimit-Remaining is silently ignored."""
        resp = MagicMock(
            status_code=200,
            headers={"X-RateLimit-Remaining": "abc"},
        )
        mock_request.return_value = resp
        session = RetryingSession()
        session.request("GET", "https://example.com")
        # No exception, no throttle set
        assert session._rate_limit_until is None

    @patch.object(requests.Session, "request")
    def test_200_without_ratelimit_headers(self, mock_request):
        """Normal 200 without rate limit headers -> no throttle."""
        resp = MagicMock(status_code=200, headers={})
        mock_request.return_value = resp
        session = RetryingSession()
        session.request("GET", "https://example.com")
        assert session._rate_limit_until is None
