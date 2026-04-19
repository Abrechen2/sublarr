"""Context-window pre-chunker for LLM translation batches.

Splits a full subtitle file into batches with surrounding lookback + lookahead
context. LLMs use this to resolve pronouns, maintain terminology consistency
across batch boundaries, and preserve narrative coherence — they see the
surrounding lines but translate only the batch.

Non-LLM backends (DeepL, Google, LibreTranslate) should skip context entirely
— the caller in TranslationManager is responsible for that conditional.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContextChunk:
    """One batch of lines to translate, with surrounding context.

    Attributes:
        lookback: N lines BEFORE the batch, for context only (not translated).
        batch: the lines the LLM must translate.
        lookahead: N lines AFTER the batch, for context only.
        batch_start_index: index of batch[0] in the original `lines` list.
            Used by callers to reassemble the full translated file.
    """

    lookback: list[str]
    batch: list[str]
    lookahead: list[str]
    batch_start_index: int


def build_chunks(
    lines: list[str],
    batch_size: int,
    lookback: int = 10,
    lookahead: int = 5,
) -> list[ContextChunk]:
    """Split a full subtitle file into ContextChunks.

    Args:
        lines: the full file as a list of subtitle lines.
        batch_size: max lines to translate per chunk (matches backend.max_batch_size).
        lookback: lines before each batch to include as context (clipped to available).
        lookahead: lines after each batch to include as context (clipped).

    Returns:
        List of ContextChunks covering every line exactly once in `batch`.
        Empty list if `lines` is empty.

    Raises:
        ValueError: batch_size < 1 or lookback < 0 or lookahead < 0.
    """
    if batch_size < 1:
        raise ValueError(f"batch_size must be >= 1, got {batch_size}")
    if lookback < 0:
        raise ValueError(f"lookback must be >= 0, got {lookback}")
    if lookahead < 0:
        raise ValueError(f"lookahead must be >= 0, got {lookahead}")

    if not lines:
        return []

    chunks: list[ContextChunk] = []
    total = len(lines)
    start = 0
    while start < total:
        end = min(start + batch_size, total)
        lb_start = max(0, start - lookback)
        la_end = min(total, end + lookahead)
        chunks.append(
            ContextChunk(
                lookback=lines[lb_start:start],
                batch=lines[start:end],
                lookahead=lines[end:la_end],
                batch_start_index=start,
            )
        )
        start = end
    return chunks
