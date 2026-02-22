---
phase: 20-translation-memory-cache
plan: 01
type: summary
status: complete
date: 2026-02-22
---

# Phase 20-01: Translation Memory Cache Backend — Summary

## Objective

Implemented a persistent translation memory cache that stores successfully translated subtitle
lines and reuses them on subsequent runs, reducing LLM calls and cost for identical or
near-identical content.

## Changes Made

### 1. `backend/db/models/translation.py`

Added `TranslationMemory` ORM model:
- Columns: `id`, `source_lang`, `target_lang`, `source_text_normalized`, `text_hash`, `translated_text`, `created_at`
- `text_hash` = SHA-256 of `source_text_normalized` (enables O(1) index lookup)
- Indexes: `idx_tm_lang_hash` (source_lang, target_lang, text_hash), `idx_tm_lang_pair` (source_lang, target_lang)
- Unique constraint `uq_tm_lang_hash` on (source_lang, target_lang, text_hash)

### 2. `backend/db/repositories/translation.py`

Added four methods to `TranslationRepository`:
- `_normalize_text(text)` — strip, lowercase, collapse whitespace
- `_hash_text(normalized)` — SHA-256 hex digest
- `lookup_translation_cache(source_lang, target_lang, source_text, similarity_threshold)` — exact hash match; optional difflib similarity scan when threshold < 1.0
- `store_translation_cache(source_lang, target_lang, source_text, translated_text)` — upsert by unique key
- `clear_translation_cache()` — bulk delete, returns rowcount
- `get_translation_cache_stats()` — returns `{"entries": N}`

### 3. `backend/db/translation.py`

Re-exported all four public functions:
- `lookup_translation_cache`
- `store_translation_cache`
- `clear_translation_cache`
- `get_translation_cache_stats`

### 4. `backend/translator.py`

Added three private helpers before `_translate_with_manager`:
- `_get_cache_config()` — reads `translation_memory_enabled` and `translation_memory_similarity_threshold` from `config_entries`; defaults: enabled=True, threshold=1.0
- `_apply_translation_cache(lines, source_lang, target_lang, similarity_threshold)` — splits input list into cache hits / misses, returns `(cached_results, uncached_indices, uncached_lines)`
- `_store_translations_in_cache(source_lines, translated_lines, source_lang, target_lang)` — persists newly translated lines; errors are logged and silently suppressed

Modified `_translate_with_manager` body:
1. Call `_get_cache_config()` once per invocation
2. Call `_apply_translation_cache()` to separate cached from uncached lines
3. If all lines are cached → return synthetic `TranslationResult` immediately (no LLM call)
4. Otherwise call LLM only for uncached lines
5. Merge results back into original-order output list
6. Store new translations in cache

Original input/output order is preserved in all cases.

### 5. `backend/routes/translate.py`

Added two new endpoints under `/api/v1/`:
- `GET /translation-memory/stats` → `{"entries": N}`
- `DELETE /translation-memory/cache` → `{"cleared": true, "deleted": N}`

### 6. `backend/db/migrations/versions/e3f4a5b6c7d8_add_translation_memory.py`

Alembic migration:
- Creates `translation_memory` table with all columns
- Creates `idx_tm_lang_hash` composite index
- Creates `idx_tm_lang_pair` index
- Creates `uq_tm_lang_hash` unique constraint
- `downgrade()` drops indexes and table

## Configuration Keys (config_entries)

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `translation_memory_enabled` | bool | `true` | Enable/disable the cache entirely |
| `translation_memory_similarity_threshold` | float (0.0–1.0) | `1.0` | Minimum similarity for fuzzy match; 1.0 = exact only |

## Verification

```bash
cd backend && python -m py_compile translator.py db/repositories/translation.py \
  db/models/translation.py routes/translate.py db/translation.py \
  db/migrations/versions/e3f4a5b6c7d8_add_translation_memory.py
# Output: (no errors)
```

## Key Design Decisions

- **Hash-first lookup**: SHA-256 hash enables O(1) exact match via index without full-text comparison.
- **Order preservation**: Input list indices are tracked so merged output always matches original subtitle line order.
- **Fail-open**: Cache errors (lookup or store) are logged as DEBUG and never propagate — LLM fallback is always used on cache failure.
- **Similarity threshold default = 1.0**: Exact-only matching is safe and predictable. Fuzzy matching is opt-in via config.
- **No LLM call when fully cached**: The pipeline short-circuits early and returns a synthetic `TranslationResult` with `backend_name="translation_memory"`.
