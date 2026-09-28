"""A metadata probe waits seconds for the media gate, not the background hour.

``BACKGROUND_WAIT_S`` is an hour, and that is right for the work the gate
exists to serialise — a remux, an extraction, a sync. A probe is not that
work: it is a read of a few seconds whose caller already has a graceful answer
for not getting in (``PROBE_REFUSED``, which the scanner treats as "says
nothing about this file" and never upserts over a good row).

Prod 2026-09-28 03:13 showed the difference. The foreign-track sweep held the
single gate slot (``media_io_max_parallel`` defaults to 1) from 03:00 to 04:17
for one 2160p remux; the ``wanted_scanner`` tick that started at 03:13 queued
behind it and was recorded ``timeout_abandoned`` at 3660 s. The scans that ran
outside the sweep window the same day took 52 s, 69 s, 82 s and 111 s.

Behind a long remux the hour is not one wait — every probe in the batch queues
on the same slot, so the scan spends its whole tick budget waiting.
"""

from unittest.mock import patch

from services.media_io_gate import MediaIOGate, media_io_gate


class TestTheWaitPolicy:
    def test_the_probe_wait_is_far_below_the_tick_budget(self):
        """3600 s is the scanner's own timeout; a probe may not approach it."""
        assert MediaIOGate.PROBE_WAIT_S < MediaIOGate.BACKGROUND_WAIT_S
        assert MediaIOGate.PROBE_WAIT_S <= 60

    def test_batch_probe_asks_for_that_wait_and_not_the_default(self):
        """The regression: `slot(label)` alone inherits the background hour."""
        seen = {}

        class _Slot:
            def __enter__(self):
                return None

            def __exit__(self, *_exc):
                return False

        def _fake_slot(label, timeout=None):
            seen["label"] = label
            seen["timeout"] = timeout
            return _Slot()

        from services import wanted_item_scanner

        with (
            patch.object(media_io_gate, "slot", _fake_slot),
            patch.object(media_io_gate, "cap_workers", return_value=1),
            patch.object(wanted_item_scanner, "get_media_streams", return_value={"streams": []}),
        ):
            wanted_item_scanner.batch_probe(["/media/x.mkv"])

        assert seen["timeout"] == MediaIOGate.PROBE_WAIT_S, (
            f"probe asked for timeout={seen['timeout']!r} — the background hour starves the scan"
        )


class TestTheRefusalIsStillGraceful:
    def test_a_refused_probe_is_the_refusal_sentinel_not_an_empty_result(self):
        """Degrading has to stay distinguishable from "no embedded streams"."""
        from services.media_io_gate import MediaGateBusyError
        from services.wanted_item_scanner import PROBE_REFUSED, batch_probe

        def _busy(label, timeout=None):
            raise MediaGateBusyError("busy")

        with (
            patch.object(media_io_gate, "slot", _busy),
            patch.object(media_io_gate, "cap_workers", return_value=1),
        ):
            results = batch_probe(["/media/x.mkv"])

        assert results["/media/x.mkv"] is PROBE_REFUSED
