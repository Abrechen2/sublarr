"""Plan B7 — orchestrator fallback chain tests."""

import pytest


def test_base_sync_engine_abc():
    from services.sync_engines.base import BaseSyncEngine, SyncResult

    with pytest.raises(TypeError):
        BaseSyncEngine()

    r = SyncResult(engine="x", ok=True, offset_ms=42, duration_ms=5, output_path="/o.srt")
    assert r.ok


def test_orchestrator_fires_engines_in_order_and_exits_on_first_success():
    from unittest.mock import MagicMock, patch

    from services.sync_engines.base import SyncResult
    from services.sync_engines.orchestrator import SyncOrchestrator

    engine_a = MagicMock()
    engine_a.name = "a"
    engine_a.is_available.return_value = True
    engine_a.sync.return_value = SyncResult(
        engine="a", ok=True, offset_ms=20, duration_ms=5, output_path="/o.srt"
    )

    engine_b = MagicMock()
    engine_b.name = "b"
    engine_b.is_available.return_value = True

    orch = SyncOrchestrator(engines=[engine_a, engine_b], sanity_threshold_ms=60_000)
    with patch("services.sync_engines.orchestrator.write_sync_job_run"):
        result = orch.sync(subtitle_path="/s.srt", video_path="/v.mkv")

    assert result.ok
    assert result.engine == "a"
    engine_b.sync.assert_not_called()


def test_orchestrator_falls_through_on_exception():
    from unittest.mock import MagicMock, patch

    from services.sync_engines.base import SyncResult
    from services.sync_engines.orchestrator import SyncOrchestrator

    engine_a = MagicMock()
    engine_a.name = "a"
    engine_a.is_available.return_value = True
    engine_a.sync.side_effect = RuntimeError("boom")

    engine_b = MagicMock()
    engine_b.name = "b"
    engine_b.is_available.return_value = True
    engine_b.sync.return_value = SyncResult(
        engine="b", ok=True, offset_ms=0, duration_ms=3, output_path="/o.srt"
    )

    orch = SyncOrchestrator(engines=[engine_a, engine_b], sanity_threshold_ms=60_000)
    with patch("services.sync_engines.orchestrator.write_sync_job_run"):
        result = orch.sync(subtitle_path="/s.srt", video_path="/v.mkv")

    assert result.ok
    assert result.engine == "b"
    engine_a.sync.assert_called_once()
    engine_b.sync.assert_called_once()


def test_orchestrator_rejects_insane_offset_and_falls_through():
    """Engine returns a huge offset beyond sanity threshold — orchestrator treats as failure."""
    from unittest.mock import MagicMock, patch

    from services.sync_engines.base import SyncResult
    from services.sync_engines.orchestrator import SyncOrchestrator

    engine_a = MagicMock()
    engine_a.name = "a"
    engine_a.is_available.return_value = True
    engine_a.sync.return_value = SyncResult(
        engine="a", ok=True, offset_ms=500_000, duration_ms=5, output_path="/o.srt"
    )

    engine_b = MagicMock()
    engine_b.name = "b"
    engine_b.is_available.return_value = True
    engine_b.sync.return_value = SyncResult(
        engine="b", ok=True, offset_ms=50, duration_ms=5, output_path="/o.srt"
    )

    orch = SyncOrchestrator(engines=[engine_a, engine_b], sanity_threshold_ms=60_000)
    with patch("services.sync_engines.orchestrator.write_sync_job_run"):
        result = orch.sync(subtitle_path="/s.srt", video_path="/v.mkv")

    assert result.ok
    assert result.engine == "b"


def test_orchestrator_skips_unavailable_engines():
    from unittest.mock import MagicMock, patch

    from services.sync_engines.base import SyncResult
    from services.sync_engines.orchestrator import SyncOrchestrator

    engine_a = MagicMock()
    engine_a.name = "a"
    engine_a.is_available.return_value = False  # Not installed

    engine_b = MagicMock()
    engine_b.name = "b"
    engine_b.is_available.return_value = True
    engine_b.sync.return_value = SyncResult(
        engine="b", ok=True, offset_ms=10, duration_ms=3, output_path="/o.srt"
    )

    orch = SyncOrchestrator(engines=[engine_a, engine_b], sanity_threshold_ms=60_000)
    with patch("services.sync_engines.orchestrator.write_sync_job_run"):
        result = orch.sync(subtitle_path="/s.srt", video_path="/v.mkv")

    assert result.ok
    assert result.engine == "b"
    engine_a.sync.assert_not_called()


def test_orchestrator_returns_failure_when_all_engines_fail():
    from unittest.mock import MagicMock, patch

    from services.sync_engines.orchestrator import SyncOrchestrator

    engine_a = MagicMock()
    engine_a.name = "a"
    engine_a.is_available.return_value = True
    engine_a.sync.side_effect = RuntimeError("boom")

    engine_b = MagicMock()
    engine_b.name = "b"
    engine_b.is_available.return_value = True
    engine_b.sync.side_effect = RuntimeError("also broke")

    orch = SyncOrchestrator(engines=[engine_a, engine_b], sanity_threshold_ms=60_000)
    with patch("services.sync_engines.orchestrator.write_sync_job_run"):
        result = orch.sync(subtitle_path="/s.srt", video_path="/v.mkv")

    assert result.ok is False
    assert result.engine in {"a", "b", "none"}


def test_legacy_sync_with_ffsubsync_preserves_dict_shape(tmp_path, monkeypatch):
    """The legacy sync_with_ffsubsync function still returns its historic dict shape.

    Plan B7 keeps the wrapper implementation in-place (not a thin delegate) to
    avoid breaking the existing routes/sync.py, routes/video_sync.py and the CLI
    consumer backend/cli/commands/sync.py — the engine classes live side-by-side
    in services.sync_engines.* and are the path the new SyncOrchestrator uses.
    """
    from unittest.mock import patch

    sub = tmp_path / "s.srt"
    sub.write_text("1\n00:00:01,000 --> 00:00:02,000\nHi\n")

    class _FakeProc:
        returncode = 0
        stdout = "offset 0.1 s applied"
        stderr = ""

    monkeypatch.setattr(
        "services.video_sync.shutil.which",
        lambda name: f"/usr/bin/{name}" if name == "ffsubsync" else None,
    )
    monkeypatch.setattr("services.video_sync.subprocess.run", lambda *a, **kw: _FakeProc())
    monkeypatch.setattr("services.video_sync.shutil.move", lambda src, dst: None)

    with patch("services.video_sync.run_trigger"):
        from services.video_sync import sync_with_ffsubsync

        result_dict = sync_with_ffsubsync(str(sub), "/v.mkv")

    assert result_dict["engine"] == "ffsubsync"
    assert "shift_ms" in result_dict
    assert "output_path" in result_dict
    assert "backup_path" in result_dict


def test_legacy_sync_with_alass_preserves_dict_shape(tmp_path, monkeypatch):
    """The legacy sync_with_alass function still returns its historic dict shape."""
    from unittest.mock import patch

    sub = tmp_path / "s.srt"
    sub.write_text("1\n00:00:01,000 --> 00:00:02,000\nHi\n")

    class _FakeProc:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(
        "services.video_sync.shutil.which",
        lambda name: f"/usr/bin/{name}" if name == "alass" else None,
    )
    monkeypatch.setattr("services.video_sync.subprocess.run", lambda *a, **kw: _FakeProc())
    monkeypatch.setattr("services.video_sync.shutil.move", lambda src, dst: None)

    with patch("services.video_sync.run_trigger"):
        from services.video_sync import sync_with_alass

        result_dict = sync_with_alass(str(sub), "/ref.srt")

    assert result_dict["engine"] == "alass"
    assert "output_path" in result_dict
    assert "backup_path" in result_dict
