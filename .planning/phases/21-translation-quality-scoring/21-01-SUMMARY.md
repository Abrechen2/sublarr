# Phase 21-01: Translation Quality Scoring Backend — SUMMARY

## Status: COMPLETE

## What Was Implemented

### 1. `backend/translation/llm_utils.py` — Evaluation Utilities

Added three new symbols:

- **`DEFAULT_QUALITY_SCORE = 50`** — module-level constant, fallback score when LLM eval fails
- **`build_evaluation_prompt(source_text, translated_text, source_lang, target_lang) -> str`**  
  Builds a concise LLM prompt: "Rate the quality of this subtitle translation from {src} to {tgt} on a scale from 0 to 100 ... Reply with only a single integer number."  
  Includes original and translated text as labeled context.
- **`parse_quality_score(response_text: str) -> int`**  
  Extracts the first integer from the LLM response via regex `\b(\d{1,3})\b`, clamps to [0, 100].  
  Returns DEFAULT_QUALITY_SCORE (50) when no number is found.

### 2. `backend/translation/__init__.py` — TranslationManager Extensions

Two new methods on `TranslationManager`:

- **`evaluate_line_quality(source_text, translated_text, source_lang, target_lang, fallback_chain) -> int`**  
  Iterates `fallback_chain`, skips non-LLM backends (`DeepL`, `LibreTranslate`, `Google`), tries only `ollama` and `openai_compat`.  
  Uses `_call_backend_raw()` to send the evaluation prompt directly (no batch parsing).  
  Returns DEFAULT_QUALITY_SCORE (50) on any error — never blocks the translation pipeline.

- **`_call_backend_raw(backend, prompt: str) -> Optional[str]`**  
  Duck-typed raw call: checks for `_call_ollama` (Ollama backend) or `_call_openai` (OpenAI-compat backend).  
  Returns `None` for unsupported backends.

### 3. `backend/translator.py` — Quality Pipeline Integration

Four new module-level helper functions:

- **`_get_quality_config() -> (enabled: bool, threshold: int, max_retries: int)`**  
  Reads `translation_quality_enabled`, `translation_quality_threshold` (default 50), and `translation_quality_max_retries` (default 2) from `config_entries` DB.  
  Falls back to `(True, 50, 2)` on any DB error.

- **`_evaluate_and_retry_lines(source_lines, translated_lines, ..., threshold, max_retries) -> (final_lines, scores)`**  
  Per-line loop: evaluates each line, retries low-scoring lines (score < threshold) up to `max_retries` times.  
  Keeps the best-scoring version across all attempts. Returns final translated lines + per-line scores list.

- **`_compute_quality_stats(scores: list, threshold: int) -> dict`**  
  Aggregates per-line scores into: `avg_quality`, `min_quality`, `low_quality_lines`, `quality_threshold`.  
  Returns `{}` for empty scores (quality eval was disabled or skipped).

- **`_write_quality_sidecar(subtitle_path: str, scores: list) -> None`**  
  Writes scores to `<subtitle_path>.quality.json` as a JSON array.  
  No-op for empty scores; logs warnings on write failures (never raises).

**Integration into translation functions:**  
All three pipeline functions (`translate_ass`, `_translate_srt`, `_translate_external_ass`) now:
1. Call `_get_quality_config()` after the initial translation
2. If enabled, call `_evaluate_and_retry_lines()` to score + retry low-quality lines
3. Call `_write_quality_sidecar()` after saving the subtitle file
4. Spread `_compute_quality_stats()` result into the returned `stats` dict

### 4. `backend/db/repositories/jobs.py` — No Changes Required

`update_job()` already serializes `result["stats"]` in full to `stats_json`. Quality stats (`avg_quality`, `min_quality`, `low_quality_lines`, `quality_threshold`) are automatically persisted as part of the stats dict.

### 5. `backend/routes/tools.py` — Quality Scores in `/parse` Response

`POST /api/v1/tools/parse` now:
1. After parsing cues, checks for `<subtitle_path>.quality.json` sidecar
2. If found and length matches cue count, injects `quality_score` into each cue dict
3. Adds `has_quality_scores: bool` to the response envelope

## Config Entries (New)

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `translation_quality_enabled` | bool | true | Enable LLM quality evaluation |
| `translation_quality_threshold` | int | 50 | Score below which lines are retried |
| `translation_quality_max_retries` | int | 2 | Max retry attempts per low-quality line |

## Stats Fields Added to Job Results

| Field | Type | Description |
|-------|------|-------------|
| `avg_quality` | float | Average score across all dialog lines |
| `min_quality` | int | Worst-scoring line |
| `low_quality_lines` | int | Lines that scored below threshold |
| `quality_threshold` | int | Threshold used (for display reference) |

## API: `/tools/parse` Response Changes

Cue objects now include optional `quality_score: int` field (0-100) when a sidecar exists.  
Response envelope gains `has_quality_scores: bool` field.

## Design Decisions

1. **Evaluation only for LLM backends** — Rule-based backends (DeepL, LibreTranslate, Google) cannot generate free-form numeric responses. Only `ollama` and `openai_compat` are tried.
2. **Per-line eval, not batch** — Each line is evaluated individually for precise retry targeting. Adds LLM round-trip overhead but avoids retrying good lines.
3. **Graceful degradation** — All evaluation failures silently fall back to DEFAULT_QUALITY_SCORE (50). Quality eval never blocks or fails a translation job.
4. **Sidecar file** — `<path>.quality.json` is the simplest persistence mechanism for per-cue scores, compatible with the existing `/parse` endpoint without DB schema changes.
5. **No jobs.py changes** — The `stats` dict is already fully serialized; new fields pass through automatically.

## Files Changed

- `backend/translation/llm_utils.py` — +42 lines (evaluation prompt, score parser)
- `backend/translation/__init__.py` — +88 lines (evaluate_line_quality, _call_backend_raw)
- `backend/translator.py` — +108 lines (4 helpers + 3x pipeline integration blocks)
- `backend/routes/tools.py` — +12 lines (sidecar loading in /parse)

## Testing

- `parse_quality_score`: edge cases (empty, clamping, non-numeric responses)
- `build_evaluation_prompt`: output contains source/target langs and both texts
- `_compute_quality_stats`: empty list, aggregates, low_quality_lines count
- `_write_quality_sidecar`: sidecar creation, content integrity, no-op for empty scores
- Syntax check: `python -m py_compile` on all 4 modified files — PASS
- Existing test suite: 39 pre-existing failures unchanged, 0 new failures introduced
