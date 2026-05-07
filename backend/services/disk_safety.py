"""Disk-pressure helpers for safety valves.

Used by ``wanted_search_runner.run_wanted_search`` (and other recurring
jobs that touch /config or /media) to early-exit when the underlying
device is so full that another download would push the host into a
broken state.

Read-only; no side effects beyond the ``shutil.disk_usage`` syscall.
"""

import logging
import shutil

logger = logging.getLogger(__name__)


def get_disk_usage_pct(path: str) -> float | None:
    """Return used-space percentage (0–100) for the device hosting ``path``.

    Returns ``None`` when the path does not exist, the syscall fails, or the
    device reports a zero total (degenerate filesystem).
    """
    try:
        stat = shutil.disk_usage(path)
    except (OSError, FileNotFoundError) as exc:
        logger.debug("disk_usage(%s) failed: %s", path, exc)
        return None
    if stat.total <= 0:
        return None
    return (stat.used / stat.total) * 100.0


def is_disk_critical(path: str, threshold_pct: float) -> bool:
    """Return True when ``path`` resides on a device at or above the threshold.

    Conservative on missing data: an unreadable path returns ``False`` so a
    transient mount glitch never silently halts the scheduler. The caller
    decides whether a follow-up alert is warranted.

    A threshold ≥ 100 disables the gate (treated as "always healthy"),
    giving operators an easy escape hatch from the UI.
    """
    if threshold_pct >= 100.0:
        return False
    pct = get_disk_usage_pct(path)
    if pct is None:
        return False
    return pct >= threshold_pct


def format_disk_status(path: str) -> str:
    """Human-readable usage string for log lines and progress dicts.

    Returns ``"<used>%"`` for a healthy lookup, ``"unknown"`` otherwise.
    """
    pct = get_disk_usage_pct(path)
    if pct is None:
        return "unknown"
    return f"{pct:.1f}%"
