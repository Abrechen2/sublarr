import { lazy, Suspense } from 'react'
import { useTranslation } from 'react-i18next'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { FormSkeleton } from '@/components/shared/PageSkeleton'
import { DubtitleSettings } from './DubtitleSettings'

const RemuxTab = lazy(() => import('./RemuxTab').then((m) => ({ default: m.RemuxTab })))

export function SubtitlesStreamManagementPage() {
  const { t } = useTranslation('settings')
  return (
    <SettingsDetailLayout
      title={t('stream_management_page.title')}
      subtitle={t('stream_management_page.subtitle')}
    >
      <div className="space-y-6">
        <Suspense fallback={<FormSkeleton />}>
          <RemuxTab />
        </Suspense>
        <DubtitleSettings />
      </div>
    </SettingsDetailLayout>
  )
}
