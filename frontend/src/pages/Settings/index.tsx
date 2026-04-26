/**
 * Settings Router — maps /settings/* sub-routes to category pages.
 *
 * /settings                               → SettingsOverview (card grid)
 * /settings/general                       → GeneralSettings
 * /settings/connections                   → ConnectionsSettings
 * /settings/connections/metadata          → ConnectionsMetadataPage
 * /settings/subtitles                     → redirect → /settings/subtitles/scoring
 * /settings/subtitles/scoring             → SubtitlesScoringPage
 * /settings/subtitles/format              → SubtitlesFormatPage
 * /settings/subtitles/stream-management   → SubtitlesStreamManagementPage
 * /settings/providers                     → ProvidersSettings
 * /settings/providers/transcription       → ProvidersTranscriptionPage
 * /settings/automation                    → AutomationSettings
 * /settings/automation/post-processing    → AutomationPostProcessingPage
 * /settings/translation                   → TranslationSettings
 * /settings/translation/cost-memory        → CostMemoryPage
 * /settings/translation/queue              → QueueDashboard
 * /settings/notifications                 → NotificationsSettings
 * /settings/system                        → SystemSettings (setup half)
 * /settings/system/diagnostics            → SystemDiagnosticsPage (logs + monitoring + tools)
 * /settings/system/hooks                  → SystemHooksPage
 * /settings/system/scheduler              → SchedulerPage
 * /settings/profiles                       → ProfilesOverridesPage
 * /settings/hooks                         → redirect → /settings/system/hooks
 * /settings/webhooks                      → redirect → /settings/system/hooks
 */
import { lazy, Suspense } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { FormSkeleton } from '@/components/shared/PageSkeleton'
import { AdvancedSettingsProvider } from '@/contexts/AdvancedSettingsContext'
import { SettingsShell } from '@/components/settings/SettingsShell'

// Re-export legacy types/constants needed by other files
export { NAV_GROUPS } from './settingsFields'
export type { FieldConfig } from './settingsFields'

// Lazy-load each settings category page
const GeneralSettings = lazy(() =>
  import('./GeneralSettings').then((m) => ({ default: m.GeneralSettings })),
)
const ConnectionsSettings = lazy(() =>
  import('./ConnectionsSettings').then((m) => ({ default: m.ConnectionsSettings })),
)
const ConnectionsMetadataPage = lazy(() =>
  import('./ConnectionsMetadataPage').then((m) => ({ default: m.ConnectionsMetadataPage })),
)
const SubtitlesScoringPage = lazy(() =>
  import('./SubtitlesScoringPage').then((m) => ({ default: m.SubtitlesScoringPage })),
)
const SubtitlesFormatPage = lazy(() =>
  import('./SubtitlesFormatPage').then((m) => ({ default: m.SubtitlesFormatPage })),
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
// Plan B6 — Post-Processing Pipeline tab (curated ops + shell escape hatch)
const PostProcessingTab = lazy(() =>
  import('./PostProcessingTab').then((m) => ({ default: m.PostProcessingTab })),
)
const TranslationSettings = lazy(() =>
  import('./TranslationSettings').then((m) => ({ default: m.TranslationSettings })),
)
const CostMemoryPage = lazy(() =>
  import('./translation/CostMemoryPage').then((m) => ({
    default: m.CostMemoryPage,
  })),
)
const QueueDashboard = lazy(() =>
  import('./translation/QueueDashboard').then((m) => ({
    default: m.QueueDashboard,
  })),
)
const NotificationsSettings = lazy(() =>
  import('./NotificationsSettings').then((m) => ({ default: m.NotificationsSettings })),
)
const SystemSettings = lazy(() =>
  import('./SystemSettings').then((m) => ({ default: m.SystemSettings })),
)
const SystemDiagnosticsPage = lazy(() =>
  import('./SystemDiagnosticsPage').then((m) => ({ default: m.SystemDiagnosticsPage })),
)
const SystemHooksPage = lazy(() =>
  import('./SystemHooksPage').then((m) => ({ default: m.SystemHooksPage })),
)
const SchedulerPage = lazy(() =>
  import('./SchedulerPage').then((m) => ({ default: m.SchedulerPage })),
)
// Plan B7 — multi-engine sync orchestrator (informational tab)
const SyncEnginesTab = lazy(() =>
  import('./SyncEnginesTab').then((m) => ({ default: m.SyncEnginesTab })),
)
// 0.71.0 — Subtitle Automation (queue drain + SDH + foreign-track cleanup)
const SubtitleAutomationPage = lazy(() =>
  import('./SubtitleAutomationPage').then((m) => ({ default: m.SubtitleAutomationPage })),
)
const AboutSettings = lazy(() =>
  import('./AboutSettings').then((m) => ({ default: m.AboutSettings })),
)
const CleanupSettings = lazy(() =>
  import('./CleanupSettings').then((m) => ({ default: m.CleanupSettings })),
)
const ProfilesOverridesPage = lazy(() =>
  import('./ProfilesOverridesPage').then((m) => ({ default: m.ProfilesOverridesPage })),
)

export function SettingsPage() {
  return (
    <AdvancedSettingsProvider>
      <Suspense fallback={<FormSkeleton />}>
        <SettingsShell>
          <Routes>
            <Route index element={<Navigate to="/settings/general" replace />} />
            <Route path="general" element={<GeneralSettings />} />
            <Route path="connections" element={<ConnectionsSettings />} />
            <Route path="connections/metadata" element={<ConnectionsMetadataPage />} />
            <Route path="subtitles" element={<Navigate to="/settings/subtitles/scoring" replace />} />
            <Route
              path="subtitles/languages"
              element={<Navigate to="/settings/profiles" replace />}
            />
            <Route path="subtitles/scoring" element={<SubtitlesScoringPage />} />
            <Route path="subtitles/format" element={<SubtitlesFormatPage />} />
            <Route path="subtitles/stream-management" element={<SubtitlesStreamManagementPage />} />
            <Route path="providers" element={<ProvidersSettings />} />
            <Route path="providers/transcription" element={<ProvidersTranscriptionPage />} />
            <Route path="automation" element={<AutomationSettings />} />
            <Route path="automation/post-processing" element={<AutomationPostProcessingPage />} />
            <Route path="automation/post-processing-pipeline" element={<PostProcessingTab />} />
            <Route path="automation/subtitle" element={<SubtitleAutomationPage />} />
            <Route path="translation" element={<TranslationSettings />} />
            <Route
              path="translation/cost-memory"
              element={
                <Suspense fallback={<FormSkeleton />}>
                  <CostMemoryPage />
                </Suspense>
              }
            />
            <Route
              path="translation/queue"
              element={
                <Suspense fallback={<FormSkeleton />}>
                  <QueueDashboard />
                </Suspense>
              }
            />
            <Route path="notifications" element={<NotificationsSettings />} />
            <Route path="system" element={<SystemSettings />} />
            <Route path="system/diagnostics" element={<SystemDiagnosticsPage />} />
            <Route path="system/hooks" element={<SystemHooksPage />} />
            <Route path="system/scheduler" element={<SchedulerPage />} />
            <Route path="system/sync-engines" element={<SyncEnginesTab />} />
            <Route path="about" element={<AboutSettings />} />
            <Route path="cleanup" element={<Suspense fallback={<FormSkeleton />}><CleanupSettings /></Suspense>} />
            <Route path="profiles" element={<ProfilesOverridesPage />} />
            <Route path="hooks" element={<Navigate to="/settings/system/hooks" replace />} />
            <Route path="webhooks" element={<Navigate to="/settings/system/hooks" replace />} />
          </Routes>
        </SettingsShell>
      </Suspense>
    </AdvancedSettingsProvider>
  )
}
