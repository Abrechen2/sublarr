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
 * /settings/webhooks  → WebhooksPage
 */
import { lazy, Suspense } from 'react'
import { Routes, Route } from 'react-router-dom'
import { FormSkeleton } from '@/components/shared/PageSkeleton'
import { AdvancedSettingsProvider } from '@/contexts/AdvancedSettingsContext'

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
const AboutSettings = lazy(() =>
  import('./AboutSettings').then((m) => ({ default: m.AboutSettings })),
)
const HooksPage = lazy(() =>
  import('./HooksPage').then((m) => ({ default: m.HooksPage })),
)
const WebhooksPage = lazy(() =>
  import('./WebhooksPage').then((m) => ({ default: m.WebhooksPage })),
)
const CleanupSettings = lazy(() =>
  import('./CleanupSettings').then((m) => ({ default: m.CleanupSettings })),
)

export function SettingsPage() {
  return (
    <AdvancedSettingsProvider>
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
        <Route path="about" element={<AboutSettings />} />
        <Route path="cleanup" element={<Suspense fallback={<FormSkeleton />}><CleanupSettings /></Suspense>} />
        <Route path="hooks" element={<HooksPage />} />
        <Route path="webhooks" element={<WebhooksPage />} />
      </Routes>
    </Suspense>
    </AdvancedSettingsProvider>
  )
}
