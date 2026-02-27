"""HTTP session with retry logic, backoff, and rate-limit awareness.

Adapted from Bazarr's RetryingSession pattern. Provides a requests.Session
wrapper that handles transient failures gracefully.
"""

import logging
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


def create_session(
    max_retries: int = 3,
    backoff_factor: float = 1.0,
    timeout: int = 15,
    user_agent: str = "Sublarr/1.0",
) -> "RetryingSession":
    """Create a configured RetryingSession."""
    session = RetryingSession(timeout=timeout)
    session.headers["User-Agent"] = user_agent

    retry_strategy = Retry(
        total=max_retries,
        backoff_factor=backoff_factor,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    return session


class RetryingSession(requests.Session):
    """Session with default timeout and rate-limit awareness."""

    def __init__(self, timeout: int = 15):
        super().__init__()
        self.default_timeout = timeout
        self._rate_limit_until: float | None = None

    def request(self, method, url, **kwargs):
        # Apply default timeout
        if "timeout" not in kwargs:
            kwargs["timeout"] = self.default_timeout

        # Rate limit check
        if self._rate_limit_until and time.time() < self._rate_limit_until:
            wait = self._rate_limit_until - time.time()
            logger.debug("Rate limited, waiting %.1fs", wait)
            time.sleep(wait)

        try:
            resp = super().request(method, url, **kwargs)
        except requests.ConnectionError as e:
            logger.warning("Connection error for %s %s: %s", method, url, e)
            raise
        except requests.Timeout:
            logger.warning("Timeout for %s %s", method, url)
            raise

        # Handle rate limiting
        if resp.status_code == 429:
            from providers.base import ProviderRateLimitError
            retry_after = resp.headers.get("Retry-After")
            if retry_after:
                try:
                    wait_seconds = int(retry_after)
                except ValueError:
                    wait_seconds = 60
            else:
                wait_seconds = 60
            self._rate_limit_until = time.time() + wait_seconds
            logger.warning("Rate limited by %s, waiting %ds", url, wait_seconds)
            raise ProviderRateLimitError(f"Rate limited by {url}, retry after {wait_seconds}s")

        # Handle auth errors
        if resp.status_code in (401, 403):
            from providers.base import ProviderAuthError
            raise ProviderAuthError(f"Authentication failed for {url}: HTTP {resp.status_code}")

        # Check remaining rate limit headers
        remaining = resp.headers.get("X-RateLimit-Remaining") or resp.headers.get("x-ratelimit-remaining")
        if remaining is not None:
            try:
                if int(remaining) <= 1:
                    reset_at = resp.headers.get("X-RateLimit-Reset") or resp.headers.get("x-ratelimit-reset")
                    if reset_at:
                        try:
                            reset_value = float(reset_at)
                            current_time = time.time()
                            # Check if it's a Unix timestamp (seconds or milliseconds)
                            # Unix timestamps are typically > 1000000000 (year 2001)
                            if reset_value > 1000000000:
                                # Could be seconds or milliseconds
                                if reset_value > 1e12:
                                    # Likely milliseconds, convert to seconds
                                    reset_value = reset_value / 1000.0
                                # Use as absolute timestamp
                                self._rate_limit_until = reset_value
                            else:
                                # Relative seconds from now
                                self._rate_limit_until = current_time + reset_value
                        except (ValueError, TypeError):
                            # Fallback: wait 5 seconds
                            self._rate_limit_until = time.time() + 5
                    else:
                        self._rate_limit_until = time.time() + 5
            except (ValueError, TypeError):
                pass

        return resp
