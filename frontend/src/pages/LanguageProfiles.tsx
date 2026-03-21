/**
 * LanguageProfiles — Standalone page for Language Profile management.
 * Wraps the existing LanguageProfilesTab in a SettingsDetailLayout.
 */
import { Suspense, lazy } from 'react'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { FormSkeleton } from '@/components/shared/PageSkeleton'

const LanguageProfilesTab = lazy(() =>
  import('./Settings/AdvancedTab').then((m) => ({ default: m.LanguageProfilesTab })),
)

export function LanguageProfilesPage() {
  return (
    <SettingsDetailLayout
      title="Language Profiles"
      subtitle="Configure language profiles for subtitle search and translation."
    >
      <Suspense fallback={<FormSkeleton />}>
        <LanguageProfilesTab />
      </Suspense>
    </SettingsDetailLayout>
  )
}
