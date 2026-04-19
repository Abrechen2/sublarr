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
