"""Outbound network policy for catalog (Provider Hub) bundle code.

The vendored bundles fetch with ``urllib.request`` and ``http.client``
themselves, and their files are pinned by SHA-256, so the download-URL guard
the built-in providers call (``validate_download_url``) cannot be added to
them. Instead, while bundle code runs inside ``outbound_guard``, a process
audit hook checks

- every ``urllib.Request`` (``OpenerDirector.open`` raises it once per
  request, and again for each redirect hop) against ``validate_hub_url``,
  which refuses ``file://`` and every other non-HTTP scheme;
- every ``socket.connect`` against ``check_hub_peer_ip``, using the address
  actually connected to — host names that resolve to loopback or the LAN,
  DNS rebinding and bundles using ``http.client`` directly are covered too;
- requests that would go through an HTTP proxy, and ``http.client``
  CONNECT tunnels: the proxy resolves the target itself, so no check made
  here can hold against DNS rebinding. Only literal IP targets (checked
  like any other) may be proxied; a proxied request to a host name is
  refused. The proxy host itself gets no allowance either — a catalog
  bundle behind a LAN-only proxy cannot work, by design.

Private/LAN addresses are refused except for the hosts the operator typed
into a bundle's server-address setting: only those hosts and the addresses
they resolve to, never the whole LAN.

A refused call raises ``HubNetworkBlockedError`` before anything is fetched
(Forgejo #54). The policy is per thread: Sublarr's own calls to Sonarr,
Jellyfin or a LAN translation backend on other threads are not affected.
Limit: a thread a bundle starts itself would run unguarded; no vendored
bundle starts one (checked when this guard was added).
"""

from __future__ import annotations

import ipaddress
import socket
import sys
import threading
import urllib.parse
import urllib.request
from collections.abc import Iterable
from contextlib import contextmanager
from dataclasses import dataclass

from providers.base import ProviderError
from security_utils import check_hub_peer_ip, validate_hub_url

_GUARDED_EVENTS = frozenset({"urllib.Request", "socket.connect", "http.client.connect"})
_INET_FAMILIES = (socket.AF_INET, socket.AF_INET6)

_state = threading.local()
_install_lock = threading.Lock()
_installed = False


class HubNetworkBlockedError(ProviderError):
    """A catalog bundle tried to reach a target the download policy refuses."""


@dataclass(frozen=True)
class _Policy:
    provider_name: str
    # Operator-chosen hosts (lower-case names or IP literals) and the
    # addresses they resolved to: the only private targets allowed.
    private_hosts: frozenset[str]
    private_ips: frozenset[str]
    via_proxy: bool


@contextmanager
def outbound_guard(provider_name: str, *, operator_urls: Iterable[str] = ()):
    """Apply the hub download policy to network calls made in this block.

    ``operator_urls`` are server addresses the operator configured for this
    bundle (Subsarr's ``base_url``): their hosts may be private/LAN, nothing
    else may. Loopback, link-local and metadata stay refused for every host,
    as for the self-hosted built-in providers.
    """
    _install_hook()
    hosts = _hosts_of(operator_urls)
    policy = _Policy(
        provider_name=provider_name,
        private_hosts=frozenset(hosts),
        private_ips=frozenset(ip for host in hosts for ip in _resolve_quietly(host)),
        via_proxy=bool(urllib.request.getproxies()),
    )
    previous = getattr(_state, "policy", None)
    _state.policy = policy
    try:
        yield
    finally:
        _state.policy = previous


def _hosts_of(urls: Iterable[str]) -> list[str]:
    hosts = []
    for url in urls:
        try:
            host = urllib.parse.urlparse(str(url or "").strip()).hostname
        except ValueError:
            continue
        if host:
            hosts.append(host.lower())
    return hosts


def _resolve_quietly(host: str) -> list[str]:
    # An operator host that does not resolve right now simply grants nothing;
    # the bundle's own connect attempt reports the failure.
    try:
        return _peer_addresses(host)
    except HubNetworkBlockedError:
        return []


def _install_hook() -> None:
    # An audit hook cannot be removed again, so it is added once, on first use:
    # an install that never enables a catalog provider never pays for it.
    global _installed
    if _installed:
        return
    with _install_lock:
        if not _installed:
            sys.addaudithook(_audit_hook)
            _installed = True


def _audit_hook(event: str, args: tuple) -> None:
    # Runs for every audit event in the process: return as early as possible.
    if event not in _GUARDED_EVENTS:
        return
    policy = getattr(_state, "policy", None)
    if policy is None:
        return
    if event == "urllib.Request":
        _check_url(policy, args[0])
    elif event == "http.client.connect":
        _check_tunnel(policy, args[0])
    else:
        _check_connect(policy, args[0], args[1])


def _check_url(policy: _Policy, url) -> None:
    url = str(url)
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    allow_private = host in policy.private_hosts
    ok, reason = validate_hub_url(url, allow_private=allow_private)
    if not ok:
        raise HubNetworkBlockedError(f"{policy.provider_name}: request blocked: {reason}")
    if policy.via_proxy and not _is_ip_literal(host) and not urllib.request.proxy_bypass(host):
        # The proxy, not Sublarr, resolves this name and connects; a check
        # made here could be rebound, and the socket check sees only the proxy.
        raise HubNetworkBlockedError(
            f"{policy.provider_name}: request blocked: a proxied request to host name "
            f"{host!r} cannot be checked"
        )


def _check_tunnel(policy: _Policy, conn) -> None:
    """An ``http.client`` CONNECT tunnel: the proxy connects to the tunnel host."""
    tunnel_host = getattr(conn, "_tunnel_host", None)
    if not tunnel_host:
        return
    tunnel_host = str(tunnel_host).strip("[]")
    if not _is_ip_literal(tunnel_host):
        raise HubNetworkBlockedError(
            f"{policy.provider_name}: proxy tunnel blocked: host name "
            f"{tunnel_host!r} cannot be checked"
        )
    _check_addresses(policy, tunnel_host, "proxy tunnel blocked")


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        return False
    return True


def _check_connect(policy: _Policy, sock, address) -> None:
    if getattr(sock, "family", None) not in _INET_FAMILIES or not isinstance(address, tuple):
        raise HubNetworkBlockedError(f"{policy.provider_name}: non-IP connection blocked")
    _check_addresses(policy, str(address[0]), "connection blocked")


def _check_addresses(policy: _Policy, host: str, what: str) -> None:
    """Every address ``host`` resolves to must pass; private only if operator-chosen."""
    for ip_text in _peer_addresses(host):
        ok, reason = check_hub_peer_ip(
            ipaddress.ip_address(ip_text),
            ip_text,
            allow_private=ip_text in policy.private_ips,
        )
        if not ok:
            raise HubNetworkBlockedError(f"{policy.provider_name}: {what}: {reason}")


def _peer_addresses(host: str) -> list[str]:
    """The IPs a connect to ``host`` may reach; a name is resolved (all answers)."""
    host = host.split("%", 1)[0]  # IPv6 zone id
    try:
        ipaddress.ip_address(host)
        return [host]
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        raise HubNetworkBlockedError(f"cannot resolve {host!r} to check it: {exc}") from exc
    return sorted({info[4][0].split("%", 1)[0] for info in infos})
