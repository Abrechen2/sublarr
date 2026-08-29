"""One unusable batch must not cost the whole file.

``_translate_in_batches`` raised on the first batch a backend could not deliver,
and the caller lost the episode. The failures are deterministic — the same
batch of the same file fails again on the next run, and the file is stuck for
good. Production bears that out: 882 ``LineCountMismatchError`` events between
2026-07-10 and 2026-08-24, and in the ten days to 2026-08-25 the very same
error texts recur on nine separate days, i.e. the same files dying nightly.

A batch that survives neither the first attempt nor the strict retry is split
and translated in halves. Splitting is not a repair — it removes the merge
opportunity, because two lines the model wants to fold into one sentence end up
in different requests.

Going down to a single line is a last resort and stays one: the batch_size=1
era put 1124 chat-filler lines into the production translation memory, which is
why ``_verify_batch`` screens every result on the way back regardless of how
small the batch got.
"""

from __future__ import annotations

import pytest

from translation.base import TranslationResult


class _FailsOnLargeBatches:
    """Fails any batch longer than ``limit`` lines, succeeds below it.

    Models the measured shape: a 15-line batch comes back with 14 lines every
    single time, while the same content in smaller pieces comes back correct.
    """

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.sizes: list[int] = []

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
        self.sizes.append(len(lines))
        if len(lines) > self.limit:
            return TranslationResult(
                success=False,
                translated_lines=[],
                backend_name="fake",
                error=f"ollama returned {len(lines) - 1} lines after retry, expected {len(lines)}",
            )
        return TranslationResult(
            success=True,
            translated_lines=[f"T_{line}" for line in lines],
            backend_name="fake",
            response_time_ms=10,
            characters_used=sum(len(line) for line in lines),
            error=None,
        )


class _FailsAlways:
    def __init__(self) -> None:
        self.sizes: list[int] = []

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
        self.sizes.append(len(lines))
        return TranslationResult(
            success=False,
            translated_lines=[],
            backend_name="fake",
            error="ollama returned 0 lines after retry, expected 1",
        )


@pytest.fixture
def no_cache(monkeypatch):
    """The memory is not what this tests; swallow the writes."""
    import translator.manager as mod

    monkeypatch.setattr(mod, "_store_translations_in_cache", lambda *a, **k: None)


@pytest.fixture
def no_context(monkeypatch):
    from config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "translation_context_enabled", False, raising=False)
    return s


def _lines(n: int) -> list[str]:
    return [f"line{i}" for i in range(n)]


def test_a_batch_that_keeps_failing_is_split_and_the_file_completes(no_cache, no_context):
    from translator.manager import _translate_in_batches

    manager = _FailsOnLargeBatches(limit=8)

    translated, _last = _translate_in_batches(
        manager, _lines(30), "en", "de", ["fake"], None, batch_size=15
    )

    assert translated == [f"T_line{i}" for i in range(30)]


def test_the_split_halves_rather_than_dropping_straight_to_single_lines(no_cache, no_context):
    """A one-line request is where the model starts making conversation."""
    from translator.manager import _translate_in_batches

    manager = _FailsOnLargeBatches(limit=8)

    _translate_in_batches(manager, _lines(15), "en", "de", ["fake"], None, batch_size=15)

    assert 1 not in manager.sizes
    assert sorted(manager.sizes) == [7, 8, 15]


def test_a_single_line_that_cannot_be_translated_still_fails_the_file(no_cache, no_context):
    """Splitting must not turn an untranslatable file into a silently short one."""
    from translator.manager import _translate_in_batches

    manager = _FailsAlways()

    with pytest.raises(RuntimeError, match="batch"):
        _translate_in_batches(manager, _lines(4), "en", "de", ["fake"], None, batch_size=2)


def test_a_stop_request_is_honoured_inside_a_split(no_cache, no_context):
    """The split creates batch boundaries; a stop must be taken at them too.

    The abort check lives between chunks. Without one inside the split, a batch
    that halves its way down runs on past a stop request for as long as the
    subdivision lasts — which is exactly the delay that had 43 of 61 abandoned
    runs recorded as ``timeout_abandoned`` in the 30 days to 2026-08-22.
    """
    import threading

    from services.scheduler import cancellation
    from translator.errors import TranslationAbortedError
    from translator.manager import _translate_in_batches

    event = threading.Event()
    manager = _FailsOnLargeBatches(limit=2)

    def _stop_once_the_split_begins(lines, *a, **kw):
        if len(lines) < 15:  # the first half of the failed batch
            event.set()
        return _FailsOnLargeBatches.translate_with_fallback(manager, lines, *a, **kw)

    manager.translate_with_fallback = _stop_once_the_split_begins

    with cancellation.bound(event), pytest.raises(TranslationAbortedError):
        _translate_in_batches(manager, _lines(15), "en", "de", ["fake"], None, batch_size=15)


def test_a_healthy_file_is_never_split(no_cache, no_context):
    from translator.manager import _translate_in_batches

    manager = _FailsOnLargeBatches(limit=15)

    _translate_in_batches(manager, _lines(30), "en", "de", ["fake"], None, batch_size=15)

    assert manager.sizes == [15, 15]
