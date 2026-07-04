# Translation Backend Selector — Design Spec

**Date:** 2026-07-01
**Status:** Approved (brainstorming) — pending implementation plan
**Author:** Claude + Dennis

## Problem

Sublarr ships a multi-backend translation system (Ollama, DeepL, OpenAI-compat,
Claude, Gemini, DeepSeek, Mistral, ChatGPT, Azure, Google, LibreTranslate,
MyMemory). The backend actually used at translation time is resolved **per
language profile** by `_resolve_backend_for_context` from the profile's
`translation_backend` (primary) + `fallback_chain_json` columns.

**The gap:** those columns have **no UI**. A user can *configure* a backend's
credentials on Settings → Translation → Backends & Glossary and *test* it, but
there is no way to *select* which backend translation actually uses. Configuring
DeepL does nothing — auto-translate keeps using whatever is in the DB column
(currently `ollama`). "Configured" (green badge) means "has credentials", not
"is used". The whole multi-backend system has no way to pick the winner.

This was discovered on 2026-07-01 while verifying translation end-to-end (see
memory `feedback_translation_backend_config_field_key`); the default profile had
also shipped with an *empty* backend/chain, which produced "All backends failed.
Last error: None" (fixed in 1.4.0-rc.3; the empty state is currently coerced to
`ollama`).

## Goal

Let the user choose which translation backend is used — globally and, optionally,
per language profile — with a single fallback backend, entirely from the UI.

## Non-Goals (YAGNI)

- N-length reorderable fallback chains. The user chose **primary + exactly one
  fallback**; the data model keeps the list shape (`fallback_chain_json`) but the
  UI exposes at most two entries.
- Cost-based / latency-based automatic routing between backends.
- Changing the quality-evaluation path (`evaluate_line_quality` keeps using the
  resolved chain as-is).
- Per-target-language backends (e.g. DeepL for `de`, Ollama for `fr`). The
  resolver already takes `target_language` but selection stays per-profile.

## What already exists (do not rebuild)

- **DB columns:** `language_profiles.translation_backend` (str) and
  `language_profiles.fallback_chain_json` (JSON text, default `["ollama"]`).
- **Profile API:** `POST`/`PUT` language-profile endpoints
  (`routes/profiles/language.py`) already document and accept `translation_backend`
  and `fallback_chain`; `update_profile()` / the repo already persist them
  (`db/repositories/profiles.py`). Only the **frontend** never sends them.
- **Backend list API:** `GET /api/v1/backends` returns every registered backend
  with `name`, `display_name`, `configured`, `supports_glossary`, etc.
- **Config read/write:** the generic config mutation (`useUpdateConfig` →
  `config_entries`) is already used across the Translation Backends page (sync
  engine, timeouts). No new endpoint is needed for the global default.
- **Resolver:** `_resolve_backend_for_context(arr_context, target_language)` in
  `translator/_helpers.py` returns `(backend, fallback_chain)` and is the single
  path all translation (manual, auto/wanted, webhook) funnels through via
  `translate_file` → `_translate_with_manager`.

## Design

### Inheritance model (the core idea)

A **global default** backend that profiles **inherit** unless they **override**.
An empty `profile.translation_backend` means "inherit the global default" — this
turns today's empty state from a latent bug into a first-class feature.

### Data model (no migration)

- **Global default (new):** two `config_entries` key/value rows (schemaless — no
  Alembic migration):
  - `translation_default_backend` — default `"ollama"`.
  - `translation_default_fallback` — default `""` (no fallback).
- **Per-profile (reuse existing columns):**
  - `translation_backend = ""` → inherit global default.
  - `translation_backend = "<name>"` → override primary.
  - `fallback_chain_json` → `[primary]` or `[primary, fallback]` (at most 2).

### Resolution (`_resolve_backend_for_context`)

```
1. Resolve the profile (series/movie profile, else default profile) — unchanged.
2. If profile.translation_backend is non-empty:
       primary  = profile.translation_backend
       fallback = second entry of profile.fallback_chain (if any, and != primary)
   Else (inherit):
       primary  = config translation_default_backend  (or "ollama" if empty)
       fallback = config translation_default_fallback  (if set and != primary)
3. chain = [primary] + ([fallback] if fallback else [])
4. return (primary, chain)
```

This preserves the rc.3 empty-safety (ends at `ollama`) but upgrades the fallback
target from hardcoded `ollama` to the configured global default. `fallback_chain`
entries are still de-duplicated and stripped of falsy values (rc.3 hardening
stays).

### API

- **Global default:** read via existing config read (`GET /api/v1/config` or the
  per-key hook the page already uses); write via the existing config mutation
  (`{ translation_default_backend: "deepl", translation_default_fallback: "ollama" }`).
  **No new backend endpoint.**
- **Per-profile:** the existing profile `PUT` already accepts `translation_backend`
  + `fallback_chain`; the frontend payload in `LanguageProfilesTab` is extended to
  include them. (Verify the endpoint whitelists both fields; extend if it filters.)
- **Backend list for the dropdowns:** reuse `GET /api/v1/backends`.

### UI

Two entry points (user chose "both"):

1. **Global default** — a new compact section on Settings → Translation →
   *Backends & Glossary* (`TranslationBackendsTab.tsx`), near the top of the
   backends list:
   - "Standard-Übersetzungs-Backend" — primary `<select>`.
   - "Fallback (optional)" — secondary `<select>`, with a "— kein Fallback —"
     option.
   - Saves via the config mutation on change (same pattern as the sync-engine
     select already on this page).

2. **Per-profile override** — in the profile add/edit form
   (`LanguageProfilesTab.tsx`):
   - "Übersetzungs-Backend" `<select>` whose first option is **"Standardvorgabe
     verwenden"** (value `""` = inherit); remaining options are the registered
     backends.
   - "Fallback (optional)" `<select>` shown **only when a primary override is
     chosen** (hidden while inheriting).
   - Both are added to the existing `handleSave` payload. Inheriting sends
     `translation_backend: ""`, `fallback_chain: []`.

3. **Shared component `BackendSelect`** — one reusable dropdown used in both
   places. Props: `value`, `onChange`, `backends` (from `GET /backends`),
   `includeInherit?` (adds the "Standardvorgabe" option — profile editor only),
   `includeNone?` (adds "— kein Fallback —" — fallback selects). Renders each
   backend by `display_name`; unconfigured backends (except `ollama`, which runs
   locally without a key) get a "(nicht konfiguriert)" suffix.

### Backend selectability & warnings

- All registered backends are selectable (not just configured ones) so the user
  can pre-select before configuring.
- Selecting an **unconfigured** backend (not `ollama`) shows a **non-blocking**
  inline warning near the control: "Backend X hat noch keinen Key —
  Übersetzung würde fehlschlagen." plus a link/anchor to that backend's card to
  configure it. Saving is still allowed (the warning, not a hard block).
- `configured` comes from `GET /backends`; `ollama` is treated as always-usable.

### Error handling

| Situation | Behaviour |
|---|---|
| Unconfigured backend selected | Soft inline warning + configure link; save allowed |
| Global default + profile both empty | Resolver falls back to `ollama` (safety net) |
| Fallback == primary | Fallback dropped (chain de-dups) |
| Primary fails at runtime | Engine tries the fallback (existing circuit-breaker/first-success logic) |
| RQ queue active with 0 workers | Startup ERROR log (already shipped in rc.3) — unchanged |

### Testing

- **Backend (`test_translator_helpers.py` — extend `TestResolveBackendForContext`):**
  - profile override → uses profile primary + its fallback.
  - profile empty + global default set → uses global default primary + fallback.
  - profile empty + global default empty → `ollama`.
  - `fallback == primary` → chain is `[primary]` (de-duped).
  - global default fallback applied only when non-empty.
- **Backend:** profile `PUT` round-trips `translation_backend` + `fallback_chain`
  (extend `test_routes_*profiles*` if not already covered).
- **Frontend:**
  - `TranslationBackendsTab` renders the global-default control and saves via the
    config mutation.
  - `LanguageProfilesTab` includes `translation_backend` + `fallback_chain` in the
    save payload; "Standardvorgabe verwenden" sends `""` / `[]`.
  - `BackendSelect` renders the "(nicht konfiguriert)" suffix and the unconfigured
    warning.

### i18n

New keys in `settings.json` (DE primary + EN mirror) for: global-default section
title/help, primary/fallback labels, "Standardvorgabe verwenden", "— kein
Fallback —", "(nicht konfiguriert)", the unconfigured warning + configure link.

### Migration

None. Columns exist; global default lives in schemaless `config_entries`. The
default empty profile state (`translation_backend=""`) already means "inherit",
which resolves to `translation_default_backend` (default `ollama`) — identical to
current behaviour, so **no backfill** and no behavioural change for existing
installs until the user picks something.

## Files touched

- **Backend:** `translator/_helpers.py` (`_resolve_backend_for_context` +
  read global-default config); `config_settings.py` only if the two default keys
  want Pydantic defaults (optional — config_entries default handled in the
  resolver); tests in `tests/test_translator_helpers.py` (+ profile route test).
- **Frontend:** `pages/Settings/translation/TranslationBackendsTab.tsx` (global
  control), `pages/Settings/LanguageProfilesTab.tsx` (override fields), new
  `components/settings/BackendSelect.tsx` (shared dropdown), `hooks/useApi.ts` if a
  backends-list hook isn't already exported, `i18n/locales/{de,en}/settings.json`,
  and matching `__tests__`.

## Open implementation checks (resolve during planning, not blockers)

1. Confirm the profile `PUT` endpoint/schema does not silently drop
   `translation_backend` / `fallback_chain` (repo persists them; verify the route
   layer passes them through).
2. Confirm a frontend hook already fetches `GET /backends` for reuse (BackendCard
   consumes backends via the parent tab — reuse that query).
3. Decide whether the two global-default keys also get Pydantic `Settings`
   defaults (nice for `getattr` reads) or are read purely from `config_entries` in
   the resolver (simpler, no `config_settings` churn). Lean: read from
   `config_entries` in the resolver, mirroring how backend config is loaded.
