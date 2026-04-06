/**
 * Settings Router — maps /settings/* sub-routes to category pages.
 *
 * /settings                             → SettingsOverview (card grid)
 * /settings/general                     → GeneralSettings
 * /settings/connections                 → ConnectionsSettings
 * /settings/connections/metadata        → ConnectionsMetadataPage
 * /settings/subtitles                   → SubtitlesSettings
 * /settings/subtitles/stream-management → SubtitlesStreamManagementPage
 * /settings/providers                   → ProvidersSettings
 * /settings/providers/transcription     → ProvidersTranscriptionPage
 * /settings/automation                  → AutomationSettings
 * /settings/automation/post-processing  → AutomationPostProcessingPage
 * /settings/translation                 → TranslationSettings
 * /settings/notifications               → NotificationsSettings
 * /settings/system                      → SystemSettings
 * /settings/system/hooks                → SystemHooksPage
 * /settings/hooks                       → redirect → /settings/system/hooks
 * /settings/webhooks                    → redirect → /settings/system/hooks
 */
import { lazy, Suspense } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { FormSkeleton } from '@/components/shared/PageSkeleton'
import { AdvancedSettingsProvider } from '@/contexts/AdvancedSettingsContext'

// Re-export legacy types/constants needed by other files
export { NAV_GROUPS } from './settingsFields'
export type { FieldConfig } from './settingsFields'

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
const ConnectionsMetadataPage = lazy(() =>
  import('./ConnectionsMetadataPage').then((m) => ({ default: m.ConnectionsMetadataPage })),
)
const SubtitlesSettings = lazy(() =>
  import('./SubtitlesSettings').then((m) => ({ default: m.SubtitlesSettings })),
)
const SubtitlesStreamManagementPage = lazy(() =>
  import('./SubtitlesStreamManagementPage').then((m) => ({ default: m.SubtitlesStreamManagementPage })),
)
const ProvidersSettings = lazy(() =>
  import('./ProvidersSettings').then((m) => ({ default: m.ProvidersSettings })),
)
const ProvidersTranscriptionPage = lazy(() =>
  import('./ProvidersTranscriptionPage').then((m) => ({ default: m.ProvidersTranscriptionPage })),
)
const AutomationSettings = lazy(() =>
  import('./AutomationSettings').then((m) => ({ default: m.AutomationSettings })),
)
const AutomationPostProcessingPage = lazy(() =>
  import('./AutomationPostProcessingPage').then((m) => ({ default: m.AutomationPostProcessingPage })),
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
const SystemHooksPage = lazy(() =>
  import('./SystemHooksPage').then((m) => ({ default: m.SystemHooksPage })),
)
const AboutSettings = lazy(() =>
  import('./AboutSettings').then((m) => ({ default: m.AboutSettings })),
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
        <Route path="connections/metadata" element={<ConnectionsMetadataPage />} />
        <Route path="subtitles" element={<SubtitlesSettings />} />
        <Route path="subtitles/stream-management" element={<SubtitlesStreamManagementPage />} />
        <Route path="providers" element={<ProvidersSettings />} />
        <Route path="providers/transcription" element={<ProvidersTranscriptionPage />} />
        <Route path="automation" element={<AutomationSettings />} />
        <Route path="automation/post-processing" element={<AutomationPostProcessingPage />} />
        <Route path="translation" element={<TranslationSettings />} />
        <Route path="notifications" element={<NotificationsSettings />} />
        <Route path="system" element={<SystemSettings />} />
        <Route path="system/hooks" element={<SystemHooksPage />} />
        <Route path="about" element={<AboutSettings />} />
        <Route path="cleanup" element={<Suspense fallback={<FormSkeleton />}><CleanupSettings /></Suspense>} />
        <Route path="hooks" element={<Navigate to="/settings/system/hooks" replace />} />
        <Route path="webhooks" element={<Navigate to="/settings/system/hooks" replace />} />
      </Routes>
    </Suspense>
    </AdvancedSettingsProvider>
  )
}
