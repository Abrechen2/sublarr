"""Canonical security utility functions for Sublarr.

Centralizes path traversal prevention, ZIP extraction safety,
Git URL validation, URL SSRF validation, and environment variable sanitization.
All security-sensitive operations should use these helpers.
"""

import ipaddress
import os
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


def validate_service_url(url: str) -> tuple[bool, str | None]:
    """Validate that a service/provider URL is safe (SSRF prevention).

    Blocks dangerous schemes (file://, ftp://, gopher://, etc.) and
    cloud metadata endpoints while allowing private LAN addresses.

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

    if host == "0.0.0.0":
        return False, "0.0.0.0 is not a valid service host"

    # Block cloud metadata hostnames
    if host.lower() in _BLOCKED_METADATA_HOSTS:
        return False, f"Blocked metadata host: {host!r}"

    # Block dangerous IP addresses (urlparse strips brackets from IPv6 literals)
    try:
        addr = ipaddress.ip_address(host)
        if addr.is_link_local:
            return False, f"Link-local addresses are not allowed: {host!r}"
        for network in _METADATA_NETWORKS:
            if addr in network:
                return False, f"Blocked metadata IP range: {host!r}"
    except ValueError:
        pass  # hostname, not an IP — allowed

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
