/**
 * Settings Router — maps /settings/* sub-routes to category pages.
 *
 * /settings           → SettingsOverview (card grid)
 * /settings/general   → GeneralSettings
 * /settings/connections → ConnectionsSettings
 * /settings/subtitles → SubtitlesSettings
 * /settings/providers → ProvidersSettings
 * /settings/automation → AutomationSettings
 * /settings/translation → TranslationSettings
 * /settings/notifications → NotificationsSettings
 * /settings/system    → SystemSettings
 */
import { lazy, Suspense } from 'react'
import { Routes, Route } from 'react-router-dom'
import { FormSkeleton } from '@/components/shared/PageSkeleton'

// Re-export legacy types/constants needed by other files
export { NAV_GROUPS } from './LegacySettings'
export type { FieldConfig } from './LegacySettings'

// Lazy-load each settings category page
const SettingsOverview = lazy(() =>
  import('./SettingsOverview').then((m) => ({ default: m.SettingsOverview })),
)
const GeneralSettings = lazy(() =>
  import('./GeneralSettings').then((m) => ({ default: m.GeneralSettings })),
)
const ConnectionsSettings = lazy(() =>
  import('./ConnectionsSettings').then((m) => ({ default: m.ConnectionsSettings })),
)
const SubtitlesSettings = lazy(() =>
  import('./SubtitlesSettings').then((m) => ({ default: m.SubtitlesSettings })),
)
const ProvidersSettings = lazy(() =>
  import('./ProvidersSettings').then((m) => ({ default: m.ProvidersSettings })),
)
const AutomationSettings = lazy(() =>
  import('./AutomationSettings').then((m) => ({ default: m.AutomationSettings })),
)
const TranslationSettings = lazy(() =>
  import('./TranslationSettings').then((m) => ({ default: m.TranslationSettings })),
)
const NotificationsSettings = lazy(() =>
  import('./NotificationsSettings').then((m) => ({ default: m.NotificationsSettings })),
)
const SystemSettings = lazy(() =>
  import('./SystemSettings').then((m) => ({ default: m.SystemSettings })),
)

export function SettingsPage() {
  return (
    <Suspense fallback={<FormSkeleton />}>
      <Routes>
        <Route index element={<SettingsOverview />} />
        <Route path="general" element={<GeneralSettings />} />
        <Route path="connections" element={<ConnectionsSettings />} />
        <Route path="subtitles" element={<SubtitlesSettings />} />
        <Route path="providers" element={<ProvidersSettings />} />
        <Route path="automation" element={<AutomationSettings />} />
        <Route path="translation" element={<TranslationSettings />} />
        <Route path="notifications" element={<NotificationsSettings />} />
        <Route path="system" element={<SystemSettings />} />
      </Routes>
    </Suspense>
  )
}
