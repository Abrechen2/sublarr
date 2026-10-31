"""The drain-worker toggle does what its help text says.

Audit #61 A02: ``subtitle_automation_queue_enabled`` was saved and read by
nothing — switching the worker off still claimed and processed queued
extractions. Off now means: new items take the legacy inline "Auto-Extract on
scan" path, and the worker leaves extraction and translation rows alone.
"""

from unittest.mock import MagicMock, patch

from db.models.core import SubtitleAutomationQueueEntry as Q
from services.subtitle_automation_runner import _eligible_task_types


def _settings(queue_enabled):
    return MagicMock(
        subtitle_automation_enabled=True,
        subtitle_automation_queue_enabled=queue_enabled,
        auto_sync_after_download=True,
        wanted_auto_extract=True,
        wanted_auto_translate=False,
    )


def test_with_the_worker_off_no_extraction_is_claimed():
    with patch("config.get_settings", return_value=_settings(False)):
        eligible = _eligible_task_types()

    assert Q.TASK_EMBEDDED_EXTRACT not in eligible
    assert Q.TASK_SIDECAR_TRANSLATE not in eligible
    # No inline fallback exists for these, so they keep draining.
    assert {Q.TASK_AUTO_SYNC, Q.TASK_FOREIGN_TRACK_CLEANUP} <= eligible


def test_with_the_worker_on_extraction_is_claimed():
    with patch("config.get_settings", return_value=_settings(True)):
        assert Q.TASK_EMBEDDED_EXTRACT in _eligible_task_types()


def test_with_the_worker_off_the_scan_extracts_inline():
    from services.wanted_scanner_sources import _WantedScanSourcesMixin

    scanner = _WantedScanSourcesMixin.__new__(_WantedScanSourcesMixin)
    with (
        patch("services.wanted_scanner_sources.get_settings", return_value=_settings(False)),
        patch("services.wanted_scanner_sources._enqueue_automation") as enqueue,
        patch("services.wanted_scanner_sources._extract_embedded_sub") as inline,
        patch("services.wanted_scanner_sources._lookup_target_language", return_value="de"),
    ):
        scanner._maybe_auto_extract(5, "/media/x.mkv")

    enqueue.assert_not_called()
    inline.assert_called_once()
