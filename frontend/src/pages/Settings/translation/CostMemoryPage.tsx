import { useTranslation } from 'react-i18next'
import { SettingsDetailLayout } from '@/components/settings/SettingsDetailLayout'
import { BackendCostTable } from './BackendCostTable'
import { CostSummaryCards } from './CostSummaryCards'
import { TranslationMemoryPanel } from './TranslationMemoryPanel'

export function CostMemoryPage() {
  const { t } = useTranslation('settings')
  return (
    <SettingsDetailLayout
      title={t('translation.cost.title')}
      subtitle={t('translation.cost.subtitle')}
    >
      <div className="space-y-5">
        <CostSummaryCards />
        <div>
          <h3 className="mb-2 font-medium">
            {t('translation.cost.per_backend')}
          </h3>
          <BackendCostTable />
        </div>
        <TranslationMemoryPanel />
      </div>
    </SettingsDetailLayout>
  )
}
