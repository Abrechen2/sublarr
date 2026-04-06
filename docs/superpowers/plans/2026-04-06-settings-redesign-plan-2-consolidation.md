# Settings Redesign — Plan 2: Consolidation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move misplaced settings to their correct locations (AniDB → Connections, Remux → Subtitles, Whisper → Provider), extract Post-Processing into its own page, merge Hooks + Webhooks into one page, remove the Cleanup duplicate from SubtitlesSettings/AutomationSettings, update routing, and delete LegacySettings.tsx dead code.

**Architecture:** Create 5 new page files by wrapping existing tab components in `SettingsDetailLayout`. Modify 5 existing pages to remove the extracted sections. Update `index.tsx` routes. The existing tab components (AnidbTab, RemuxTab, WhisperTab) are not modified — they are just re-homed. `LegacySettings.tsx` exports are migrated before deletion.

**Prerequisite:** Plan 1 (Foundation Components) must be completed first.

**Tech Stack:** React 19, TypeScript, React Router v6, react-i18next (namespace `settings`)

**Branch:** `feature/settings-redesign`

---

## File Map

| File | Change |
|------|--------|
| `frontend/src/pages/settings/ConnectionsMetadataPage.tsx` | **Create** — wraps AnidbTab in SettingsDetailLayout |
| `frontend/src/pages/settings/SubtitlesStreamManagementPage.tsx` | **Create** — wraps RemuxTab in SettingsDetailLayout |
| `frontend/src/pages/settings/ProvidersTranscriptionPage.tsx` | **Create** — wraps WhisperTab in SettingsDetailLayout |
| `frontend/src/pages/settings/AutomationPostProcessingPage.tsx` | **Create** — extracts ProcessingPipelineContent from AutomationSettings |
| `frontend/src/pages/settings/SystemHooksPage.tsx` | **Create** — merges HooksPage + WebhooksPage |
| `frontend/src/pages/settings/index.tsx` | Modify — add 5 new routes, redirect old hooks/webhooks routes |
| `frontend/src/pages/settings/SystemSettings.tsx` | Modify — remove AnidbTab and RemuxTab sections, add navigation links |
| `frontend/src/pages/settings/TranslationSettings.tsx` | Modify — remove WhisperTab section |
| `frontend/src/pages/settings/AutomationSettings.tsx` | Modify — remove ProcessingPipelineContent section |
| `frontend/src/pages/settings/SubtitlesSettings.tsx` | Modify — remove CleanupContent section (lives in AutomationSettings currently) |
| `frontend/src/components/settings/SettingsGrid.tsx` | Modify — update tile descriptions to match new structure |
| `frontend/src/pages/settings/settingsFields.ts` | Modify — update NAV_GROUPS to match new IA |
| `frontend/src/pages/settings/LegacySettings.tsx` | **Delete** — after migrating exports |
| `frontend/src/i18n/locales/en/settings.json` | Add page titles for new pages |
| `frontend/src/i18n/locales/de/settings.json` | Same in German |

---

### Task 1: Add i18n keys for new page titles

**Files:**
- Modify: `frontend/src/i18n/locales/en/settings.json`
- Modify: `frontend/src/i18n/locales/de/settings.json`

- [ ] **Step 1: Add to EN settings.json**

Add these keys at the top level of `frontend/src/i18n/locales/en/settings.json`:

```json
  "metadata_page": {
    "title": "Metadata",
    "subtitle": "AniDB ID resolution and scan engine configuration"
  },
  "stream_management_page": {
    "title": "Stream Management",
    "subtitle": "Remux subtitle streams from video containers"
  },
  "transcription_page": {
    "title": "Transcription",
    "subtitle": "Speech-to-text backends for generating subtitles from audio"
  },
  "post_processing_page": {
    "title": "Post-Processing",
    "subtitle": "Automatically apply fixes, sync and cleanup after subtitle download"
  },
  "system_hooks_page": {
    "title": "Hooks & Webhooks",
    "subtitle": "Shell hooks and incoming webhook endpoints for Sonarr, Radarr and Jellyfin"
  },
```

- [ ] **Step 2: Add to DE settings.json**

```json
  "metadata_page": {
    "title": "Metadaten",
    "subtitle": "AniDB-ID-Auflösung und Scan-Engine-Konfiguration"
  },
  "stream_management_page": {
    "title": "Stream-Verwaltung",
    "subtitle": "Untertitel-Streams aus Video-Containern extrahieren und verwalten"
  },
  "transcription_page": {
    "title": "Transkription",
    "subtitle": "Speech-to-Text-Backends zur Untertitel-Generierung aus Audio"
  },
  "post_processing_page": {
    "title": "Post-Processing",
    "subtitle": "Automatisch Fixes, Sync und Bereinigung nach dem Untertitel-Download"
  },
  "system_hooks_page": {
    "title": "Hooks & Webhooks",
    "subtitle": "Shell-Hooks und eingehende Webhook-Endpunkte für Sonarr, Radarr und Jellyfin"
  },
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/i18n/locales/en/settings.json frontend/src/i18n/locales/de/settings.json
git commit -m "feat: add i18n keys for new consolidated settings pages"
```

---

### Task 2: Create ConnectionsMetadataPage

**Files:**
- Create: `frontend/src/pages/settings/ConnectionsMetadataPage.tsx`

AnidbTab is already a standalone component. This page just wraps it with the correct layout and breadcrumb.

- [ ] **Step 1: Read AnidbTab to confirm its import path**

```bash
cat frontend/src/pages/settings/AnidbTab.tsx | head -5
```

Expected output: file starts with imports, exports `AnidbTab` as a named export.

- [ ] **Step 2: Create the page**

Create `frontend/src/pages/settings/ConnectionsMetadataPage.tsx`:

```tsx
import { lazy, Suspense } from 'react'
import { useTranslation } from 'react-i18next'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { FormSkeleton } from '@/components/shared/PageSkeleton'

const AnidbTab = lazy(() => import('./AnidbTab').then((m) => ({ default: m.AnidbTab })))

export function ConnectionsMetadataPage() {
  const { t } = useTranslation('settings')
  return (
    <SettingsDetailLayout
      title={t('metadata_page.title')}
      subtitle={t('metadata_page.subtitle')}
      breadcrumb={[
        { label: t('title'), href: '/settings' },
        { label: t('categories.connections', 'Connections'), href: '/settings/connections' },
        { label: t('metadata_page.title') },
      ]}
    >
      <Suspense fallback={<FormSkeleton />}>
        <AnidbTab />
      </Suspense>
    </SettingsDetailLayout>
  )
}
```

- [ ] **Step 3: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors related to this file.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/settings/ConnectionsMetadataPage.tsx
git commit -m "feat: add ConnectionsMetadataPage wrapping AnidbTab"
```

---

### Task 3: Create SubtitlesStreamManagementPage

**Files:**
- Create: `frontend/src/pages/settings/SubtitlesStreamManagementPage.tsx`

- [ ] **Step 1: Create the page**

Create `frontend/src/pages/settings/SubtitlesStreamManagementPage.tsx`:

```tsx
import { lazy, Suspense } from 'react'
import { useTranslation } from 'react-i18next'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { FormSkeleton } from '@/components/shared/PageSkeleton'

const RemuxTab = lazy(() => import('./RemuxTab').then((m) => ({ default: m.RemuxTab })))

export function SubtitlesStreamManagementPage() {
  const { t } = useTranslation('settings')
  return (
    <SettingsDetailLayout
      title={t('stream_management_page.title')}
      subtitle={t('stream_management_page.subtitle')}
      breadcrumb={[
        { label: t('title'), href: '/settings' },
        { label: t('categories.subtitles', 'Subtitles'), href: '/settings/subtitles' },
        { label: t('stream_management_page.title') },
      ]}
    >
      <Suspense fallback={<FormSkeleton />}>
        <RemuxTab />
      </Suspense>
    </SettingsDetailLayout>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/settings/SubtitlesStreamManagementPage.tsx
git commit -m "feat: add SubtitlesStreamManagementPage wrapping RemuxTab"
```

---

### Task 4: Create ProvidersTranscriptionPage

**Files:**
- Create: `frontend/src/pages/settings/ProvidersTranscriptionPage.tsx`

- [ ] **Step 1: Create the page**

Create `frontend/src/pages/settings/ProvidersTranscriptionPage.tsx`:

```tsx
import { lazy, Suspense } from 'react'
import { useTranslation } from 'react-i18next'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { FormSkeleton } from '@/components/shared/PageSkeleton'

const WhisperTab = lazy(() => import('./WhisperTab').then((m) => ({ default: m.WhisperTab })))

export function ProvidersTranscriptionPage() {
  const { t } = useTranslation('settings')
  return (
    <SettingsDetailLayout
      title={t('transcription_page.title')}
      subtitle={t('transcription_page.subtitle')}
      breadcrumb={[
        { label: t('title'), href: '/settings' },
        { label: t('categories.providers', 'Providers'), href: '/settings/providers' },
        { label: t('transcription_page.title') },
      ]}
    >
      <Suspense fallback={<FormSkeleton />}>
        <WhisperTab />
      </Suspense>
    </SettingsDetailLayout>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/settings/ProvidersTranscriptionPage.tsx
git commit -m "feat: add ProvidersTranscriptionPage wrapping WhisperTab"
```

---

### Task 5: Create AutomationPostProcessingPage

**Files:**
- Modify: `frontend/src/pages/settings/AutomationSettings.tsx`
- Create: `frontend/src/pages/settings/AutomationPostProcessingPage.tsx`

The post-processing pipeline is in `ProcessingPipelineContent()` inside `AutomationSettings.tsx` (approx lines 401–613). This task extracts it into its own file.

- [ ] **Step 1: Read AutomationSettings to find the exact content to extract**

```bash
sed -n '395,620p' frontend/src/pages/settings/AutomationSettings.tsx
```

This shows the `ProcessingPipelineContent` function. Copy its complete body.

- [ ] **Step 2: Create AutomationPostProcessingPage**

Create `frontend/src/pages/settings/AutomationPostProcessingPage.tsx`. The file should:
1. Import all hooks and components used by `ProcessingPipelineContent`
2. Export a page component `AutomationPostProcessingPage` that wraps the content in `SettingsDetailLayout`

Pattern:
```tsx
import { useTranslation } from 'react-i18next'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
// ... all imports that were used in ProcessingPipelineContent

export function AutomationPostProcessingPage() {
  const { t } = useTranslation('settings')
  // ... all hooks that were used in ProcessingPipelineContent
  return (
    <SettingsDetailLayout
      title={t('post_processing_page.title')}
      subtitle={t('post_processing_page.subtitle')}
      breadcrumb={[
        { label: t('title'), href: '/settings' },
        { label: t('categories.automation', 'Automation'), href: '/settings/automation' },
        { label: t('post_processing_page.title') },
      ]}
    >
      {/* paste the JSX from ProcessingPipelineContent here */}
    </SettingsDetailLayout>
  )
}
```

- [ ] **Step 3: Remove ProcessingPipelineContent from AutomationSettings**

In `AutomationSettings.tsx`:
1. Delete the `ProcessingPipelineContent` function definition
2. Find where it is rendered in the main component (search for `<ProcessingPipelineContent`) and remove that `<SettingsSection>` block
3. Remove any imports that are now only used by the deleted code

- [ ] **Step 4: Add a navigation link in AutomationSettings pointing to the new page**

In `AutomationSettings.tsx`, where the Post-Processing section was, add a link card:

```tsx
import { Link } from 'react-router-dom'
// ...
<div
  style={{
    padding: '14px 18px',
    background: 'var(--bg-surface)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-lg)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
  }}
>
  <div>
    <div style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>
      {t('post_processing_page.title')}
    </div>
    <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: 2 }}>
      {t('post_processing_page.subtitle')}
    </div>
  </div>
  <Link
    to="/settings/automation/post-processing"
    style={{ fontSize: '12px', color: 'var(--accent)' }}
  >
    {t('common:actions.configure', 'Configure')} →
  </Link>
</div>
```

- [ ] **Step 5: TypeScript and lint check**

```bash
cd frontend && npx tsc --noEmit && npm run lint
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/settings/AutomationPostProcessingPage.tsx frontend/src/pages/settings/AutomationSettings.tsx
git commit -m "feat: extract post-processing into AutomationPostProcessingPage"
```

---

### Task 6: Create SystemHooksPage (merge HooksPage + WebhooksPage)

**Files:**
- Create: `frontend/src/pages/settings/SystemHooksPage.tsx`

`HooksPage` handles shell hooks + execution log. `WebhooksPage` shows read-only webhook URLs for Sonarr/Radarr/Jellyfin (copy buttons). Both are small enough to be on one page with two sections.

- [ ] **Step 1: Read both pages fully**

```bash
cat frontend/src/pages/settings/HooksPage.tsx
cat frontend/src/pages/settings/WebhooksPage.tsx
```

- [ ] **Step 2: Create SystemHooksPage**

Create `frontend/src/pages/settings/SystemHooksPage.tsx`. Combine both into one page:

```tsx
import { useTranslation } from 'react-i18next'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
// copy all imports from HooksPage.tsx
// copy all imports from WebhooksPage.tsx (deduplicate)

// copy WEBHOOKS constant from WebhooksPage.tsx
const WEBHOOKS = [
  { service: 'Sonarr', path: '/api/v1/webhook/sonarr', descKey: 'webhooks_page.sonarr_desc' },
  { service: 'Radarr', path: '/api/v1/webhook/radarr', descKey: 'webhooks_page.radarr_desc' },
  { service: 'Jellyfin', path: '/api/v1/webhook/jellyfin', descKey: 'webhooks_page.jellyfin_desc' },
] as const

export function SystemHooksPage() {
  const { t } = useTranslation('settings')

  return (
    <SettingsDetailLayout
      title={t('system_hooks_page.title')}
      subtitle={t('system_hooks_page.subtitle')}
      breadcrumb={[
        { label: t('title'), href: '/settings' },
        { label: t('categories.system', 'System'), href: '/settings/system' },
        { label: t('system_hooks_page.title') },
      ]}
    >
      {/* Section 1: Incoming Webhooks — paste JSX from WebhooksPage */}
      {/* Section 2: Shell Hooks — paste JSX from HooksPage */}
      {/* Section 3: Execution Log — paste from HooksPage */}
    </SettingsDetailLayout>
  )
}
```

Fill in the actual JSX by copying verbatim from the existing files. Keep all hooks and state local.

- [ ] **Step 3: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/settings/SystemHooksPage.tsx
git commit -m "feat: add SystemHooksPage consolidating HooksPage + WebhooksPage"
```

---

### Task 7: Update routing in index.tsx

**Files:**
- Modify: `frontend/src/pages/settings/index.tsx`

- [ ] **Step 1: Read the current index.tsx**

```bash
cat frontend/src/pages/settings/index.tsx
```

- [ ] **Step 2: Replace index.tsx with updated routing**

The new routes to add (add lazy imports + Route entries):

```tsx
// New lazy imports to add:
const ConnectionsMetadataPage = lazy(() =>
  import('./ConnectionsMetadataPage').then((m) => ({ default: m.ConnectionsMetadataPage })),
)
const SubtitlesStreamManagementPage = lazy(() =>
  import('./SubtitlesStreamManagementPage').then((m) => ({ default: m.SubtitlesStreamManagementPage })),
)
const ProvidersTranscriptionPage = lazy(() =>
  import('./ProvidersTranscriptionPage').then((m) => ({ default: m.ProvidersTranscriptionPage })),
)
const AutomationPostProcessingPage = lazy(() =>
  import('./AutomationPostProcessingPage').then((m) => ({ default: m.AutomationPostProcessingPage })),
)
const SystemHooksPage = lazy(() =>
  import('./SystemHooksPage').then((m) => ({ default: m.SystemHooksPage })),
)
```

New routes to add in the `<Routes>` block:

```tsx
<Route path="connections/metadata" element={<ConnectionsMetadataPage />} />
<Route path="subtitles/stream-management" element={<SubtitlesStreamManagementPage />} />
<Route path="providers/transcription" element={<ProvidersTranscriptionPage />} />
<Route path="automation/post-processing" element={<AutomationPostProcessingPage />} />
<Route path="system/hooks" element={<SystemHooksPage />} />
```

Replace old hooks/webhooks routes with redirects (keep old URLs working):

```tsx
// Replace:
<Route path="hooks" element={<HooksPage />} />
<Route path="webhooks" element={<WebhooksPage />} />
// With:
<Route path="hooks" element={<Navigate to="/settings/system/hooks" replace />} />
<Route path="webhooks" element={<Navigate to="/settings/system/hooks" replace />} />
```

Add `Navigate` to imports: `import { Routes, Route, Navigate } from 'react-router-dom'`

- [ ] **Step 3: Remove the `export { NAV_GROUPS }` re-export from LegacySettings**

In `index.tsx`, remove this line:
```tsx
export { NAV_GROUPS } from './LegacySettings'
export type { FieldConfig } from './LegacySettings'
```

These exports are only used by `LegacySettings` itself. Grep first to confirm:
```bash
cd frontend && grep -r "NAV_GROUPS\|FieldConfig" src/ --include="*.tsx" --include="*.ts" | grep -v LegacySettings
```

If any other file uses them, update those imports to point to `./settingsFields` directly before removing.

- [ ] **Step 4: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/settings/index.tsx
git commit -m "feat: add routes for new consolidated settings pages, redirect old hooks/webhooks"
```

---

### Task 8: Remove AniDB and Remux from SystemSettings

**Files:**
- Modify: `frontend/src/pages/settings/SystemSettings.tsx`

- [ ] **Step 1: Read SystemSettings to find the AniDB and Remux sections**

```bash
sed -n '370,415p' frontend/src/pages/settings/SystemSettings.tsx
```

- [ ] **Step 2: Remove AnidbTab section**

Find and delete the entire `<SettingsSection>` block that renders `<AnidbTab />`. Also remove the lazy import:
```tsx
// Remove:
const AnidbTab = lazy(() => import('./AnidbTab').then((m) => ({ default: m.AnidbTab })))
```

- [ ] **Step 3: Remove RemuxTab section**

Same: find and delete the `<SettingsSection>` block that renders `<RemuxTab />` and its lazy import.

- [ ] **Step 4: Add navigation links to the new pages**

In the System tabs/sections where AniDB and Remux were, add link cards pointing to their new locations. Follow the same link card pattern used in Task 5 Step 4, pointing to `/settings/connections/metadata` and `/settings/subtitles/stream-management`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/settings/SystemSettings.tsx
git commit -m "feat: remove AniDB and Remux from SystemSettings, add navigation links"
```

---

### Task 9: Remove WhisperTab from TranslationSettings

**Files:**
- Modify: `frontend/src/pages/settings/TranslationSettings.tsx`

- [ ] **Step 1: Find the WhisperTab section**

```bash
sed -n '225,260p' frontend/src/pages/settings/TranslationSettings.tsx
```

- [ ] **Step 2: Remove WhisperTab section and its lazy import**

Delete the `<SettingsSection>` block that renders `<WhisperTab />` and its lazy import at line ~49.

- [ ] **Step 3: Add navigation link to Providers > Transcription**

In the section where Whisper was, add a link card to `/settings/providers/transcription`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/settings/TranslationSettings.tsx
git commit -m "feat: remove WhisperTab from TranslationSettings, add link to Providers > Transcription"
```

---

### Task 10: Remove duplicate Cleanup from AutomationSettings

**Files:**
- Modify: `frontend/src/pages/settings/AutomationSettings.tsx`

The Cleanup content (auto_cleanup_after_extract, auto_cleanup_keep_languages, etc.) is in `CleanupContent()` inside AutomationSettings — it's a duplicate of what's on the dedicated `/settings/cleanup` page.

- [ ] **Step 1: Find CleanupContent in AutomationSettings**

```bash
grep -n "CleanupContent\|cleanup_after_extract\|cleanup_keep" frontend/src/pages/settings/AutomationSettings.tsx
```

- [ ] **Step 2: Delete CleanupContent function and its usage**

Remove the `CleanupContent` function definition and the `<SettingsSection>` block that renders it.

- [ ] **Step 3: Add navigation link to the Cleanup page**

Add a link card to `/settings/cleanup` where CleanupContent was.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/settings/AutomationSettings.tsx
git commit -m "feat: remove duplicate CleanupContent from AutomationSettings, link to /settings/cleanup"
```

---

### Task 11: Remove HooksPage and WebhooksPage source files

**Files:**
- Delete: `frontend/src/pages/settings/HooksPage.tsx`
- Delete: `frontend/src/pages/settings/WebhooksPage.tsx`

- [ ] **Step 1: Confirm no other file imports HooksPage or WebhooksPage**

```bash
cd frontend && grep -r "HooksPage\|WebhooksPage" src/ --include="*.tsx" --include="*.ts"
```

Expected: only `index.tsx` references them (via the redirect routes, which don't import the components directly anymore).

- [ ] **Step 2: Remove the redirect route lazy imports from index.tsx**

Since the redirect routes don't render the old components, also remove their lazy import lines:
```tsx
// Remove these if still present:
const HooksPage = lazy(...)
const WebhooksPage = lazy(...)
```

- [ ] **Step 3: Delete the files**

```bash
rm frontend/src/pages/settings/HooksPage.tsx
rm frontend/src/pages/settings/WebhooksPage.tsx
```

- [ ] **Step 4: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: delete HooksPage and WebhooksPage (merged into SystemHooksPage)"
```

---

### Task 12: Delete LegacySettings.tsx

**Files:**
- Delete: `frontend/src/pages/settings/LegacySettings.tsx`

- [ ] **Step 1: Confirm no remaining imports**

```bash
cd frontend && grep -r "LegacySettings\|from.*settingsFields\|NAV_GROUPS\|FieldConfig\|TAB_KEYS\|TABS\b" src/ --include="*.tsx" --include="*.ts"
```

If any file still imports from LegacySettings, update it to either import from `./settingsFields` (for NAV_GROUPS, FIELDS) or remove the import if the values are unused.

- [ ] **Step 2: Delete the file**

```bash
rm frontend/src/pages/settings/LegacySettings.tsx
```

- [ ] **Step 3: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Run full test suite**

```bash
cd frontend && npm run test -- --run
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: delete LegacySettings.tsx dead code"
```

---

### Task 13: Update SettingsGrid tiles to match new structure

**Files:**
- Modify: `frontend/src/components/settings/SettingsGrid.tsx`

The tile descriptions need to reflect the new page structure. Also the `cleanup` tile should remain and its description updated. No tiles are added or removed in this plan — tile count changes happen in Plan 3.

- [ ] **Step 1: Update i18n description keys in EN settings.json**

Find these keys and update them:

```json
"settings": {
  "categories": {
    "connections": {
      "description": "Sonarr, Radarr, Media Servers, Metadata"
    },
    "subtitles": {
      "description": "Languages, Scoring, Format, Stream Management"
    },
    "providers": {
      "description": "Download sources and Transcription (Whisper)"
    },
    "automation": {
      "description": "Scheduling, Upgrades, Post-Processing"
    },
    "system": {
      "description": "Security, Backup, Logs, Hooks & Webhooks"
    }
  }
}
```

Update the DE equivalents:
```json
"connections": { "description": "Sonarr, Radarr, Media-Server, Metadaten" },
"subtitles": { "description": "Sprachen, Scoring, Format, Stream-Verwaltung" },
"providers": { "description": "Download-Quellen und Transkription (Whisper)" },
"automation": { "description": "Zeitpläne, Upgrades, Post-Processing" },
"system": { "description": "Sicherheit, Backup, Protokoll, Hooks & Webhooks" }
```

- [ ] **Step 2: TypeScript and lint**

```bash
cd frontend && npx tsc --noEmit && npm run lint
```

- [ ] **Step 3: Visual check**

Start the dev server. Navigate to /settings. Verify:
- Tile for Connections shows updated description ✓
- Tile for System no longer mentions AniDB or Remux ✓
- Navigating to /settings/hooks redirects to /settings/system/hooks ✓
- Navigating to /settings/webhooks redirects to /settings/system/hooks ✓
- New routes /settings/connections/metadata, /settings/subtitles/stream-management, /settings/providers/transcription, /settings/automation/post-processing all render correctly ✓

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/settings/SettingsGrid.tsx frontend/src/i18n/locales/en/settings.json frontend/src/i18n/locales/de/settings.json
git commit -m "feat: update SettingsGrid tile descriptions to reflect new IA"
```
