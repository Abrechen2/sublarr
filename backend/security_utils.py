"""Canonical security utility functions for Sublarr.

Centralizes path traversal prevention, ZIP extraction safety,
Git URL validation, URL SSRF validation, and environment variable sanitization.
All security-sensitive operations should use these helpers.
"""

import ipaddress
import os
import socket
import urllib.parse
import zipfile

# Domains allowed for git-based plugin installation
_ALLOWED_GIT_DOMAINS = {"github.com", "gitlab.com", "codeberg.org"}

# Schemes allowed for service/provider URLs
_ALLOWED_SERVICE_SCHEMES = {"http", "https"}

# Cloud metadata hostnames that must always be blocked
_BLOCKED_METADATA_HOSTS = {"metadata.google.internal", "metadata.goog"}

# Metadata IP ranges (link-local 169.254.x.x, Alibaba 100.100.100.200)
_METADATA_NETWORKS = [
    ipaddress.ip_network("169.254.0.0/16"),  # AWS / Azure / GCP link-local
    ipaddress.ip_network("100.100.100.200/32"),  # Alibaba Cloud metadata
]


# ---------------------------------------------------------------------------
# Per-provider domain allowlists for subtitle download URLs (P1)
# ---------------------------------------------------------------------------

# Providers that perform all downloads locally (no external URL needed).
_LOCAL_PROVIDERS = {"embedded", "whisper"}

# Providers that are self-hosted (operator chooses the URL).
# Scheme must be http/https, but any hostname is accepted.
# The generic Custom HTTP/JSON provider ("customapi") and its dynamically
# registered instances ("customapi-<name>") fall in this class too.
_SELF_HOSTED_PROVIDERS = {"subsdump", "customapi"}


def _is_self_hosted_provider(provider_name: str) -> bool:
    return provider_name in _SELF_HOSTED_PROVIDERS or provider_name.startswith("customapi-")

# Allowlists: a URL is accepted when netloc equals entry OR ends with ".<entry>".
_PROVIDER_DOWNLOAD_DOMAINS: dict[str, set[str]] = {
    "opensubtitles": {"opensubtitles.com", "opensubtitles.org"},
    "podnapisi": {"podnapisi.net"},
    "jimaku": {"jimaku.cc"},
    "addic7ed": {"addic7ed.com"},
    "betaseries": {"betaseries.com"},
    "gestdown": {"gestdown.info"},
    "kitsunekko": {"kitsunekko.net"},
    "legendasdivx": {"legendasdivx.pt"},
    "napisy24": {"napisy24.pl"},
    "subdl": {"subdl.com"},
    "animetosho": {"animetosho.org"},
    "subf2m": {"subf2m.co"},
    "subsource": {"subsource.net"},
    "titlovi": {"titlovi.com"},
    "titrari": {"titrari.ro"},
    "tvsubtitles": {"tvsubtitles.net"},
    "turkcealtyazi": {"turkcealtyazi.org"},
    "yifysubtitles": {"yifysubtitles.ch"},
    "zimuku": {"zimuku.net"},
}


def validate_download_url(url: str, provider_name: str) -> tuple[bool, str | None]:
    """Validate that a provider download URL points to an allowed domain (P1 SSRF guard).

    Returns:
        (True, None) if the URL is safe to fetch.
        (False, reason) if the URL should be rejected.
    """
    if provider_name in _LOCAL_PROVIDERS:
        return True, None

    if _is_self_hosted_provider(provider_name):
        if not url:
            return False, "Self-hosted provider download URL must not be empty"
        try:
            parsed = urllib.parse.urlparse(url)
        except Exception:
            return False, "URL could not be parsed"
        if parsed.scheme not in _ALLOWED_SERVICE_SCHEMES:
            return False, f"Invalid scheme {parsed.scheme!r} — only http/https are allowed"
        host = parsed.hostname
        if not host:
            return False, "URL has no hostname"
        if host.lower() in _BLOCKED_METADATA_HOSTS:
            return False, f"Blocked metadata host: {host!r}"
        try:
            addr = ipaddress.ip_address(host)
            if addr.is_link_local or addr.is_loopback:
                return False, f"Link-local/loopback addresses are not allowed: {host!r}"
            for network in _METADATA_NETWORKS:
                if addr in network:
                    return False, f"Blocked metadata IP range: {host!r}"
        except ValueError:
            pass  # hostname, not an IP — OK
        return True, None

    allowed_domains = _PROVIDER_DOWNLOAD_DOMAINS.get(provider_name)
    if allowed_domains is None:
        return False, f"Unknown provider {provider_name!r} — no download domain allowlist defined"

    if not url:
        return False, "Download URL must not be empty"

    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return False, "URL could not be parsed"

    if parsed.scheme not in _ALLOWED_SERVICE_SCHEMES:
        return False, f"Invalid scheme {parsed.scheme!r} — only http/https are allowed"

    host = parsed.hostname
    if not host:
        return False, "URL has no hostname"

    if host.lower() in _BLOCKED_METADATA_HOSTS:
        return False, f"Blocked metadata host: {host!r}"
    try:
        addr = ipaddress.ip_address(host)
        if addr.is_link_local:
            return False, f"Link-local addresses are not allowed: {host!r}"
        for network in _METADATA_NETWORKS:
            if addr in network:
                return False, f"Blocked metadata IP range: {host!r}"
    except ValueError:
        pass

    netloc = host.lower()
    for allowed in allowed_domains:
        if netloc == allowed or netloc.endswith("." + allowed):
            return True, None

    return False, (
        f"Download URL domain {netloc!r} is not in the allowlist for provider {provider_name!r}"
    )


def safe_subprocess_arg(path: str) -> str:
    """Return ``path`` made safe to pass as a positional argv to an external
    binary, by prefixing ``./`` when a *relative* path's basename starts with
    ``-``.

    subprocess with a list avoids shell parsing, but the called binary still
    does its own getopt-style flag parsing, so a file literally named
    ``-i.mkv`` would be mistaken for a flag. Prefixing ``./`` keeps the path
    semantically identical while removing the ambiguity. Absolute paths (which
    start with the path separator, not ``-``) are returned unchanged.
    """
    if not path:
        return path
    if os.path.isabs(path):
        return path
    base = os.path.basename(path)
    if base.startswith("-"):
        return os.path.join(".", path)
    return path


def is_safe_path(file_path: str, base_dir: str) -> bool:
    """Return True iff file_path resolves inside base_dir (symlinks resolved).

    Args:
        file_path: Path to validate.
        base_dir: Allowed base directory.

    Returns:
        True if file_path is inside base_dir after resolving symlinks.
    """
    real_path = os.path.realpath(file_path)
    real_base = os.path.realpath(base_dir)
    # Normalize real_base to always end with sep so startswith works correctly
    # for root paths like "E:\" that already end with the separator.
    if not real_base.endswith(os.sep):
        real_base = real_base + os.sep
    return real_path.startswith(real_base) or real_path + os.sep == real_base


def safe_zip_extract(zip_file: zipfile.ZipFile, dest_dir: str) -> None:
    """Extract zip_file into dest_dir, rejecting any ZIP Slip entries.

    Args:
        zip_file: Open ZipFile object.
        dest_dir: Target extraction directory.

    Raises:
        ValueError: If any entry resolves outside dest_dir (ZIP Slip).
    """
    dest_real = os.path.realpath(dest_dir)
    for member in zip_file.namelist():
        target = os.path.realpath(os.path.join(dest_real, member))
        if not (target.startswith(dest_real + os.sep) or target == dest_real):
            raise ValueError(f"ZIP Slip detected: {member!r}")
    zip_file.extractall(dest_dir)


def _normalise_to_ip(host: str) -> "ipaddress.IPv4Address | ipaddress.IPv6Address | None":
    """Coerce ``host`` into a canonical ``IPv4Address``/``IPv6Address`` if possible.

    Handles bypass-prone forms that ``ipaddress.ip_address`` rejects out of
    the box (pentest 2026-05-08 finding):
    - Decimal-encoded IPv4: ``"2130706433"`` (= 127.0.0.1) and ``"2852039166"``
      (= 169.254.169.254 / AWS metadata).
    - Octal/hex IPv4: ``"0177.0.0.1"``, ``"0x7f.0.0.1"``.
    - IPv4-mapped IPv6: ``"::ffff:127.0.0.1"`` is unwrapped to its v4 form so
      loopback/link-local checks fire.

    Returns ``None`` for true hostnames (DNS) — caller decides how to handle.
    """
    # First try canonical dotted-decimal / canonical IPv6.
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        addr = None

    if addr is None:
        # Try non-canonical IPv4 forms (octal, hex, decimal int).
        # socket.inet_aton accepts decimal int strings, octal "0177.0.0.1",
        # and hex "0x7f.0.0.1". A pure host name still raises OSError.
        try:
            packed = socket.inet_aton(host)
            addr = ipaddress.IPv4Address(packed)
        except OSError:
            return None

    # Unwrap IPv4-mapped IPv6 ("::ffff:127.0.0.1" or "::ffff:7f00:1") so
    # the loopback / metadata checks see the underlying IPv4.
    if isinstance(addr, ipaddress.IPv6Address):
        v4 = addr.ipv4_mapped
        if v4 is not None:
            return v4

    return addr


def validate_service_url(url: str) -> tuple[bool, str | None]:
    """Validate that a service/provider URL is safe (SSRF prevention).

    Blocks dangerous schemes (file://, ftp://, gopher://, etc.), cloud
    metadata endpoints, loopback addresses, link-local addresses, and the
    unspecified address (0.0.0.0 / ::). Private LAN addresses (RFC 1918)
    are allowed because Sublarr's primary use case is reaching homelab
    Sonarr/Radarr/Ollama instances on 10/8, 172.16/12, 192.168/16.

    Hostname resolution: when ``host`` is a DNS name we resolve it to all
    A/AAAA records and re-run the IP checks against each — this catches
    "localhost", "metadata.google.internal" pointing at metadata, etc.
    DNS rebinding (validate-time vs fetch-time mismatch) is NOT prevented
    here; the caller is expected to pin the resolved IP if that matters.

    Args:
        url: URL to validate (e.g. Sonarr, Radarr, Ollama endpoint).

    Returns:
        (True, None) if the URL is acceptable.
        (False, reason) if the URL is rejected, where reason is a human-readable string.
    """
    if not url:
        return False, "URL must not be empty"

    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return False, "URL could not be parsed"

    if parsed.scheme not in _ALLOWED_SERVICE_SCHEMES:
        return False, f"Invalid scheme {parsed.scheme!r} — only http/https are allowed"

    host = parsed.hostname
    if not host:
        return False, "URL has no hostname"

    # Block cloud metadata hostnames before any IP coercion.
    if host.lower() in _BLOCKED_METADATA_HOSTS:
        return False, f"Blocked metadata host: {host!r}"

    # Try to coerce the host into an IP, including non-canonical forms
    # (decimal/octal/hex IPv4, IPv4-mapped IPv6) that the original
    # urlparse → ip_address pipeline silently allowed (pentest finding).
    addr = _normalise_to_ip(host)

    if addr is not None:
        ok, reason = _check_ip_address(addr, host)
        if not ok:
            return False, reason
        return True, None

    # Hostname (not an IP literal) — resolve and re-check every answer.
    # Fail-open on DNS resolution errors so legitimate homelab hostnames
    # like ``sonarr.local`` (mDNS only resolvable on the home LAN, not on
    # the dev/CI box) still pass validation. The trade-off: an attacker
    # who controls a hostname can theoretically register an A record only
    # at fetch-time (DNS rebinding) to bypass — caller pins the resolved
    # IP if that matters. Documented as deferred above.
    try:
        infos = socket.getaddrinfo(host, parsed.port or None, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, OSError):
        return True, None

    seen: set[str] = set()
    for info in infos:
        sockaddr = info[4]
        ip_str = sockaddr[0]
        if ip_str in seen:
            continue
        seen.add(ip_str)
        try:
            resolved = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if isinstance(resolved, ipaddress.IPv6Address) and resolved.ipv4_mapped is not None:
            resolved = resolved.ipv4_mapped
        ok, reason = _check_ip_address(resolved, f"{host} ({ip_str})")
        if not ok:
            return False, reason

    return True, None


def _check_ip_address(addr, label: str) -> tuple[bool, str | None]:
    """Return (False, reason) for any IP class we never want service URLs to point at.

    Used by ``validate_service_url`` for both literal IPs and DNS-resolved
    hostnames so the bypass surface is identical no matter how the host
    was expressed in the URL.
    """
    if addr.is_unspecified:
        return False, f"Unspecified address (0.0.0.0 / ::) is not a valid service host: {label!r}"
    if addr.is_loopback:
        return False, f"Loopback addresses are not allowed: {label!r}"
    if addr.is_link_local:
        return False, f"Link-local addresses are not allowed: {label!r}"
    for network in _METADATA_NETWORKS:
        if addr in network:
            return False, f"Blocked metadata IP range: {label!r}"
    return True, None


def validate_git_url(url: str) -> None:
    """Validate that a Git repository URL is safe to clone.

    Only HTTPS URLs on allow-listed domains are permitted.

    Args:
        url: Git repository URL to validate.

    Raises:
        ValueError: If the URL uses a non-HTTPS scheme or a non-allowed domain.
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"Git URL must use HTTPS, got: {parsed.scheme!r}")
    domain = parsed.netloc.lower().split(":")[0]
    if not any(domain == d or domain.endswith("." + d) for d in _ALLOWED_GIT_DOMAINS):
        raise ValueError(f"Git URL domain not in allowlist: {domain!r}")


def sanitize_env_value(value: str) -> str:
    """Sanitize a string for safe use as an environment variable value.

    Strips newlines and null bytes that could enable env-var injection,
    and truncates to a safe maximum length.

    Args:
        value: Raw string to sanitize.

    Returns:
        Sanitized string safe for use as an env var value.
    """
    return value.replace("\n", " ").replace("\r", " ").replace("\x00", "")[:1024]
