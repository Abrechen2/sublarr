import { useTranslation } from 'react-i18next'
import { PageHeader } from '@/components/layout/PageHeader'
import { SettingsGrid } from '@/components/settings/SettingsGrid'
import { SettingsSearch } from '@/components/settings/SettingsSearch'

export function SettingsOverview() {
  const { t } = useTranslation('common')

  return (
    <div data-testid="settings-overview" className="flex flex-col gap-6">
      <PageHeader
        title={t('nav.settings')}
        subtitle={t('settings.overview.subtitle', 'Configure Sublarr to fit your workflow')}
        actions={<SettingsSearch className="w-[260px]" />}
      />
      <SettingsGrid />
    </div>
  )
}
