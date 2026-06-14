"""Size-aware subprocess timeouts for large-file I/O operations.

Remuxing or audio-syncing a large video means reading and rewriting the
whole file. On a spinning-disk array (~30-50 MB/s sustained, slower with
parity) a 25 GB remux needs ~10 min of pure I/O — far beyond a fixed
600 s ceiling. Hardcoded timeouts therefore false-fail big files on every
run (observed: a 25 GB Remux-1080p movie timing out on both mkvmerge and
ffsubsync, left untouched each cleanup cycle).

``compute_io_timeout`` derives a per-file timeout from the input size:

    timeout = clamp(base + size_gb * per_gb, floor, cap)

Defaults are tuned for a spinning NAS array:
  - ``base`` 300 s   — fixed overhead (scan, container parse, startup)
  - ``per_gb`` 60 s  — ~17 MB/s worst-case sustained read+write per GB
  - ``floor`` 600 s  — never below the legacy ceiling (no regression)
  - ``cap`` 3600 s   — hard upper bound so a genuine zombie still dies

A 25 GB file resolves to ``300 + 25*60 = 1800 s`` (30 min). Missing or
unstattable paths fall back to ``floor``.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_BYTES_PER_GB = 1024**3


def compute_io_timeout(
    path: str,
    *,
    base: int = 300,
    per_gb: int = 60,
    floor: int = 600,
    cap: int = 3600,
) -> int:
    """Return a size-aware subprocess timeout in seconds for ``path``.

    The result is always within ``[floor, cap]``. If the file size cannot
    be determined (missing path, OSError), ``floor`` is returned so the
    call behaves exactly like the legacy fixed timeout.
    """
    try:
        size_bytes = os.path.getsize(path)
    except OSError:
        logger.debug("compute_io_timeout: cannot stat %s, using floor=%ds", path, floor)
        return floor

    size_gb = size_bytes / _BYTES_PER_GB
    scaled = int(base + size_gb * per_gb)
    return max(floor, min(cap, scaled))
