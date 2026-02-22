# Phase 28-01 — LLM Backend Presets: Summary

## What was implemented

### Backend (`backend/routes/translate.py`)

- Added `BACKEND_TEMPLATES` list constant (after Blueprint definition, before batch state) with 5 pre-configured templates:
  - **DeepSeek V3** — `https://api.deepseek.com/v1`, model `deepseek-chat`, 64k context
  - **Gemini 1.5 Flash** — `https://generativelanguage.googleapis.com/v1beta/openai`, 128k context
  - **Claude 3 Haiku** — `https://api.anthropic.com/v1`, 32k context
  - **Mistral Medium** — `https://api.mistral.ai/v1`, 32k context
  - **LM Studio (local)** — `http://localhost:1234/v1`, no API key required, 8k context
- Added `GET /api/v1/backends/templates` route returning `{ templates: [...] }`, placed alongside the other `/backends/*` management routes.

### Frontend API client (`frontend/src/api/client.ts`)

- Added `BackendTemplate` interface (exported)
- Added `getBackendTemplates()` async function calling `GET /backends/templates`

### Frontend hooks (`frontend/src/hooks/useApi.ts`)

- Added `useBackendTemplates()` hook using `useQuery` with `staleTime: Infinity` (templates are static)
- Added `getBackendTemplates` to imports from client.ts

### Frontend UI (`frontend/src/pages/Settings/TranslationTab.tsx`)

- Added `Wand2` to lucide-react imports, added `useBackendTemplates` hook import
- Added `TemplatePickerModal` component (inline):
  - Full-screen overlay modal listing all templates from the API
  - Each template row shows display_name (bold), description (muted), and base_url (monospace)
  - Click-to-select calls onApply(backend_type, config) converting config_defaults values to strings
  - Click outside or X button closes the modal
- Updated `TranslationBackendsTab`:
  - Added `showTemplatePicker` state and `handleApplyTemplate` handler
  - `handleApplyTemplate` calls PUT /backends/<backend_type>/config via useSaveBackendConfig mutation
    with the template's config_defaults (without API key), then shows a toast directing the user
    to open the backend card and add their key
  - Added "Add from Template" button (Wand2 icon) in the header row next to the backend count label

## User flow

1. User navigates to Settings > Translation > Translation Backends
2. Clicks "Add from Template"
3. Modal appears listing all 5 templates with descriptions
4. User clicks a template (e.g. "DeepSeek V3")
5. Config is saved: base_url, model, context_window for the openai_compat backend
6. Toast: "Template applied — open the openai_compat backend card to add your API key and save"
7. User expands the openai_compat card, sees pre-filled values, enters their API key, saves

## Verification

- python -m py_compile backend/routes/translate.py — passes
- npx tsc --noEmit — zero TypeScript errors
- No existing functionality was changed
