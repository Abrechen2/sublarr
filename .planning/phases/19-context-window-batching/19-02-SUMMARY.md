---
phase: 19-context-window-batching
plan: 02
type: summary
status: complete
date: 2026-02-22
---

# Phase 19-02 Summary — Context-Window Batching Frontend

## What was implemented

Frontend Settings UI for the context window size introduced in Phase 19-01 backend.
Users can now configure how many preceding/following subtitle lines are sent as
context to the LLM, directly from Settings > Translation.

## Files changed

| File | Change |
|------|--------|
| `backend/routes/config.py` | GET /config now includes `translation.context_window_size` from `config_entries`; PUT /config now accepts dot-notation extension keys |
| `frontend/src/hooks/useApi.ts` | Added `useContextWindowSize()` hook |
| `frontend/src/pages/Settings/TranslationTab.tsx` | Added `ContextWindowSizeRow` component; added `useContextWindowSize` import |
| `frontend/src/pages/Settings/index.tsx` | Lazy-imported `ContextWindowSizeRow`; rendered it inside the Translation tab card |

## Backend changes (routes/config.py)

### GET /config
Extended `get_config()` to merge in a list of known namespaced extension config
entries that are not Pydantic Settings fields. Currently only
`translation.context_window_size`, read via `get_config_entry()`.

If the key is absent in the DB (never set), it is simply omitted from the
response — the frontend defaults to `3`.

### PUT /config
Added `is_extension_key = '.' in key` check. Keys containing a dot are treated
as namespaced extension config entries and bypass the `valid_keys` Pydantic
Settings filter. They are saved directly to `config_entries` via
`save_config_entry(key, value)`.

## Frontend hook (useApi.ts)

### `useContextWindowSize()`
- Reads `data['translation.context_window_size']` from `useConfig()` response
- Falls back to `3` when the key is absent or `data` is not yet loaded
- Converts the string value from the API to a `number`
- `save(size)` calls `useUpdateConfig().mutate()` with the dot-notation key
- Returns `{ value, save, isPending }`

## UI component (TranslationTab.tsx)

### `ContextWindowSizeRow`
- `SettingRow` with label "Context window (lines)"
- Inline help text: "Number of lines before and after each batch sent as context
  to the LLM. 0 = disabled."
- Number input, `min=0`, `max=10`, `w-24` (narrow — number is 0-10)
- Local state (`useState`) for responsive typing; synced via `useEffect` when
  the loaded value changes
- Saves on `onBlur` only if the clamped value differs from the loaded value
  (avoids spurious PUT requests)
- Input disabled while `isPending`

## Rendering (Settings/index.tsx)

`ContextWindowSizeRow` is lazy-loaded from `TranslationTab` and rendered inside
the Translation tab card, after the standard `tabFields.map(...)` block and
before the `GlobalGlossaryPanel`.

## Config entry

Key: `translation.context_window_size`  
Type: string-encoded integer (consistent with all other `config_entries`)  
Default (frontend): `3` when key is absent  
Range: 0–10 (clamped in `onChange` and `onBlur`)  
Storage: `config_entries` table, via `save_config_entry` / `get_config_entry`

## Verification

- `npx tsc --noEmit` passes with zero errors
- `python3 -m py_compile backend/routes/config.py` passes
- Manual flow: open Settings > Translation, change value, blur field → PUT /config
  is called; refresh page → value is restored from DB
