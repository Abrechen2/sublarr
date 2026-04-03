"""Path mapping utility — extracted from config.py for size management.

config.py re-exports map_path for backwards compatibility.
"""

import os


def map_path(path: str) -> str:
    """Map a remote file path to a local path using configured path mappings.

    Path mapping is configured via the SUBLARR_PATH_MAPPING setting:
    Format: "remote_prefix=local_prefix" (multiple pairs separated by semicolons)
    Example: "/data/media=/mnt/media;/anime=/share/anime"

    On Windows, forward slashes in the mapped path are converted to backslashes.

    SECURITY NOTE: This function performs string-based prefix replacement only.
    Callers that serve or delete files MUST validate the mapped result with
    ``security_utils.is_safe_path(mapped, media_path)`` before using it,
    to guard against path traversal after mapping.
    """
    from config import get_settings  # local import — prevents circular dep

    s = get_settings()
    mapping = s.path_mapping
    if not mapping:
        return path

    for pair in mapping.split(";"):
        pair = pair.strip()
        if "=" not in pair:
            continue
        remote_prefix, local_prefix = pair.split("=", 1)
        remote_prefix = remote_prefix.strip()
        local_prefix = local_prefix.strip()
        if not remote_prefix or not local_prefix:
            continue

        if path.startswith(remote_prefix):
            mapped = local_prefix + path[len(remote_prefix) :]
            if os.name == "nt":
                mapped = mapped.replace("/", "\\")
            return mapped

    return path
