"""Canonical security utility functions for Sublarr.

Centralizes path traversal prevention, ZIP extraction safety,
Git URL validation, service URL validation, and environment variable sanitization.
All security-sensitive operations should use these helpers.
"""

import ipaddress
import os
import urllib.parse
import zipfile

# Domains allowed for git-based plugin installation
_ALLOWED_GIT_DOMAINS = {"github.com", "gitlab.com", "codeberg.org"}


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


# Schemes that are safe for outbound HTTP service connections
_ALLOWED_SERVICE_SCHEMES = {"http", "https"}

# Cloud/hypervisor metadata IPs that must never be contacted
_METADATA_IPS = {
    "169.254.169.254",  # AWS / Azure / GCP / OpenStack instance metadata
    "fd00:ec2::254",  # AWS IPv6 metadata
    "100.100.100.200",  # Alibaba Cloud metadata
}

# Hostnames that resolve to cloud metadata endpoints
_METADATA_HOSTNAMES = {
    "metadata.google.internal",
    "metadata.goog",
}


def validate_service_url(url: str) -> tuple[bool, str | None]:
    """Validate a URL that the app will use to contact an external service.

    Rules (designed for internal Homelab services like Sonarr/Radarr/Ollama):
    - Scheme must be http or https (blocks file://, ftp://, dict://, gopher://)
    - Hostname must be present and not 0.0.0.0
    - Cloud metadata IPs/hostnames are blocked (169.254.169.254 etc.)

    Private IP ranges (192.168.x.x, 10.x.x.x, 172.16-31.x.x) are explicitly
    allowed because internal services run there.

    Args:
        url: URL string to validate.

    Returns:
        (True, None) if valid; (False, reason_string) if invalid.
    """
    if not url or not url.strip():
        return False, "URL must not be empty"

    try:
        parsed = urllib.parse.urlparse(url.strip())
    except Exception:
        return False, "Malformed URL"

    if parsed.scheme not in _ALLOWED_SERVICE_SCHEMES:
        return False, f"Scheme '{parsed.scheme}' is not allowed; use http or https"

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return False, "URL must include a hostname"

    if hostname == "0.0.0.0":
        return False, "0.0.0.0 is not a valid service host"

    if hostname in _METADATA_HOSTNAMES:
        return False, f"Metadata endpoint '{hostname}' is not allowed"

    try:
        addr = ipaddress.ip_address(hostname)
        if str(addr) in _METADATA_IPS:
            return False, f"Metadata IP {addr} is not allowed"
        if addr.is_link_local:
            return False, f"Link-local address {addr} is not allowed"
    except ValueError:
        # Not an IP address — domain name, which is fine
        pass

    return True, None


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
