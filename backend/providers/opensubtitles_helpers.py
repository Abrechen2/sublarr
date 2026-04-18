"""Pure helpers + constants for OpenSubtitlesProvider.

Extracted from providers/opensubtitles.py. Covers the module-level
scaffolding that doesn't depend on the provider instance:

- ``API_BASE`` endpoint
- ``_FORMAT_MAP`` — API format string → SubtitleFormat enum
- ``_UPLOADER_RANK_BONUS`` — uploader rank string → trust-score bonus
- ``_compute_opensubtitles_hash(filepath)`` — OpenSubtitles-style file
  hash (first + last 64 KB chunk + file size, mod 2**64)
"""

import os

from providers.base import SubtitleFormat

API_BASE = "https://api.opensubtitles.com/api/v1"

# Map common format strings to SubtitleFormat
_FORMAT_MAP = {
    "srt": SubtitleFormat.SRT,
    "ass": SubtitleFormat.ASS,
    "ssa": SubtitleFormat.SSA,
    "vtt": SubtitleFormat.VTT,
}

# Uploader rank to trust-bonus mapping (0-20 scale)
_UPLOADER_RANK_BONUS: dict[str, float] = {
    "administrator": 20.0,
    "platinum": 20.0,
    "gold": 15.0,
    "silver": 10.0,
    "bronze": 5.0,
    "trusted": 5.0,
}


def _compute_opensubtitles_hash(filepath: str) -> str:
    """Compute OpenSubtitles-style file hash.

    Based on first and last 64KB of the file + file size.
    """
    block_size = 65536
    file_size = os.path.getsize(filepath)

    if file_size < block_size * 2:
        return ""

    hash_val = file_size

    try:
        with open(filepath, "rb") as f:
            # First 64KB
            for _ in range(block_size // 8):
                buf = f.read(8)
                hash_val += int.from_bytes(buf, byteorder="little", signed=False)
                hash_val &= 0xFFFFFFFFFFFFFFFF

            # Last 64KB
            f.seek(-block_size, 2)
            for _ in range(block_size // 8):
                buf = f.read(8)
                hash_val += int.from_bytes(buf, byteorder="little", signed=False)
                hash_val &= 0xFFFFFFFFFFFFFFFF

        return f"{hash_val:016x}"
    except Exception:
        return ""
