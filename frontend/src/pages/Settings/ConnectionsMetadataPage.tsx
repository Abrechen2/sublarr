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
    >
      <Suspense fallback={<FormSkeleton />}>
        <AnidbTab />
      </Suspense>
    </SettingsDetailLayout>
  )
}
