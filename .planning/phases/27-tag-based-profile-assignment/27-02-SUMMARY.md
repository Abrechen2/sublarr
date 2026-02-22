# Phase 27-02 — Tag-based Profile Assignment Frontend

**Status:** Completed  
**Date:** 2026-02-22  
**Phase:** 27 — Tag-based Profile Assignment  
**Part:** 02 — Frontend

---

## Summary

Implemented the complete frontend for tag-based language profile assignment. Users can now define rules that automatically assign a language profile to any series or movie carrying a specific tag in their *arr application.

---

## Changes Made

### `frontend/src/lib/types.ts`
- Added `TagRule` interface:
  ```ts
  export interface TagRule {
    id: number
    tag_label: string
    profile_id: number
    profile_name?: string
  }
  ```

### `frontend/src/api/client.ts`
- Added `TagRule` to the import from `@/lib/types`
- Added four new API functions under the Language Profiles section:
  - `getTagRules()` — GET `/language-profiles/tag-rules`
  - `createTagRule(payload)` — POST `/language-profiles/tag-rules`
  - `updateTagRule(id, payload)` — PUT `/language-profiles/tag-rules/:id`
  - `deleteTagRule(id)` — DELETE `/language-profiles/tag-rules/:id`

### `frontend/src/hooks/useApi.ts`
- Added four new React Query hooks after the Language Profiles hook group:
  - `useTagRules()` — query with 5-minute staleTime
  - `useCreateTagRule()` — mutation, invalidates `tag-rules` on success
  - `useUpdateTagRule()` — mutation, invalidates `tag-rules` on success
  - `useDeleteTagRule()` — mutation, invalidates `tag-rules` on success

### `frontend/src/pages/Settings/AdvancedTab.tsx`
- Imported new hooks: `useTagRules`, `useCreateTagRule`, `useUpdateTagRule`, `useDeleteTagRule`
- Added `Tag` icon from lucide-react
- Added `TagRule` to the type imports
- Added new `TagRulesPanel` component (internal to the file)
- Integrated `TagRulesPanel` into `LanguageProfilesTab` at the bottom, wrapped in a surface card

---

## UI Design

The `TagRulesPanel` component is placed at the bottom of the Language Profiles tab, inside a surface card. It follows the exact same design conventions as the rest of the Settings UI:

- **Header row**: Tag icon + "Tag-based Profile Assignment" label + "Add Rule" button
- **Description**: Explains the automatic assignment behavior
- **Add form** (collapsible): Two-column grid with tag label (monospace input) + profile dropdown + Add/Cancel buttons. Enter key submits.
- **Rules list**: Column header row (Tag Label | Profile | Actions), then one row per rule
  - **Display row**: Monospace tag badge | profile name | Edit + Delete buttons
  - **Inline edit row**: Editable input + profile dropdown + Save (✓) + Cancel (✗) buttons. Enter saves, Escape cancels.
  - **Delete confirmation**: Inline two-button confirmation (Delete/Cancel) before actual deletion

---

## Patterns Used

- React Query with `queryKey: ['tag-rules']` for cache management
- Inline edit pattern (same as other Settings tabs — no modal)
- Delete confirmation via `confirmDeleteId` state (same as `LanguageProfilesTab`)
- CSS variables for all colors (`var(--accent)`, `var(--bg-surface)`, etc.)
- Tailwind for spacing, grid layout, and responsive behavior

---

## TypeScript Verification

```
cd frontend && npx tsc --noEmit
# Exit 0 — no errors
```
