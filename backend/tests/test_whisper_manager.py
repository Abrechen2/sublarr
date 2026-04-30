"""Unit tests for whisper.WhisperManager — backend dispatch + circuit breaker."""

from whisper import WhisperManager


def test_invalidate_backend_resets_circuit_breaker():
    """Switching active backends must NOT carry over circuit-breaker stats.

    Before this fix, the breaker was created lazily and bound to the OLD
    backend's name. Switching to a new backend would reuse the breaker,
    so OPEN-state failure counts from the previous backend silently
    blocked the new one until cooldown elapsed.
    """
    manager = WhisperManager()
    # Force-create a breaker as if a transcription had already run.
    manager._backend_name = "subgen"
    breaker = manager._get_circuit_breaker()
    assert breaker is not None
    assert manager._circuit_breaker is breaker

    manager.invalidate_backend()

    assert manager._backend is None
    assert manager._backend_name is None
    assert manager._circuit_breaker is None, (
        "circuit breaker must be cleared so the next backend gets a fresh state"
    )

    # After invalidation, _get_circuit_breaker creates a new instance.
    manager._backend_name = "faster_whisper"
    fresh = manager._get_circuit_breaker()
    assert fresh is not breaker, "expected a freshly-instantiated breaker"
