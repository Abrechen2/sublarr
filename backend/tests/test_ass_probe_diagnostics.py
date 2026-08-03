"""Diagnosability of ``ass_probe.run_ffprobe`` failures.

Prod incident 2026-08-01: the wanted batch-probe logged twelve failures as
``ffprobe failed:`` with an empty reason. The cause was that ``run_ffprobe``
invoked ffprobe with ``-v quiet``, which suppresses every diagnostic on
stderr — so the ``RuntimeError`` interpolating ``result.stderr`` could never
carry a reason. The actual cause (files deleted from disk) stayed invisible.

These tests pin the contract: ffprobe must stay quiet enough not to pollute
normal operation, but loud enough that a failure explains itself.
"""

from unittest.mock import MagicMock, patch

import pytest


class TestFfprobeFailureIsDiagnosable:
    def test_argv_does_not_silence_diagnostics(self, tmp_path, app_ctx):
        """``-v quiet`` would make every failure message empty."""
        from ass_probe import run_ffprobe

        video = tmp_path / "show.mkv"
        video.write_bytes(b"\x1a\x45\xdf\xa3")

        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return MagicMock(returncode=0, stdout='{"streams": []}', stderr="")

        with patch("ass_probe.subprocess.run", side_effect=fake_run):
            run_ffprobe(str(video), use_cache=False)

        cmd = captured["cmd"]
        assert "quiet" not in cmd, "ffprobe -v quiet swallows the failure reason"

        # The loglevel must be explicit, and at least 'error' so that a
        # non-zero exit is accompanied by a message on stderr.
        assert "-v" in cmd
        assert cmd[cmd.index("-v") + 1] == "error"

    def test_stderr_reaches_the_raised_error(self, tmp_path, app_ctx):
        """A failing probe must name its cause, not raise an empty message."""
        from ass_probe import run_ffprobe

        video = tmp_path / "gone.mkv"
        video.write_bytes(b"\x1a\x45\xdf\xa3")

        reason = "gone.mkv: No such file or directory"

        with (
            patch(
                "ass_probe.subprocess.run",
                return_value=MagicMock(returncode=1, stdout="", stderr=reason),
            ),
            pytest.raises(RuntimeError) as excinfo,
        ):
            run_ffprobe(str(video), use_cache=False)

        assert reason in str(excinfo.value)
