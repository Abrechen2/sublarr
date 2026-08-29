"""Name what went wrong when a provider call failed.

"Unhealthy" is not an answer anybody can act on. A rejected key, a host that
no longer resolves and a rate limit need three different responses, and the
panel could not tell them apart because every failure arrived as the same
boolean (#201).

Exception type first, message second. The type is the reliable signal; the
string check exists for the case the reporting install actually hit —
podnapisi.net stopped resolving, and requests wraps that in a generic
ConnectionError whose class says nothing.
"""

from __future__ import annotations

#: Stored on provider_stats.last_failure_kind and mapped to a status_reason.
FAILURE_KINDS = ("auth", "network", "rate_limit", "timeout", "other")

_NETWORK_MARKERS = (
    "nameresolutionerror",
    "name or service not known",
    "temporary failure in name resolution",
    "failed to resolve",
    "connection refused",
    "network is unreachable",
    "no route to host",
    "max retries exceeded",
)

_AUTH_MARKERS = (
    "401",
    "403",
    "unauthorized",
    "forbidden",
    "invalid api key",
    "authentication failed",
)


def classify_provider_error(exc: BaseException) -> str:
    """Return one of ``FAILURE_KINDS`` for a provider exception."""
    from providers.base import (
        ProviderAuthError,
        ProviderRateLimitError,
        ProviderTimeoutError,
    )

    if isinstance(exc, ProviderAuthError):
        return "auth"
    if isinstance(exc, ProviderRateLimitError):
        return "rate_limit"
    if isinstance(exc, ProviderTimeoutError | TimeoutError):
        return "timeout"

    # Walk the cause chain: requests wraps the interesting exception, and the
    # outer class is usually the uninformative one.
    seen: list[str] = []
    cursor: BaseException | None = exc
    depth = 0
    while cursor is not None and depth < 5:
        seen.append(f"{type(cursor).__name__} {cursor}".lower())
        cursor = cursor.__cause__ or cursor.__context__
        depth += 1
    haystack = " ".join(seen)

    if any(marker in haystack for marker in _NETWORK_MARKERS):
        return "network"
    if any(marker in haystack for marker in _AUTH_MARKERS):
        return "auth"
    if "timeout" in haystack or "timed out" in haystack:
        return "timeout"
    return "other"
