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
    >
      <Suspense fallback={<FormSkeleton />}>
        <WhisperTab />
      </Suspense>
    </SettingsDetailLayout>
  )
}
