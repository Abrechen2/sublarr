"""Warn before the disks Sublarr writes to run full.

Settings → System offered "Warning Threshold (%)" and "Notify" and nothing read
them (audit #61 A17); the only disk guard was the wanted search pausing at
``wanted_search_disk_pause_pct`` (98 % by default), which is far too late to
be a warning. Hourly, each of the config and media folders over the threshold
is logged and, when enabled, notified — once per folder per day, and again
only after it went back under the threshold.
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, date, datetime

logger = logging.getLogger(__name__)

_lock = threading.Lock()
#: Folder → the day it was last reported while over the threshold.
_reported: dict[str, date] = {}


def check_disk_warning(settings=None) -> list[dict]:
    """The folders over the threshold that are reported now (deduplicated)."""
    from services.disk_safety import get_disk_usage_pct

    if settings is None:
        from config import get_settings

        settings = get_settings()
    threshold = float(getattr(settings, "disk_warning_threshold_percent", 90) or 0)
    if threshold <= 0:
        return []
    folders = {
        getattr(settings, "config_dir", "") or "",
        getattr(settings, "media_path", "") or "",
    } - {""}
    today = datetime.now(UTC).date()
    reports = []
    with _lock:
        for folder in sorted(folders):
            pct = get_disk_usage_pct(folder)
            if pct is None:
                continue
            if pct < threshold:
                _reported.pop(folder, None)
                continue
            if _reported.get(folder) == today:
                continue
            _reported[folder] = today
            reports.append({"path": folder, "percent": round(pct, 1), "threshold": threshold})
    for report in reports:
        logger.warning(
            "Disk at %s is %.1f%% full (warning threshold %.0f%%)",
            report["path"],
            report["percent"],
            report["threshold"],
        )
    if reports and getattr(settings, "disk_warning_notify", True):
        from notifier import send_notification

        for report in reports:
            send_notification(
                "Disk space low",
                f"{report['path']} is {report['percent']}% full "
                f"(warning threshold {report['threshold']:.0f}%).",
                "error",
            )
    return reports


def disk_warning_tick() -> None:
    """Scheduler entry point (module-level and argument-free for the job store)."""
    try:
        check_disk_warning()
    except Exception:  # noqa: BLE001 — a warning must never break the scheduler
        logger.debug("disk warning check failed", exc_info=True)
