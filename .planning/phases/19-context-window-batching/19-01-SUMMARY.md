---
phase: 19-context-window-batching
plan: 01
type: summary
status: complete
date: 2026-02-22
---

# Phase 19-01 Summary — Context-Window Batching Backend

## What was implemented

Context-window batching injects surrounding subtitle lines as read-only context
into every LLM translation prompt, giving the model scene continuity without
adding more lines to translate.

## Files changed

| File | Change |
|------|--------|
| `backend/translation/llm_utils.py` | Added `format_context_timestamp()` and `build_translation_prompt_with_context()` |
| `backend/translation/base.py` | Extended `translate_batch` ABC signature: `+context_before`, `+context_after` |
| `backend/translation/__init__.py` | Extended `translate_with_fallback` signature; forwards context to `backend.translate_batch` |
| `backend/translation/ollama.py` | Accepts context params; uses `build_translation_prompt_with_context` |
| `backend/translation/openai_compat.py` | Same as Ollama — accepts and uses context |
| `backend/translation/deepl_backend.py` | Accepts context params (ignored — non-LLM) |
| `backend/translation/libretranslate.py` | Same — accepts params, ignores |
| `backend/translation/google_translate.py` | Same — accepts params, ignores |
| `backend/translator.py` | Added helper functions + wired all three call sites |

## New functions in `translator.py`

### `_get_context_window_size() -> int`
Reads `translation.context_window_size` from `config_entries` DB. Default 3,
range 0–10. Returns 0 on any error (safe fallback).

### `_events_to_context_items(events) -> list[dict]`
Converts pysubs2 event list to `{start_ms, end_ms, text}` dicts, skipping
comments and empty events.

### `_assemble_context(all_items, target_indices, n) -> (before, after)`
Core logic: walks N lines backwards/forwards from the target batch. Stops at
file boundaries and at any time gap > 5 000 ms (scene break). Returns
chronologically ordered lists. Very short files (< 3 total lines) use all
available items as context regardless of N.

### `_build_dialog_context_items(subs, dialog_indices) -> (all_items, before, after)`
Glue function: builds `all_items` from `subs.events`, maps `dialog_indices`
(event positions) to `all_items` positions, calls `_assemble_context`.

## Prompt structure (when context_window_size > 0)

```
Translate ONLY the lines in the [TRANSLATE THESE LINES] block. Lines in
[CONTEXT - DO NOT TRANSLATE] blocks are provided for scene continuity only.

<prompt template from config>

[CONTEXT - DO NOT TRANSLATE]
00:01:23 - Previous line text

[TRANSLATE THESE LINES]
1: First line to translate
2: Second line to translate

[CONTEXT - DO NOT TRANSLATE]
00:01:45 - Following line text
```

## Config entry

Key: `translation.context_window_size`
- Type: string-encoded integer (consistent with all other config_entries)
- Default: `3` (when key is absent)
- Range: 0–10 (clamped)
- Storage: existing `config_entries` table via `get_config_entry` / `save_config_entry`
- `0` disables the feature entirely — behaviour is identical to pre-Phase-19

## Behaviour when context_window_size = 0

`_build_dialog_context_items` returns empty lists immediately. Both
`context_before` and `context_after` are passed as `None` to
`translate_with_fallback`, which passes `None` to each backend. In
`build_translation_prompt_with_context`, when both are `None`/empty the
function falls through to the standard `build_translation_prompt` call.
No performance cost, no prompt change.

## Three call sites patched

1. `translate_ass_embedded` — embedded ASS stream extracted from MKV
2. `_translate_srt` — SRT file (external or extracted), including retry loops
3. `_translate_external_ass` — downloaded provider ASS file, including retry loops

Retry calls reuse the same `ctx_before_*` / `ctx_after_*` values already
assembled before the first attempt, avoiding redundant re-computation.

## Verification

- `python -m py_compile` passes on all 8 modified files
- Smoke tests confirm:
  - Normal middle-of-file batch gets N lines of before/after context
  - Scene break (gap > 5 s) stops context inclusion
  - File start/end uses only available lines (no padding)
  - n=0 returns empty context (no prompt change)

## Not in scope for 19-01

- Frontend Settings UI for `context_window_size` (Phase 19-02)
- Config API endpoint exposure (19-02 will use existing GET/PUT /config)
