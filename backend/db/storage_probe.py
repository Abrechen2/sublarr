"""Startup probe: warn when SQLite sits on slow storage (SD card / network share).

The single most common cause of "Sublarr is painfully slow" reports is a SQLite
database living on a microSD card or an NFS/SMB share, where per-commit fsync
latency dominates every request. PostgreSQL users are unaffected (the pool and
the server absorb it). This probe times a handful of *committed* writes against
the real database file at startup and logs a one-line WARNING with remediation
when the median commit latency crosses a threshold — so self-hosters can
diagnose it themselves instead of filing a vague bug report.

The probe is best-effort: any failure is swallowed so it can never break
startup, and it only runs for SQLite backends.
"""

import logging
import time

from sqlalchemy import text

logger = logging.getLogger(__name__)

# Median committed-write latency (ms) above which the storage is flagged slow.
# SSD/NVMe commits land in ~1-5 ms; a microSD card or network share is typically
# 30-200+ ms. 25 ms sits comfortably above SSD noise and below SD-card pain, so
# it flags the genuinely-slow volumes without false-positiving on decent disks.
SLOW_STORAGE_THRESHOLD_MS = 25.0

_PROBE_SAMPLES = 5
_PROBE_TABLE = "_sublarr_storage_probe"


def measure_commit_latency_ms(engine, samples: int = _PROBE_SAMPLES) -> float | None:
    """Return the median per-commit latency in ms for ``samples`` tiny writes.

    Writes into a dedicated throwaway table in the *main* database (not a TEMP
    table — TEMP storage bypasses the WAL fsync we are trying to measure), each
    row committed individually so every sample exercises a real fsync on the
    ``/config`` volume. The table is dropped afterwards.

    Returns ``None`` when the probe cannot run (any error) — a diagnostic must
    never break startup.
    """
    try:
        timings: list[float] = []
        with engine.connect() as conn:
            conn.execute(text(f"CREATE TABLE IF NOT EXISTS {_PROBE_TABLE} (v INTEGER)"))
            conn.commit()
            for i in range(samples):
                start = time.perf_counter()
                conn.execute(text(f"INSERT INTO {_PROBE_TABLE} (v) VALUES (:v)"), {"v": i})
                conn.commit()
                timings.append((time.perf_counter() - start) * 1000.0)
            conn.execute(text(f"DROP TABLE IF EXISTS {_PROBE_TABLE}"))
            conn.commit()
        if not timings:
            return None
        timings.sort()
        return timings[len(timings) // 2]
    except Exception as e:  # pragma: no cover - defensive; probe must not throw
        logger.debug("Storage probe skipped: %s", e)
        return None


def warn_if_slow_storage(engine) -> float | None:
    """Measure SQLite commit latency and log a WARNING when the volume is slow.

    Returns the measured median latency in ms (or ``None`` if the probe could
    not run) so callers/tests can assert on it.
    """
    latency = measure_commit_latency_ms(engine)
    if latency is None:
        return None
    if latency >= SLOW_STORAGE_THRESHOLD_MS:
        logger.warning(
            "SQLite write latency is %.0f ms/commit — this storage is slow "
            "(SSD/NVMe is <5 ms). If Sublarr feels sluggish, move the /config "
            "volume off a microSD card or network share (NFS/SMB) onto an SSD, "
            "or switch to PostgreSQL. Docs: https://sublarr.de/docs/getting-started/installation/",
            latency,
        )
    else:
        logger.info("Storage probe: SQLite commit latency %.1f ms (ok)", latency)
    return latency
