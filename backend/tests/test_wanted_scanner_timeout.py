"""The wanted scanner's ceiling must clear a full scan of a real library.

Prod 2026-09-30: the every-sixth-cycle full scan over 10 698 items took
3 816 s and finished normally ("+39 added"), but the 3 600 s ceiling had
already recorded it as timeout_abandoned, logged an ERROR with a stack dump
and set off the hourly watch. 2026-09-28 03:13 the same. The ceiling cannot
cancel anything — the scan keeps its lock and runs on — so a tight one only
produces false alarms.
"""

MEASURED_FULL_SCAN_S = 3816


def test_the_ceiling_leaves_headroom_over_the_measured_full_scan():
    from services.scheduler import _build_default_jobs

    spec = next(j for j in _build_default_jobs() if j.id == "wanted_scanner")
    assert spec.timeout_s >= 1.5 * MEASURED_FULL_SCAN_S


def test_the_ceiling_stays_below_the_interval():
    """Above the interval a genuinely stuck scan would never be reported:
    the next fire would only ever read as skipped_overlap."""
    from services.scheduler import _build_default_jobs

    spec = next(j for j in _build_default_jobs() if j.id == "wanted_scanner")
    interval_s = spec.default_trigger.interval.total_seconds()
    assert spec.timeout_s < interval_s
