"""Canonical security utility functions for Sublarr.

Centralizes path traversal prevention, ZIP extraction safety,
Git URL validation, and environment variable sanitization.
All security-sensitive operations should use these helpers.
"""

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
    return real_path.startswith(real_base + os.sep) or real_path == real_base


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
    if not any(
        domain == d or domain.endswith("." + d) for d in _ALLOWED_GIT_DOMAINS
    ):
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
