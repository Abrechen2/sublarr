/**
 * LanguageProfiles — Standalone page for Language Profile management.
 * Wraps the existing LanguageProfilesTab in a SettingsDetailLayout.
 */
import { Suspense, lazy } from 'react'
import { useTranslation } from 'react-i18next'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { FormSkeleton } from '@/components/shared/PageSkeleton'

const LanguageProfilesTab = lazy(() =>
  import('./Settings/AdvancedTab').then((m) => ({ default: m.LanguageProfilesTab })),
)

export function LanguageProfilesPage() {
  const { t } = useTranslation('settings')

  return (
    <SettingsDetailLayout
      title={t('language_profiles.title')}
      subtitle={t('language_profiles.description')}
    >
      <Suspense fallback={<FormSkeleton />}>
        <LanguageProfilesTab />
      </Suspense>
    </SettingsDetailLayout>
  )
}
