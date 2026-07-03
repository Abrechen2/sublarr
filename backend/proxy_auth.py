"""Reverse-proxy header authentication helpers.

When enabled (UISettings.proxy_auth_enabled), a request is authenticated if its
DIRECT peer IP (``request.remote_addr`` — Sublarr applies no ProxyFix, so this
is the real TCP peer) is within an operator-configured trusted-proxy network
AND it carries a non-empty configured identity header (default ``Remote-User``).
Lets Authelia/authentik SSO satisfy the UI-auth gate. Fails closed on any
misconfiguration.
"""

from __future__ import annotations

import ipaddress
import logging

logger = logging.getLogger(__name__)

_Network = ipaddress.IPv4Network | ipaddress.IPv6Network


def parse_trusted_networks(raw: str) -> list[_Network]:
    """Parse comma-separated IPs/CIDRs into network objects.

    Bare IPs become host networks (/32 or /128). Invalid entries are skipped
    with a warning.
    """
    networks: list[_Network] = []
    for part in (raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            networks.append(ipaddress.ip_network(part, strict=False))
        except ValueError:
            logger.warning("Ignoring invalid trusted-proxy entry: %r", part)
    return networks


def ip_in_networks(ip_str: str | None, networks: list[_Network]) -> bool:
    """True if ip_str is a valid address contained in any of networks.

    Version mismatches (v4 address vs v6 network) return False, not an error.
    """
    if not ip_str:
        return False
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return any(ip in net for net in networks)


def request_has_valid_proxy_auth() -> bool:
    """True if the current request is authenticated via a trusted reverse proxy.

    All must hold: feature enabled → a non-empty trusted-proxy allowlist is
    configured → the request's direct peer IP is within it → the configured
    identity header is present and non-empty. Any failure → False (fail closed).
    """
    from flask import request

    from config import get_settings

    settings = get_settings()
    if not getattr(settings, "proxy_auth_enabled", False):
        return False
    networks = parse_trusted_networks(getattr(settings, "proxy_auth_trusted_ips", "") or "")
    if not networks:
        return False  # enabled but no allowlist → never trust (fail closed)
    if not ip_in_networks(request.remote_addr, networks):
        return False
    header_name = getattr(settings, "proxy_auth_header", "Remote-User") or "Remote-User"
    return bool(request.headers.get(header_name, "").strip())
