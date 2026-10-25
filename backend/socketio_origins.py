"""Origin check for the Socket.IO / Engine.IO handshake.

The browser opens Socket.IO on its own origin (``io(window.location.origin)``),
so the connection Sublarr has to accept is the one whose ``Origin`` matches the
host the browser used — whatever that is: localhost, a LAN IP, a domain. A
fixed allowlist cannot know that, which is why live updates silently failed
for every install not opened via localhost (Forgejo #60).

Rules:
- An ``Origin`` whose host[:port] equals the request's ``Host`` header is
  always allowed (scheme http or https — a TLS-terminating proxy forwards
  ``https://host`` to a backend that itself sees plain http).
- ``SUBLARR_CORS_ORIGINS`` adds foreign origins on top; ``*`` allows all.
- ``X-Forwarded-Host`` / ``X-Forwarded-Proto`` are deliberately ignored.
  Sublarr applies no ProxyFix (see proxy_auth.py), so these headers are
  client-controlled and must not widen the check. A reverse proxy therefore
  has to forward the original ``Host`` (Traefik and Caddy do by default;
  nginx needs ``proxy_set_header Host $http_host;``), or the public origin
  goes into ``SUBLARR_CORS_ORIGINS``.

Requests without an ``Origin`` header (non-browser clients) are not checked
by Engine.IO at all; the Socket.IO connect handler still authenticates them.
"""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import urlsplit

_DEFAULT_PORTS = {"http": 80, "https": 443}

OriginChecker = Callable[[str | None, dict], bool]


def _split_host(host: str) -> tuple[str, int | None] | None:
    """Split a Host header value into (lowercased hostname, port or None)."""
    try:
        parts = urlsplit(f"//{host.strip()}")
        return (parts.hostname or "", parts.port)
    except ValueError:
        return None


def is_same_origin(origin: str | None, host: str | None) -> bool:
    """True if ``origin`` names the same host and port as the ``Host`` header."""
    if not origin or not host:
        return False
    try:
        parts = urlsplit(origin.strip())
        origin_port = parts.port
    except ValueError:
        return False
    scheme = parts.scheme.lower()
    if scheme not in _DEFAULT_PORTS or not parts.hostname:
        return False
    host_parts = _split_host(host)
    if host_parts is None or not host_parts[0]:
        return False
    host_name, host_port = host_parts
    if parts.hostname != host_name:
        return False
    effective_origin_port = origin_port or _DEFAULT_PORTS[scheme]
    if host_port is None:
        # A Host header without a port means the scheme's default port.
        return effective_origin_port == _DEFAULT_PORTS[scheme]
    return effective_origin_port == host_port


def _normalise(origin: str) -> str:
    return origin.strip().rstrip("/").lower()


def build_origin_checker(raw: str) -> OriginChecker | str:
    """Build the ``cors_allowed_origins`` value for Socket.IO from the setting.

    Returns ``"*"`` when the configured list contains a wildcard, otherwise a
    callable ``(origin, environ) -> bool`` that python-engineio (>= 4.x) calls
    with the WSGI environ.
    """
    extra = {_normalise(o) for o in (raw or "").split(",") if o.strip()}
    if "*" in extra:
        return "*"
    allowed = frozenset(extra)

    def _check(origin: str | None, environ: dict) -> bool:
        if not origin:
            return False
        if _normalise(origin) in allowed:
            return True
        return is_same_origin(origin, environ.get("HTTP_HOST"))

    return _check
