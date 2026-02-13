"""HTTP session with retry logic, backoff, and rate-limit awareness.

Adapted from Bazarr's RetryingSession pattern. Provides a requests.Session
wrapper that handles transient failures gracefully.
"""

import time
import logging
from typing import Optional

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
        self._rate_limit_until: Optional[float] = None

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

        # Check remaining rate limit headers
        remaining = resp.headers.get("X-RateLimit-Remaining") or resp.headers.get("x-ratelimit-remaining")
        if remaining is not None:
            try:
                if int(remaining) <= 1:
                    reset_at = resp.headers.get("X-RateLimit-Reset") or resp.headers.get("x-ratelimit-reset")
                    if reset_at:
                        self._rate_limit_until = float(reset_at)
                    else:
                        self._rate_limit_until = time.time() + 5
            except (ValueError, TypeError):
                pass

        return resp
