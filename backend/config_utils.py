"""Path mapping utility — extracted from config.py for size management.

config.py re-exports map_path for backwards compatibility.
"""

import os


def is_under_folder(path: str, folder: str) -> bool:
    """Whether ``path`` is ``folder`` or inside it.

    A plain prefix test lets "/media/movies" match "/media/movies-4k/...": with
    several pairs that maps a library onto another library's root.
    """
    if not folder or not path.startswith(folder):
        return False
    rest = path[len(folder) :]
    return not rest or folder.endswith(("/", "\\")) or rest.startswith(("/", "\\"))


def map_path(path: str) -> str:
    """Map a remote file path to a local path using configured path mappings.

    Path mapping is configured via the SUBLARR_PATH_MAPPING setting:
    Format: "remote_prefix=local_prefix" (multiple pairs separated by semicolons)
    Example: "/data/media=/mnt/media;/anime=/share/anime"

    A pair matches whole folders only ("/data/movies" never rewrites
    "/data/movies-4k/..."), and the pair with the longest remote prefix wins,
    so a specific pair beats a general one in any order.

    On Windows, forward slashes in the mapped path are converted to backslashes.

    SECURITY NOTE: This function performs prefix replacement only.
    Callers that serve or delete files MUST validate the mapped result with
    ``security_utils.is_safe_path(mapped, media_path)`` before using it,
    to guard against path traversal after mapping.
    """
    from config import get_settings  # local import — prevents circular dep

    s = get_settings()
    mapping = s.path_mapping
    if not mapping:
        return path

    best = None
    for pair in mapping.split(";"):
        pair = pair.strip()
        if "=" not in pair:
            continue
        remote_prefix, local_prefix = pair.split("=", 1)
        remote_prefix = remote_prefix.strip()
        local_prefix = local_prefix.strip()
        if not remote_prefix or not local_prefix:
            continue
        if not is_under_folder(path, remote_prefix):
            continue
        if best is None or len(remote_prefix) > len(best[0]):
            best = (remote_prefix, local_prefix)

    if best is None:
        return path
    remote_prefix, local_prefix = best
    # Join at the folder boundary whichever side spells the trailing separator.
    mapped = local_prefix.rstrip("/\\") + path[len(remote_prefix.rstrip("/\\")) :]
    if os.name == "nt":
        mapped = mapped.replace("/", "\\")
    return mapped
