"""Plan B7 — concrete engine tests (ffsubsync + alass)."""

from unittest.mock import patch


def test_ffsubsync_engine_is_available_uses_shutil_which():
    from services.sync_engines.ffsubsync_engine import FfsubsyncEngine

    with (
        patch("services.sync_engines.ffsubsync_engine.shutil.which", return_value=None),
        patch("services.sync_engines.ffsubsync_engine._check_module", return_value=False),
    ):
        assert FfsubsyncEngine().is_available() is False

    with patch(
        "services.sync_engines.ffsubsync_engine.shutil.which",
        return_value="/usr/bin/ffsubsync",
    ):
        assert FfsubsyncEngine().is_available() is True


def test_alass_engine_is_available_uses_shutil_which():
    from services.sync_engines.alass_engine import AlassEngine

    with patch("services.sync_engines.alass_engine.shutil.which", return_value=None):
        assert AlassEngine().is_available() is False

    with patch(
        "services.sync_engines.alass_engine.shutil.which",
        return_value="/usr/bin/alass",
    ):
        assert AlassEngine().is_available() is True


def test_ffsubsync_engine_sync_returns_sync_result_on_success(tmp_path):
    from services.sync_engines.base import SyncResult
    from services.sync_engines.ffsubsync_engine import FfsubsyncEngine

    sub = tmp_path / "in.srt"
    sub.write_text("1\n00:00:01,000 --> 00:00:02,000\nHi\n")

    fake_proc = type(
        "P",
        (),
        {
            "returncode": 0,
            "stdout": "estimated shift: 0.123 s",
            "stderr": "",
        },
    )()

    with (
        patch(
            "services.sync_engines.ffsubsync_engine.shutil.which",
            return_value="ffsubsync",
        ),
        patch(
            "services.sync_engines.ffsubsync_engine.subprocess.run",
            return_value=fake_proc,
        ),
        patch("services.sync_engines.ffsubsync_engine._fire_after_sync_trigger"),
        patch("services.sync_engines.ffsubsync_engine.shutil.copy2"),
    ):
        result = FfsubsyncEngine().sync(str(sub), "/v.mkv")

    assert isinstance(result, SyncResult)
    assert result.engine == "ffsubsync"
    assert result.ok is True
