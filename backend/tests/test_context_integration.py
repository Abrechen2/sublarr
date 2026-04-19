"""Integration test — context_windower -> translate_with_fallback -> LLMBackend.

Verifies that when _translate_in_batches calls translate_with_fallback with
multi-chunk lines, each chunk gets appropriate lookback/lookahead context.

The tests use a stub ``_FakeManager`` instead of a real TranslationManager
so we can observe the exact lookback/lookahead values passed to each chunk
without standing up a full backend stack.
"""

from __future__ import annotations

import pytest

from translation.base import TranslationResult


class _FakeManager:
    """Records every translate_with_fallback call for assertions.

    Echoes back ``T_<line>`` per input line so the caller's line-count
    verification succeeds.
    """

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def translate_with_fallback(
        self,
        lines,
        source_lang,
        target_lang,
        fallback_chain,
        glossary_entries=None,
        *,
        lookback=None,
        lookahead=None,
    ) -> TranslationResult:
        self.calls.append(
            {
                "lines": list(lines),
                "lookback": list(lookback) if lookback is not None else None,
                "lookahead": list(lookahead) if lookahead is not None else None,
            }
        )
        return TranslationResult(
            success=True,
            translated_lines=[f"T_{line}" for line in lines],
            backend_name="fake",
            response_time_ms=10,
            characters_used=sum(len(line) for line in lines),
            error=None,
        )


@pytest.fixture
def enable_context(monkeypatch):
    """Force translation_context_enabled=True with deterministic window sizes.

    ``_translate_in_batches`` reads these via ``get_settings()``. We patch the
    singleton directly so tests are hermetic (no env-var / DB state leak).
    """
    from config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "translation_context_enabled", True, raising=False)
    monkeypatch.setattr(s, "translation_context_lookback_lines", 10, raising=False)
    monkeypatch.setattr(s, "translation_context_lookahead_lines", 5, raising=False)
    return s


def test_translate_in_batches_passes_context(enable_context):
    """Multi-chunk call should pass lookback/lookahead per chunk."""
    from translator.manager import _translate_in_batches

    fake = _FakeManager()
    lines = [f"line{i}" for i in range(25)]

    translated, last = _translate_in_batches(
        fake,
        lines,
        "en",
        "de",
        fallback_chain=["fake"],
        glossary_entries=None,
        batch_size=10,
    )

    assert len(translated) == 25
    assert translated[0] == "T_line0"
    # 3 chunks (10 + 10 + 5)
    assert len(fake.calls) == 3
    # First chunk: empty lookback -> None; has lookahead
    assert fake.calls[0]["lookback"] is None  # empty list converted to None
    assert fake.calls[0]["lookahead"] is not None
    assert fake.calls[0]["lookahead"] == ["line10", "line11", "line12", "line13", "line14"]
    # Middle chunk: both lookback and lookahead present
    assert fake.calls[1]["lookback"] is not None
    assert fake.calls[1]["lookahead"] is not None
    assert fake.calls[1]["lookback"] == [f"line{i}" for i in range(10)]
    # Last chunk: has lookback, empty lookahead -> None
    assert fake.calls[2]["lookback"] is not None
    assert fake.calls[2]["lookahead"] is None
    # last TranslationResult returned
    assert last.success is True


def test_single_batch_no_context(enable_context):
    """Single-batch call bypasses chunking entirely -- no context passed."""
    from translator.manager import _translate_in_batches

    fake = _FakeManager()
    lines = ["a", "b", "c"]

    _translate_in_batches(
        fake,
        lines,
        "en",
        "de",
        fallback_chain=["fake"],
        glossary_entries=None,
        batch_size=10,
    )

    assert len(fake.calls) == 1
    # Single-batch path doesn't pass context (positional call only)
    assert fake.calls[0]["lookback"] is None
    assert fake.calls[0]["lookahead"] is None


def test_context_disabled_via_config(monkeypatch):
    """When translation_context_enabled=False, chunks receive no context."""
    from config import get_settings
    from translator.manager import _translate_in_batches

    s = get_settings()
    monkeypatch.setattr(s, "translation_context_enabled", False, raising=False)

    fake = _FakeManager()
    lines = [f"line{i}" for i in range(25)]

    _translate_in_batches(
        fake,
        lines,
        "en",
        "de",
        fallback_chain=["fake"],
        glossary_entries=None,
        batch_size=10,
    )

    # 3 chunks but all receive no context (0 + 0 = empty -> None)
    assert len(fake.calls) == 3
    for c in fake.calls:
        assert c["lookback"] is None
        assert c["lookahead"] is None
